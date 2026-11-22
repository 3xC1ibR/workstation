"""Read open asks from Ribbon Field without copying them into the Status store.

Ribbon Field owns asks. This reader runs its command-line listing and keeps the
result in memory; page refreshes read that copy while one background thread
renews it. When the listing is unavailable the reason is reported, never an
empty list presented as "no asks".
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

FIELDS = ("id", "kind", "blocking", "context", "unblocks", "effort_minutes", "link", "due_at", "session_id",
          "created_at", "thread_title", "project_label", "cwd", "stale", "overdue", "thread_closed", "options", "resolutions")
TITLE_LIMIT = 140
SENTENCE_END = re.compile(r"(?<=[.?!])\s+")


def title_and_detail(question):
    """Lead with one line: the first line, or its first sentence when that line is long. The rest is the detail."""
    lines = str(question).strip().splitlines() or [""]
    first, rest = lines[0].strip(), "\n".join(lines[1:]).strip()
    if len(first) > TITLE_LIMIT:
        sentence = SENTENCE_END.split(first, maxsplit=1)
        if len(sentence) == 2 and sentence[0]:
            first, rest = sentence[0], (sentence[1] + ("\n" + rest if rest else "")).strip()
    return first, rest or None


def command_path():
    configured = os.environ.get("AGENT_COORD_CLI")
    if configured:
        return configured
    launcher = Path.home() / ".local/bin/agent-coord"
    return str(launcher) if launcher.exists() else shutil.which("agent-coord")


def read_asks(command=None, timeout=8):
    """Return {available, reason, asks}; asks are display records for open, unsnoozed asks."""
    command = command or command_path()
    if not command:
        return {"available": False, "reason": "Ribbon Field's command-line interface is not installed on this machine.", "asks": []}
    environment = {**os.environ, "PATH": os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])}
    for name in ("AGENT_COORD_SESSION_ID", "CODEX_THREAD_ID"):
        environment.pop(name, None)             # a read for the user, not on behalf of any agent session
    try:
        completed = subprocess.run([command, "ask", "--list", "--all-sessions", "--status", "open"], capture_output=True,
                                   text=True, timeout=timeout, stdin=subprocess.DEVNULL, env=environment)
    except FileNotFoundError:
        return {"available": False, "reason": "Ribbon Field's command-line interface is not installed on this machine.", "asks": []}
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "Ribbon Field did not answer in time. Its asks are not shown.", "asks": []}
    except OSError:
        return {"available": False, "reason": "Ribbon Field's command-line interface could not be run.", "asks": []}
    if completed.returncode != 0:
        if "unrecognized arguments" in completed.stderr or "invalid choice" in completed.stderr:
            return {"available": False, "asks": [],
                    "reason": "The installed Ribbon Field does not provide the asks listing yet. Open Ribbon Field to see what agents need from you."}
        return {"available": False, "reason": "Ribbon Field could not list its asks. Open Ribbon Field to see them.", "asks": []}
    try:
        listing = json.loads(completed.stdout)
        listing = listing.get("asks", listing.get("result")) if isinstance(listing, dict) else listing
        if not isinstance(listing, list):
            raise ValueError("Unexpected listing")
        asks = []
        for record in listing:
            if record.get("status", "open") != "open" or record.get("snoozed"):
                continue
            title, detail = title_and_detail(record["question"])
            session = str(record["session_id"])
            asks.append({**{field: record.get(field) for field in FIELDS}, "title": title, "detail": detail,
                         "thread_link": "agentcoord://thread/" + session})
    except (ValueError, KeyError, TypeError, AttributeError):
        return {"available": False, "reason": "Ribbon Field returned an asks listing this page cannot read.", "asks": []}
    return {"available": True, "reason": None, "asks": asks}


class AskReader:
    """Share one listing among page refreshes without making them wait for Ribbon Field.

    The first read, and the first read after invalidate(), wait for the command.
    Every other read returns the last listing at once; a listing older than its
    lifetime starts one background refresh, and later reads see its result.
    """

    def __init__(self, reader=read_asks, lifetime=20):
        self.reader, self.lifetime = reader, lifetime
        self.lock = threading.Lock()                # guards the fields below; never held while the command runs
        self.waiting = threading.Lock()             # readers with no listing share one command
        self.value, self.read_at, self.refreshing, self.generation = None, 0.0, False, 0

    def current(self):
        with self.lock:
            if self.value is not None:
                if time.monotonic() - self.read_at > self.lifetime and not self.refreshing:
                    self.refreshing = True
                    threading.Thread(target=self._refresh, args=(self.generation,), name="ask-listing-refresh", daemon=True).start()
                return self.value
        with self.waiting:
            with self.lock:
                if self.value is not None:          # another waiting reader has just read it
                    return self.value
                generation = self.generation
            value = self.reader()
            self._keep(value, generation)
            return value

    def _keep(self, value, generation):
        """Retain a listing unless invalidate() was called after its command started."""
        with self.lock:
            if generation == self.generation:
                self.value, self.read_at = value, time.monotonic()

    def _refresh(self, generation):
        try:
            self._keep(self.reader(), generation)
        finally:
            with self.lock:
                self.refreshing = False

    def invalidate(self):
        """Read Ribbon Field again on the next request, after the user resolved an ask there."""
        with self.lock:
            self.value, self.generation = None, self.generation + 1


def for_operation(asks, operation):
    """Asks filed from the operation's conversations or from its workspace."""
    threads, workspace = set(operation["threads"]), operation["origin"].get("workspace")
    return [ask for ask in asks if ask["session_id"] in threads or (workspace and ask.get("cwd") == workspace)]

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


def shared_workspaces(operations):
    """Workspaces that hold more than one operation, such as a shared projects root."""
    seen, shared = set(), set()
    for operation in operations:
        workspace = operation.get("origin", {}).get("workspace")
        if workspace:
            (shared if workspace in seen else seen).add(workspace)
    return shared


def for_operation(asks, operation, shared=frozenset()):
    """Asks filed from the operation's conversations, or from its workspace when no other operation shares it.

    A workspace shared by several operations (for example a common projects root) says nothing about
    which operation an ask belongs to, so only the conversation match applies there.
    """
    threads, workspace = set(operation["threads"]), operation["origin"].get("workspace")
    by_workspace = bool(workspace) and workspace not in shared
    return [ask for ask in asks if ask["session_id"] in threads or (by_workspace and ask.get("cwd") == workspace)]

RESOLUTION_FIELDS = {"resolution", "option", "answer", "note"}


def ribbon_field_address():
    """The loopback address of the running Ribbon Field runtime, from its discovery record."""
    database = Path(os.environ.get("AGENT_COORD_DB") or Path.home() / ".local/state/agent-coord/state.sqlite3")
    discovery = database.parent / f".{database.name}.runtime" / "discovery.json"
    try:
        address = json.loads(discovery.read_text()).get("url")
    except (OSError, ValueError) as error:
        raise ValueError("Ribbon Field is not running on this Mac. Open it and try again.") from error
    if not isinstance(address, str) or not re.match(r"^http://(127\.0\.0\.1|localhost):\d+/$", address):
        raise ValueError("Ribbon Field's local address could not be read. Answer in Ribbon Field.")
    return address


REPLY_LIMIT = 8000


def reply_message(ask_id, title, text):
    """The user message a reply becomes. The page's script builds the same words on the tailnet address."""
    return (f"Reply to ask #{ask_id} ({title}), sent from the review page without resolving it:\n\n{text}\n\n"
            f"Ask #{ask_id} is still open. Resolve it, replace it or withdraw it once you have acted on this reply.")


def reply_to_ask(ask, text, *, address=None, opener=None):
    """Queue the user's words as a message in the asking conversation through Ribbon Field's loopback interface.

    The ask is not resolved. Ribbon Field delivers a queued message when that conversation is idle, as it does for
    its own composer. `ask` is the listing record, so the conversation and title come from Ribbon Field, not the page.
    """
    import urllib.error
    import urllib.parse
    import urllib.request
    import uuid
    if not isinstance(text, str) or not text.strip() or len(text) > REPLY_LIMIT:
        raise ValueError(f"Write a reply of at most {REPLY_LIMIT} characters.")
    address = address or ribbon_field_address()
    opener = opener or urllib.request.urlopen
    body = {"message": reply_message(ask["id"], ask["title"], text.strip()), "requestId": "review-page-reply-" + uuid.uuid4().hex}
    try:
        with opener(urllib.request.Request(address + "api/browser/config"), timeout=5) as response:
            token = json.load(response)["token"]
        request = urllib.request.Request(
            address + "api/browser/sessions/" + urllib.parse.quote(str(ask["session_id"]), safe="") + "/queue",
            data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "X-Agent-Coord-Token": token})
        with opener(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            message = json.load(error).get("error")
        except (ValueError, AttributeError):
            message = None
        raise ValueError(message or "Ribbon Field cannot deliver a message to that conversation. Use Reply in conversation.") from error
    except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError, ValueError) as error:
        raise ValueError("Could not reach Ribbon Field on this Mac. Your text is still here; try again.") from error


def resolve_ask(ask_id, body, *, snooze=False, address=None, opener=None):
    """Send the user's resolution to Ribbon Field's loopback browser API.

    Ribbon Field authorizes loopback requests itself; this adds no authority beyond what any
    process on this Mac already has. The Status service calls it only for its own local page.
    """
    import urllib.error
    import urllib.request
    if not isinstance(ask_id, int) or isinstance(ask_id, bool) or ask_id <= 0:
        raise ValueError("Choose an ask to answer.")
    allowed = {"until"} if snooze else RESOLUTION_FIELDS
    if not isinstance(body, dict) or not body or body.keys() - allowed:
        raise ValueError("Provide a resolution, an option or an answer.")
    address = address or ribbon_field_address()
    opener = opener or urllib.request.urlopen
    try:
        with opener(urllib.request.Request(address + "api/browser/config"), timeout=5) as response:
            token = json.load(response)["token"]
        request = urllib.request.Request(
            address + f"api/browser/asks/{ask_id}" + ("/snooze" if snooze else ""), data=json.dumps(body).encode(),
            method="POST", headers={"Content-Type": "application/json", "X-Agent-Coord-Token": token})
        with opener(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            message = json.load(error).get("error")
        except (ValueError, AttributeError):
            message = None
        raise ValueError(message or f"Ribbon Field did not accept this answer (HTTP {error.code}).") from error
    except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError, ValueError) as error:
        raise ValueError("Could not reach Ribbon Field on this Mac. Your text is still here; try again.") from error

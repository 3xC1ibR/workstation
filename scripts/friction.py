#!/usr/bin/python3
"""Record friction that agents encounter while working, in one central store.

Friction is avoidable effort that did not block the task: a command that had to
be retried, a misleading error, an undocumented setup step, a flaky test, an
instruction that disagreed with the repository. Agents record each occurrence
with one command and continue working:

    friction 'While <task>, <obstacle>; <likely cause or remedy>.'

The command captures the working directory, repository, branch, commit,
provider, session and host automatically, so the agent supplies only the
description. Records are appended to a single JSON Lines store outside every
repository (default ~/.local/state/friction/records.jsonl, overridable with
FRICTION_STORE), so recording never needs a repository write scope, never
produces a Git change, and survives worktree deletion.

Agents only record. The --list mode exists for people and triage jobs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAXIMUM_TEXT_LENGTH = 1500
SCOPES = ("repository", "environment", "harness", "external")
DEFAULT_STORE = Path.home() / ".local" / "state" / "friction" / "records.jsonl"

# Ordered (provider, session variable) pairs. The first provider whose marker
# variable is present wins; Agent Coord's explicit client name takes precedence.
PROVIDER_MARKERS = (
    ("claude", "CLAUDECODE", "CLAUDE_CODE_SESSION_ID"),
    ("codex", "CODEX_THREAD_ID", "CODEX_THREAD_ID"),
    ("gemini", "GEMINI_CLI", "GEMINI_SESSION_ID"),
    ("kimi", "KIMI_SESSION_ID", "KIMI_SESSION_ID"),
)


def store_path() -> Path:
    configured = os.environ.get("FRICTION_STORE")
    return Path(configured).expanduser() if configured else DEFAULT_STORE


def _git(cwd: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def repository_context(cwd: Path) -> dict[str, Any]:
    """Describe the repository containing cwd; worktrees map to their main checkout."""
    # One process in the common case; a repository without commits needs the fallback.
    output = _git(
        cwd, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir",
        "HEAD", "--abbrev-ref", "HEAD",
    )
    if output is not None and len(output.splitlines()) == 4:
        worktree_root, common_directory, commit, branch = output.splitlines()
    else:
        output = _git(cwd, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir")
        if output is None or len(output.splitlines()) != 2:
            return {
                "project": cwd.name or str(cwd),
                "repository_root": None,
                "worktree_root": None,
                "branch": None,
                "commit": None,
            }
        worktree_root, common_directory = output.splitlines()
        commit, branch = None, None
    repository_root = worktree_root
    if Path(common_directory).name == ".git":
        repository_root = str(Path(common_directory).parent)
    return {
        "project": Path(repository_root).name,
        "repository_root": repository_root,
        "worktree_root": worktree_root if worktree_root != repository_root else None,
        "branch": branch if branch and branch != "HEAD" else None,
        "commit": commit[:12] if commit else None,
    }


def agent_context(environment: dict[str, str]) -> dict[str, Any]:
    provider = environment.get("AGENT_COORD_CLIENT") or None
    session_id = environment.get("AGENT_COORD_SESSION_ID") or None
    for name, marker, session_variable in PROVIDER_MARKERS:
        if environment.get(marker):
            provider = provider or name
            session_id = session_id or environment.get(session_variable) or None
            break
    return {"provider": provider or "unknown", "session_id": session_id}


def build_record(text: str, scope: str | None, cwd: Path, environment: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "id": "frc_" + uuid.uuid4().hex[:12],
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "text": text,
        "scope": scope,
        **repository_context(cwd),
        "cwd": str(cwd),
        **agent_context(environment),
        "host": socket.gethostname().split(".")[0],
    }


def append_record(record: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        os.write(descriptor, line.encode("utf-8"))
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def normalize_text(raw: str) -> str:
    return " ".join(raw.split())


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def list_records(path: Path, project: str | None, since: str | None, output_format: str) -> str:
    records = read_records(path)
    if project:
        records = [record for record in records if record.get("project") == project]
    if since:
        records = [record for record in records if str(record.get("recorded_at", "")) >= since]
    if output_format == "jsonl":
        return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("project") or "unknown"), []).append(record)
    sections = []
    for name in sorted(grouped, key=lambda key: (-len(grouped[key]), key)):
        lines = [f"## {name} ({len(grouped[name])})", ""]
        for record in sorted(grouped[name], key=lambda item: str(item.get("recorded_at", "")), reverse=True):
            date = str(record.get("recorded_at", ""))[:10] or "undated"
            scope = record.get("scope") or "unclassified"
            lines.append(f"- {date} [{scope}, {record.get('provider', 'unknown')}] {record.get('text', '')}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections) + ("\n" if sections else "No friction records.\n")


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="friction",
        description="Record avoidable friction encountered while working. Agents only record.",
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="One or two sentences: 'While <task>, <obstacle>; <cause or remedy>.' Use - to read standard input.",
    )
    parser.add_argument("--scope", choices=SCOPES, help="Owner of the remedy.")
    parser.add_argument("--list", action="store_true", help="Print recorded friction (for people and triage).")
    parser.add_argument("--project", help="With --list, restrict to one project.")
    parser.add_argument("--since", help="With --list, restrict to records on or after this ISO date.")
    parser.add_argument("--format", choices=("markdown", "jsonl"), default="markdown", dest="output_format")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    path = store_path()
    if arguments.list:
        sys.stdout.write(list_records(path, arguments.project, arguments.since, arguments.output_format))
        return 0
    raw = arguments.text
    if raw is None or raw == "-":
        raw = "" if sys.stdin.isatty() else sys.stdin.read()
    text = normalize_text(raw)
    if not text:
        print("friction: provide a description, e.g. friction 'While <task>, <obstacle>.'", file=sys.stderr)
        return 2
    if len(text) > MAXIMUM_TEXT_LENGTH:
        print(f"friction: description exceeds {MAXIMUM_TEXT_LENGTH} characters; shorten it.", file=sys.stderr)
        return 2
    record = build_record(text, arguments.scope, Path.cwd(), dict(os.environ))
    try:
        append_record(record, path)
    except OSError as error:
        print(f"friction: could not record ({error.strerror}); continue your task.", file=sys.stderr)
        return 1
    print(f"Recorded {record['id']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

Agents only record. The --list and --resolve modes exist for people and for
agents assigned friction triage. Triage never edits existing lines: it appends a
resolution entry that names the records it handles, its disposition and the
evidence (a commit, Beads issue or URL). --list hides resolved records unless
--all is given; a record's latest resolution wins.
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
DISPOSITIONS = ("fixed", "duplicate", "stale", "external", "declined")
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


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def build_resolution(
    record_ids: list[str],
    disposition: str,
    reference: str,
    note: str | None,
    cwd: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "kind": "resolution",
        "id": "frr_" + uuid.uuid4().hex[:12],
        "recorded_at": _now(),
        "resolves": record_ids,
        "disposition": disposition,
        "reference": reference,
        "note": note,
        "cwd": str(cwd),
        **agent_context(environment),
        "host": socket.gethostname().split(".")[0],
    }


def build_record(text: str, scope: str | None, cwd: Path, environment: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "kind": "report",
        "id": "frc_" + uuid.uuid4().hex[:12],
        "recorded_at": _now(),
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


def partition(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Split store entries into reports and the latest resolution for each report ID.

    Entries without a kind predate resolutions and are reports.
    """
    reports: list[dict[str, Any]] = []
    resolutions: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry.get("kind", "report") == "resolution":
            for record_id in entry.get("resolves") or []:
                resolutions[str(record_id)] = entry
        else:
            reports.append(entry)
    return reports, resolutions


def resolve_records(
    path: Path,
    record_ids: list[str],
    disposition: str,
    reference: str,
    note: str | None,
    cwd: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    """Append one resolution entry; raise ValueError if any ID is not a recorded report."""
    unique_ids = list(dict.fromkeys(record_ids))
    if not unique_ids:
        raise ValueError("no record IDs given")
    reports, _ = partition(read_records(path))
    known = {str(report.get("id")) for report in reports}
    unknown = [record_id for record_id in unique_ids if record_id not in known]
    if unknown:
        raise ValueError("unknown record IDs: " + " ".join(unknown))
    resolution = build_resolution(unique_ids, disposition, reference, note, cwd, environment)
    append_record(resolution, path)
    return resolution


def list_records(
    path: Path,
    project: str | None,
    since: str | None,
    output_format: str,
    scope: str | None = None,
    include_resolved: bool = False,
) -> str:
    records, resolutions = partition(read_records(path))
    if not include_resolved:
        records = [record for record in records if str(record.get("id")) not in resolutions]
    if scope:
        records = [record for record in records if record.get("scope") == scope]
    if project:
        records = [record for record in records if record.get("project") == project]
    if since:
        records = [record for record in records if str(record.get("recorded_at", "")) >= since]
    if output_format == "jsonl":
        lines = []
        for record in records:
            resolution = resolutions.get(str(record.get("id")))
            if resolution is not None:
                record = {**record, "resolution": _resolution_summary(resolution)}
            lines.append(json.dumps(record, ensure_ascii=False) + "\n")
        return "".join(lines)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("project") or "unknown"), []).append(record)
    sections = []
    for name in sorted(grouped, key=lambda key: (-len(grouped[key]), key)):
        lines = [f"## {name} ({len(grouped[name])})", ""]
        for record in sorted(grouped[name], key=lambda item: str(item.get("recorded_at", "")), reverse=True):
            date = str(record.get("recorded_at", ""))[:10] or "undated"
            scope = record.get("scope") or "unclassified"
            resolution = resolutions.get(str(record.get("id")))
            status = ""
            if resolution is not None:
                status = f" (resolved {resolution.get('disposition')}: {resolution.get('reference')})"
            lines.append(
                f"- {date} {record.get('id', 'no-id')} [{scope}, {record.get('provider', 'unknown')}]{status} "
                f"{record.get('text', '')}"
            )
        sections.append("\n".join(lines))
    return "\n\n".join(sections) + ("\n" if sections else "No friction records.\n")


def _resolution_summary(resolution: dict[str, Any]) -> dict[str, Any]:
    return {
        key: resolution.get(key)
        for key in ("id", "recorded_at", "disposition", "reference", "note", "session_id")
    }


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="friction",
        description=(
            "Record avoidable friction encountered while working. Agents only record; "
            "--list and --resolve are for people and assigned friction triage."
        ),
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="One or two sentences: 'While <task>, <obstacle>; <cause or remedy>.' Use - to read standard input.",
    )
    parser.add_argument("--scope", choices=SCOPES, help="Owner of the remedy. With --list, restrict to one scope.")
    parser.add_argument("--list", action="store_true", help="Print unresolved friction (for people and triage).")
    parser.add_argument("--all", action="store_true", dest="include_resolved", help="With --list, include resolved records.")
    parser.add_argument("--project", help="With --list, restrict to one project.")
    parser.add_argument("--since", help="With --list, restrict to records on or after this ISO date.")
    parser.add_argument(
        "--resolve",
        nargs="+",
        metavar="RECORD_ID",
        help="Mark records handled (triage only). Use - to read whitespace-separated IDs from standard input.",
    )
    parser.add_argument("--disposition", choices=DISPOSITIONS, help="With --resolve, how the records were handled.")
    parser.add_argument("--reference", help="With --resolve, the evidence: commit, Beads issue, record ID or URL.")
    parser.add_argument("--note", help="With --resolve, an optional one-sentence explanation.")
    parser.add_argument("--format", choices=("markdown", "jsonl"), default="markdown", dest="output_format")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    path = store_path()
    if arguments.resolve:
        return _resolve_command(arguments, path)
    if arguments.list:
        listing = list_records(
            path,
            arguments.project,
            arguments.since,
            arguments.output_format,
            arguments.scope,
            arguments.include_resolved,
        )
        try:
            sys.stdout.write(listing)
            sys.stdout.flush()
        except BrokenPipeError:
            # A reader such as head closed the pipe early; that is not an error.
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
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


def _resolve_command(arguments: argparse.Namespace, path: Path) -> int:
    if not arguments.disposition or not arguments.reference or not arguments.reference.strip():
        print("friction: --resolve requires --disposition and --reference.", file=sys.stderr)
        return 2
    record_ids: list[str] = []
    for value in arguments.resolve:
        if value == "-":
            record_ids.extend(sys.stdin.read().split())
        else:
            record_ids.append(value)
    note = normalize_text(arguments.note) if arguments.note else None
    try:
        resolution = resolve_records(
            path,
            record_ids,
            arguments.disposition,
            arguments.reference.strip(),
            note or None,
            Path.cwd(),
            dict(os.environ),
        )
    except ValueError as error:
        print(f"friction: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"friction: could not record the resolution ({error.strerror}).", file=sys.stderr)
        return 1
    print(f"Resolved {len(resolution['resolves'])} records as {resolution['disposition']} ({resolution['id']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

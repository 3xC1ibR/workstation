#!/usr/bin/env python3
"""Lightweight, stdlib-only Stoic I/O CLI for technical threads.

Encapsulates Stoic Bearer authentication internally without loading personal
context, LTM/Toggl bundles, or activating conversation sync hooks.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


DEFAULT_ORIGIN = "https://tryblume.ai"
DEFAULT_TOKEN_FILE = "~/.config/stoic/codex-token"
DEFAULT_TIMEOUT = 20

SEARCH_TYPES = (
    "message",
    "task",
    "project",
    "note",
    "bookmark",
    "document",
    "goal",
    "reminder",
    "program",
    "assistant_job",
    "custom_record",
    "automation",
)
SEARCH_MODES = ("auto", "lexical", "literal", "semantic")
TASK_LIST_STATUSES = ("pending", "in_progress", "done", "wont_do", "all")
TASK_CREATE_STATUSES = ("pending", "in_progress")
RESPONSIBILITIES = ("user", "agent", "undetermined")

HTTP_ERROR_HINTS = {
    401: "Check the Stoic credential and renew it if expired.",
    403: "Check Stoic account permissions.",
    404: "Requested record or endpoint was not found.",
    409: "Conflict with existing Stoic state.",
    412: "Precondition failed (stale ETag or revision).",
    422: "Stoic rejected the request payload or parameters.",
}


class StoicError(Exception):
    """Base error for stoic_io CLI failures."""


class StoicAuthError(StoicError):
    """Credential resolution or actor-verification failure."""


class StoicValidationError(StoicError):
    """Local argument or payload validation failure."""


class StoicHTTPError(StoicError):
    """HTTP error returned by Stoic."""

    def __init__(self, status: int, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


class NoRedirect(HTTPRedirectHandler):
    """Refuse HTTP redirects so Bearer tokens are never forwarded off-origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def scrub_secrets(text: str, secrets: Sequence[str]) -> str:
    """Remove any secret values from error or log strings."""
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "<redacted>")
    return cleaned


def resolve_origin(env: dict[str, str] | None = None) -> str:
    """Resolve and validate the Stoic API origin URL."""
    environ = os.environ if env is None else env
    raw = (environ.get("STOIC_API_URL") or DEFAULT_ORIGIN).strip().rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise StoicValidationError(
            "STOIC_API_URL must be an absolute http(s) origin."
        )
    if parts.query or parts.fragment:
        raise StoicValidationError(
            "STOIC_API_URL must not include query parameters or fragments."
        )
    return raw


def resolve_token(env: dict[str, str] | None = None) -> str:
    """Resolve the Stoic agent Bearer token using standard workstation precedence.

    Order: STOIC_API_TOKEN -> STOIC_API_TOKEN_FILE -> ~/.config/stoic/codex-token.
    """
    environ = os.environ if env is None else env
    value = environ.get("STOIC_API_TOKEN")
    if not value:
        token_path = environ.get("STOIC_API_TOKEN_FILE") or DEFAULT_TOKEN_FILE
        try:
            value = Path(token_path).expanduser().read_text(encoding="utf-8")
        except FileNotFoundError:
            raise StoicAuthError("Stoic agent credential is missing.") from None
        except OSError as exc:
            raise StoicAuthError(
                f"Unable to read Stoic agent credential ({exc.strerror or type(exc).__name__})."
            ) from None
    value = value.strip()
    if not value:
        raise StoicAuthError("Stoic agent credential is empty.")
    if not re.fullmatch(r"[!-~]+", value):
        raise StoicAuthError(
            "Stoic agent credential contains invalid characters."
        )
    return value


def _extract_error_detail(raw_body: str) -> Any:
    if not raw_body:
        return None
    try:
        parsed = json.loads(raw_body)
    except ValueError:
        snippet = raw_body.strip()
        return snippet[:400] if snippet else None
    if isinstance(parsed, dict) and "detail" in parsed:
        return parsed["detail"]
    return parsed


def api_request(
    method: str,
    path: str,
    token: str,
    *,
    query: Sequence[tuple[str, str]] = (),
    body: dict[str, Any] | None = None,
    origin: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    opener: Any = None,
) -> Any:
    """Send an authenticated JSON request to Stoic without following redirects."""
    base = origin if origin is not None else resolve_origin()
    url = base + path
    if query:
        url = url + "?" + urlencode(list(query), doseq=True)

    payload_bytes: bytes | None = None
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
    }
    if body is not None:
        payload_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url, data=payload_bytes, headers=headers, method=method)
    client = opener if opener is not None else build_opener(NoRedirect)

    try:
        with client.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return {}
            try:
                return json.loads(raw)
            except ValueError as exc:
                raise StoicError(
                    f"Stoic returned non-JSON response for {method} {path}."
                ) from exc
    except HTTPError as err:
        try:
            err_body = err.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = ""
        finally:
            try:
                err.close()
            except Exception:
                pass
        detail = _extract_error_detail(scrub_secrets(err_body, (token,)))
        hint = HTTP_ERROR_HINTS.get(err.code, "")
        detail_str = ""
        if detail is not None:
            formatted = (
                detail
                if isinstance(detail, str)
                else json.dumps(detail, ensure_ascii=False)
            )
            detail_str = f" Detail: {formatted[:400]}"
        hint_str = f" {hint}" if hint else ""
        raise StoicHTTPError(
            err.code,
            scrub_secrets(
                f"Stoic returned HTTP {err.code} for {method} {path}.{hint_str}{detail_str}",
                (token,),
            ),
            detail=detail,
        ) from None
    except (URLError, OSError) as err:
        reason = getattr(err, "reason", err)
        raise StoicError(
            scrub_secrets(
                f"Stoic request failed for {method} {path}: {reason}",
                (token,),
            )
        ) from None


def verify_agent_actor(
    token: str,
    *,
    origin: str | None = None,
    opener: Any = None,
) -> dict[str, Any]:
    """Verify GET /api/auth/web/me reports actor == 'agent' before any write."""
    me = api_request(
        "GET", "/api/auth/web/me", token, origin=origin, opener=opener
    )
    actor = me.get("actor") if isinstance(me, dict) else None
    if actor != "agent":
        raise StoicAuthError(
            f"Refusing write: Stoic credential actor is {actor!r}, expected 'agent'."
        )
    return me


def parse_tags(
    raw_values: Sequence[str] | None,
    *,
    lowercase: bool = False,
    max_count: int | None = None,
    max_len: int | None = None,
) -> list[str] | None:
    """Parse comma-separated and/or repeated tag flags into a clean list."""
    if not raw_values:
        return None
    seen: set[str] = set()
    tags: list[str] = []
    for item in raw_values:
        for piece in item.split(","):
            cleaned = piece.strip()
            if lowercase:
                cleaned = cleaned.lower()
            if not cleaned or cleaned in seen:
                continue
            if max_len is not None and len(cleaned) > max_len:
                raise StoicValidationError(
                    f"Tag {cleaned!r} exceeds maximum length of {max_len} characters."
                )
            seen.add(cleaned)
            tags.append(cleaned)
    if lowercase:
        tags.sort()
    if max_count is not None and len(tags) > max_count:
        raise StoicValidationError(
            f"At most {max_count} tags are allowed (got {len(tags)})."
        )
    return tags or None


def parse_search_types(raw_values: Sequence[str] | None) -> list[str]:
    """Parse and validate Stoic record search types."""
    if not raw_values:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        for piece in item.split(","):
            record_type = piece.strip()
            if not record_type:
                continue
            if record_type not in SEARCH_TYPES:
                allowed = ", ".join(SEARCH_TYPES)
                raise StoicValidationError(
                    f"Unknown record type {record_type!r}. Must be one of: {allowed}"
                )
            if record_type not in seen:
                seen.add(record_type)
                result.append(record_type)
    return result


def validate_iso_datetime(value: str) -> str:
    """Validate an ISO 8601 date or datetime string (Python 3.10+ safe)."""
    cleaned = value.strip()
    if not cleaned:
        raise StoicValidationError("--due must not be empty.")
    normalized = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        raise StoicValidationError(
            f"Invalid --due datetime {value!r}; expected ISO 8601 (e.g. 2026-12-01 or 2026-12-01T17:00:00Z)."
        ) from None
    return cleaned


def validate_http_url(url: str) -> str:
    """Validate a bookmark URL matching Stoic's BookmarkCreate contract."""
    cleaned = url.strip()
    parts = urlsplit(cleaned)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise StoicValidationError("URL must be an absolute http(s) link.")
    if len(cleaned) > 2048:
        raise StoicValidationError("URL must be 2048 characters or fewer.")
    return cleaned


def _clean_provenance_value(label: str, value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > 255:
        raise StoicValidationError(
            f"{label} must be 255 characters or fewer."
        )
    return cleaned


def build_agent_provenance(
    args: argparse.Namespace,
    env: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """Build optional AgentProvenance metadata for agent-authored notes."""
    environ = os.environ if env is None else env
    client = _clean_provenance_value("--client", getattr(args, "client", None))
    model = _clean_provenance_value("--model", getattr(args, "model", None))
    session_id = _clean_provenance_value(
        "--session-id",
        getattr(args, "session_id", None)
        or environ.get("AGENT_COORD_SESSION_ID"),
    )
    thread_id = _clean_provenance_value(
        "--thread-id",
        getattr(args, "thread_id", None) or environ.get("CODEX_THREAD_ID"),
    )
    provenance: dict[str, str] = {}
    if client:
        provenance["client"] = client
    if model:
        provenance["model"] = model
    if thread_id:
        provenance["thread_id"] = thread_id
    if session_id:
        provenance["session_id"] = session_id
    return provenance or None


def build_search_request(args: argparse.Namespace) -> dict[str, Any]:
    """Build validated GET /api/search/records request specification."""
    query_text = args.query.strip()
    if not query_text:
        raise StoicValidationError("Search query must not be empty.")
    if not (1 <= args.limit <= 50):
        raise StoicValidationError("--limit must be between 1 and 50.")
    if not (0 <= args.offset <= 500):
        raise StoicValidationError("--offset must be between 0 and 500.")
    record_types = parse_search_types(args.types)
    query: list[tuple[str, str]] = [
        ("q", query_text),
        ("mode", args.mode),
        ("limit", str(args.limit)),
        ("offset", str(args.offset)),
    ]
    for record_type in record_types:
        query.append(("types", record_type))
    if args.project_id:
        query.append(("project_id", args.project_id.strip()))
    if args.status:
        query.append(("status", args.status.strip()))
    return {
        "method": "GET",
        "path": "/api/search/records",
        "query": query,
        "body": None,
    }


def build_get_request(args: argparse.Namespace) -> dict[str, Any]:
    """Build validated GET /api/search/records/{record_type}/{id} request spec."""
    record_type = args.record_type.strip()
    if record_type not in SEARCH_TYPES:
        allowed = ", ".join(SEARCH_TYPES)
        raise StoicValidationError(
            f"Unknown record type {record_type!r}. Must be one of: {allowed}"
        )
    record_id = args.id.strip()
    if not record_id or len(record_id) > 255:
        raise StoicValidationError(
            "Record ID is required and must be at most 255 characters."
        )
    safe_type = quote(record_type, safe="")
    safe_id = quote(record_id, safe="")
    return {
        "method": "GET",
        "path": f"/api/search/records/{safe_type}/{safe_id}",
        "query": [],
        "body": None,
    }


def build_list_tasks_request(args: argparse.Namespace) -> dict[str, Any]:
    """Build validated GET /api/tasks request specification."""
    if not (1 <= args.limit <= 200):
        raise StoicValidationError("--limit must be between 1 and 200.")
    if args.offset < 0:
        raise StoicValidationError("--offset must be 0 or greater.")
    query: list[tuple[str, str]] = [
        ("limit", str(args.limit)),
        ("offset", str(args.offset)),
    ]
    if args.status and args.status != "all":
        query.append(("status", args.status))
    if args.project_id:
        query.append(("project_id", args.project_id.strip()))
    return {
        "method": "GET",
        "path": "/api/tasks",
        "query": query,
        "body": None,
    }


def build_save_note_request(
    args: argparse.Namespace,
    *,
    stdin: Any = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build validated POST /api/notes request specification."""
    title = args.title.strip()
    if not title:
        raise StoicValidationError("--title must not be empty.")
    if args.body is not None:
        content = args.body
    elif args.body_file == "-":
        stream = sys.stdin if stdin is None else stdin
        content = stream.read()
    else:
        try:
            content = Path(args.body_file).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise StoicValidationError(
                f"Failed to read --body-file {args.body_file!r}: {exc.strerror or exc}"
            ) from None

    body: dict[str, Any] = {
        "title": title,
        "content": content,
        "author": "agent",
    }
    tags = parse_tags(args.tags)
    if tags is not None:
        body["tags"] = tags
    if args.project_id:
        project_id = args.project_id.strip()
        if project_id:
            body["project_id"] = project_id
    provenance = build_agent_provenance(args, env=env)
    if provenance is not None:
        body["agent_provenance"] = provenance

    return {
        "method": "POST",
        "path": "/api/notes",
        "query": [],
        "body": body,
    }


def build_save_task_request(args: argparse.Namespace) -> dict[str, Any]:
    """Build validated POST /api/tasks request specification.

    Note: Stoic's POST /api/tasks accepts project_id as a query parameter,
    while title, description, status, due_date, and agreement go in the body.
    """
    title = args.title.strip()
    if not title:
        raise StoicValidationError("--title must not be empty.")
    if len(title) > 255:
        raise StoicValidationError("--title must be 255 characters or fewer.")

    body: dict[str, Any] = {
        "title": title,
        "description": args.description if args.description is not None else "",
        "status": args.status,
    }
    if args.due is not None:
        body["due_date"] = validate_iso_datetime(args.due)

    has_agreement = any(
        (
            args.confirmed,
            args.suggested,
            args.responsibility is not None,
            args.source is not None,
        )
    )
    if has_agreement:
        source = (args.source or "").strip()
        if len(source) > 4000:
            raise StoicValidationError(
                "--source must be 4000 characters or fewer."
            )
        if args.confirmed:
            state = "confirmed"
        elif args.suggested:
            state = "suggested"
        else:
            state = "unknown"
        body["agreement"] = {
            "state": state,
            "responsibility": args.responsibility or "undetermined",
            "source": source,
        }

    query: list[tuple[str, str]] = []
    if args.project_id:
        project_id = args.project_id.strip()
        if project_id:
            query.append(("project_id", project_id))

    return {
        "method": "POST",
        "path": "/api/tasks",
        "query": query,
        "body": body,
    }


def build_save_bookmark_request(args: argparse.Namespace) -> dict[str, Any]:
    """Build validated POST /api/bookmarks request specification."""
    url = validate_http_url(args.url)
    body: dict[str, Any] = {"url": url}
    if args.title is not None:
        title = args.title.strip()
        if title:
            body["title"] = title
    if args.note is not None:
        body["note"] = args.note
    tags = parse_tags(args.tags, lowercase=True, max_count=20, max_len=50)
    if tags is not None:
        body["tags"] = tags
    return {
        "method": "POST",
        "path": "/api/bookmarks",
        "query": [],
        "body": body,
    }


def format_dry_run(spec: dict[str, Any], *, origin: str) -> dict[str, Any]:
    """Build a JSON-serializable dry-run preview without touching credentials."""
    url = origin + spec["path"]
    if spec["query"]:
        url = url + "?" + urlencode(list(spec["query"]), doseq=True)
    return {
        "dry_run": True,
        "method": spec["method"],
        "url": url,
        "headers": {
            "Authorization": "Bearer <redacted>",
            "Content-Type": "application/json",
        },
        "body": spec["body"],
        "pre_write_check": "GET /api/auth/web/me (requires actor == 'agent')",
    }


def format_human(command: str, data: Any) -> str:
    """Render a concise human-readable summary for CLI responses."""
    if isinstance(data, dict) and data.get("dry_run"):
        lines = [
            f"DRY RUN {data['method']} {data['url']}",
            f"Pre-write check: {data['pre_write_check']}",
            json.dumps(data["body"], ensure_ascii=False, indent=2),
        ]
        return "\n".join(lines)

    if command == "whoami" and isinstance(data, dict):
        return (
            f"id={data.get('id')} actor={data.get('actor')} "
            f"account_type={data.get('account_type')} "
            f"provider={data.get('auth_provider')}"
        )

    if command == "search" and isinstance(data, dict):
        items = data.get("items") or []
        if not items:
            return "No matching records."
        lines = []
        for item in items:
            rec_type = item.get("type", "?")
            rec_id = item.get("id", "?")
            title = item.get("title") or "(untitled)"
            snippet = (item.get("snippet") or "").replace("\n", " ").strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            line = f"[{rec_type}] {rec_id} — {title}"
            if snippet:
                line = f"{line}\n  {snippet}"
            lines.append(line)
        return "\n".join(lines)

    if command == "get" and isinstance(data, dict):
        rec_type = data.get("type", "?")
        rec_id = data.get("id", "?")
        details = data.get("details")
        header = f"[{rec_type}] {rec_id}"
        return header + "\n" + json.dumps(details, ensure_ascii=False, indent=2)

    if command == "list-tasks" and isinstance(data, dict):
        items = data.get("items") or []
        total = data.get("total", len(items))
        if not items:
            return f"Tasks: 0 (total={total})"
        lines = [f"Tasks: showing {len(items)} of {total}"]
        for item in items:
            status = item.get("status", "?")
            rec_id = item.get("id", "?")
            title = item.get("title") or "(untitled)"
            due = item.get("due_date")
            due_part = f" due={due}" if due else ""
            lines.append(f"- [{status}] {rec_id} — {title}{due_part}")
        return "\n".join(lines)

    if command in ("save-note", "save-task", "save-bookmark") and isinstance(
        data, dict
    ):
        rec_id = data.get("id", "?")
        label = data.get("title") or data.get("url") or "(saved)"
        return f"Saved {command.replace('save-', '')}: {rec_id} — {label}"

    return json.dumps(data, ensure_ascii=False, indent=2)


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser supporting global or per-subcommand format flags."""
    fmt_parent = argparse.ArgumentParser(add_help=False)
    fmt_group = fmt_parent.add_mutually_exclusive_group()
    fmt_group.add_argument(
        "--json",
        dest="output_format",
        action="store_const",
        const="json",
        default=argparse.SUPPRESS,
        help="Output JSON (default).",
    )
    fmt_group.add_argument(
        "--human",
        dest="output_format",
        action="store_const",
        const="human",
        default=argparse.SUPPRESS,
        help="Output concise human-readable summary.",
    )

    parser = argparse.ArgumentParser(
        prog="stoic_io.py",
        description="Lightweight read/write Stoic I/O CLI (stdlib only, no full context load).",
        parents=[fmt_parent],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Read commands
    sub.add_parser(
        "whoami",
        parents=[fmt_parent],
        help="Show authenticated Stoic identity and actor.",
    )

    p_search = sub.add_parser(
        "search",
        parents=[fmt_parent],
        help="Search current Stoic records.",
    )
    p_search.add_argument("query", help="Search query string.")
    p_search.add_argument(
        "--types",
        action="append",
        help="Record types (comma-separated or repeated): " + ", ".join(SEARCH_TYPES),
    )
    p_search.add_argument(
        "--limit", type=int, default=10, help="Max results (1-50, default 10)."
    )
    p_search.add_argument(
        "--offset", type=int, default=0, help="Pagination offset (0-500, default 0)."
    )
    p_search.add_argument(
        "--mode",
        choices=SEARCH_MODES,
        default="auto",
        help="Search mode (default: auto).",
    )
    p_search.add_argument("--project-id", help="Filter by project ID.")
    p_search.add_argument("--status", help="Filter by record status.")

    p_get = sub.add_parser(
        "get",
        parents=[fmt_parent],
        help="Fetch a single Stoic record by type and ID.",
    )
    p_get.add_argument(
        "record_type",
        help="Record type (" + ", ".join(SEARCH_TYPES) + ").",
    )
    p_get.add_argument("id", help="Record ID.")

    p_tasks = sub.add_parser(
        "list-tasks",
        parents=[fmt_parent],
        help="List Stoic tasks.",
    )
    p_tasks.add_argument(
        "--status",
        choices=TASK_LIST_STATUSES,
        default="all",
        help="Task status filter (default: all).",
    )
    p_tasks.add_argument("--project-id", help="Filter by project ID.")
    p_tasks.add_argument(
        "--limit", type=int, default=20, help="Max results (1-200, default 20)."
    )
    p_tasks.add_argument(
        "--offset", type=int, default=0, help="Pagination offset (>=0, default 0)."
    )

    # Write commands
    p_note = sub.add_parser(
        "save-note",
        parents=[fmt_parent],
        help="Create an agent-authored Stoic note.",
    )
    p_note.add_argument("--title", required=True, help="Note title.")
    note_body = p_note.add_mutually_exclusive_group(required=True)
    note_body.add_argument("--body", help="Note body text.")
    note_body.add_argument(
        "--body-file",
        help="Path to note body file, or '-' to read from stdin.",
    )
    p_note.add_argument(
        "--tags", action="append", help="Comma-separated or repeated tags."
    )
    p_note.add_argument("--project-id", help="Optional Stoic project ID.")
    p_note.add_argument("--client", help="Optional agent_provenance.client.")
    p_note.add_argument("--model", help="Optional agent_provenance.model.")
    p_note.add_argument("--thread-id", help="Optional agent_provenance.thread_id.")
    p_note.add_argument(
        "--session-id", help="Optional agent_provenance.session_id."
    )
    p_note.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the exact request payload without sending.",
    )

    p_task = sub.add_parser(
        "save-task",
        parents=[fmt_parent],
        help="Create a Stoic task.",
    )
    p_task.add_argument("--title", required=True, help="Task title (<=255 chars).")
    p_task.add_argument("--description", default="", help="Task description.")
    p_task.add_argument(
        "--project-id", help="Parent project ID (sent as query param)."
    )
    p_task.add_argument(
        "--due", help="Optional ISO 8601 due date or datetime."
    )
    p_task.add_argument(
        "--status",
        choices=TASK_CREATE_STATUSES,
        default="pending",
        help="Initial task status (default: pending).",
    )
    agree_group = p_task.add_mutually_exclusive_group()
    agree_group.add_argument(
        "--confirmed",
        action="store_true",
        help="Set agreement.state = 'confirmed'.",
    )
    agree_group.add_argument(
        "--suggested",
        action="store_true",
        help="Set agreement.state = 'suggested'.",
    )
    p_task.add_argument(
        "--responsibility",
        choices=RESPONSIBILITIES,
        help="Set agreement.responsibility.",
    )
    p_task.add_argument(
        "--source", help="Set agreement.source (e.g. thread link or context)."
    )
    p_task.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the exact request payload without sending.",
    )

    p_bm = sub.add_parser(
        "save-bookmark",
        parents=[fmt_parent],
        help="Create or re-unread a Stoic bookmark.",
    )
    p_bm.add_argument("--url", required=True, help="Absolute http(s) URL.")
    p_bm.add_argument("--title", help="Optional bookmark title.")
    p_bm.add_argument("--note", help="Optional bookmark note.")
    p_bm.add_argument(
        "--tags",
        action="append",
        help="Optional comma-separated or repeated tags (max 20, <=50 chars).",
    )
    p_bm.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the exact request payload without sending.",
    )

    return parser


def run_command(
    argv: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    stdin: Any = None,
    opener: Any = None,
) -> tuple[str, Any, str]:
    """Parse arguments, execute the command, and return (command, data, output_format)."""
    parser = build_parser()
    args = parser.parse_args(list(argv))
    output_format = getattr(args, "output_format", "json")
    origin = resolve_origin(env=env)

    if args.command == "whoami":
        token = resolve_token(env=env)
        data = api_request(
            "GET", "/api/auth/web/me", token, origin=origin, opener=opener
        )
        return args.command, data, output_format

    if args.command == "search":
        spec = build_search_request(args)
        token = resolve_token(env=env)
        data = api_request(
            spec["method"],
            spec["path"],
            token,
            query=spec["query"],
            origin=origin,
            opener=opener,
        )
        return args.command, data, output_format

    if args.command == "get":
        spec = build_get_request(args)
        token = resolve_token(env=env)
        data = api_request(
            spec["method"],
            spec["path"],
            token,
            origin=origin,
            opener=opener,
        )
        return args.command, data, output_format

    if args.command == "list-tasks":
        spec = build_list_tasks_request(args)
        token = resolve_token(env=env)
        data = api_request(
            spec["method"],
            spec["path"],
            token,
            query=spec["query"],
            origin=origin,
            opener=opener,
        )
        return args.command, data, output_format

    if args.command == "save-note":
        spec = build_save_note_request(args, stdin=stdin, env=env)
    elif args.command == "save-task":
        spec = build_save_task_request(args)
    elif args.command == "save-bookmark":
        spec = build_save_bookmark_request(args)
    else:
        raise StoicValidationError(f"Unsupported command: {args.command}")

    if args.dry_run:
        return args.command, format_dry_run(spec, origin=origin), output_format

    token = resolve_token(env=env)
    verify_agent_actor(token, origin=origin, opener=opener)
    data = api_request(
        spec["method"],
        spec["path"],
        token,
        query=spec["query"],
        body=spec["body"],
        origin=origin,
        opener=opener,
    )
    return args.command, data, output_format


def main(argv: Sequence[str] | None = None) -> int:
    try:
        command, data, output_format = run_command(
            sys.argv[1:] if argv is None else argv
        )
    except StoicError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if output_format == "human":
        print(format_human(command, data))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

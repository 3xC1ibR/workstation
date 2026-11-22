#!/usr/bin/env python3
"""Retain a generated status report in the shared, provider-independent inbox."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile

import re

from build_status import render, validate

OPERATION_KEY = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*\Z")


def inbox_directory():
    return Path(os.environ.get("AGENT_STATUS_INBOX", Path.home() / ".local/state/agent-status/inbox")).expanduser()


def register(document, html, *, workspace, agent=None, provider=None, thread_id=None, root=None, viewer_url=None, operation=None):
    validate(document)
    if not isinstance(html, str) or not html.strip() or len(html.encode()) > 8 * 1024 * 1024:
        raise ValueError("A nonempty HTML report of at most 8 MB is required")
    origin = {"workspace": str(workspace), "agent": agent or None, "provider": provider or None,
              "thread_id": thread_id or None, "host": socket.gethostname()}
    if operation is not None:
        if not isinstance(operation, str) or not OPERATION_KEY.fullmatch(operation) or len(operation) > 80:
            raise ValueError("An operation key is 1-80 lowercase letters, digits, and single hyphens, such as holdco-1099-bridge")
        origin["operation"] = operation            # absent keys keep earlier registrations' identifiers stable
    canonical = json.dumps({"document": document, "origin": origin}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    identifier = hashlib.sha256(canonical.encode()).hexdigest()
    root = Path(root) if root else inbox_directory()
    if document.get("response_fields"):
        from response_access import connection
        html = render(document, connection(root, identifier, viewer_url or os.environ.get("AGENT_STATUS_URL", "http://127.0.0.1:8766")))
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    destination = reports / identifier
    if destination.exists():
        return identifier
    manifest = {"version": 1, "id": identifier, "title": document["title"], "subject": document["subject"],
                "summary": document["summary"], "generated_at": document["generated_at"],
                "received_at": datetime.now(timezone.utc).isoformat(), "origin": origin,
                "response_field_count": len(document.get("response_fields", []))}
    if len(json.dumps(manifest, ensure_ascii=False).encode()) > 256 * 1024:
        raise ValueError("The report's title, summary, and origin metadata exceed the inbox record limit")
    staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=reports))
    try:
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")
        (staging / "report.json").write_text(json.dumps(document, ensure_ascii=False) + "\n", encoding="utf-8")
        (staging / "report.html").write_text(html, encoding="utf-8")
        try:
            staging.rename(destination)
        except OSError:
            if not destination.is_dir():
                raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return identifier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("--html", required=True, type=Path)
    parser.add_argument("--workspace", default=os.getcwd())
    parser.add_argument("--agent")
    parser.add_argument("--provider")
    parser.add_argument("--thread-id")
    parser.add_argument("--operation", help="Stable operation key shared by every version of one living report")
    parser.add_argument("--viewer-url", default=os.environ.get("AGENT_STATUS_URL", "http://127.0.0.1:8766"))
    arguments = parser.parse_args()
    document = json.loads(arguments.document.read_text())
    identifier = register(document, arguments.html.read_text(),
                          workspace=arguments.workspace, agent=arguments.agent, provider=arguments.provider,
                          thread_id=arguments.thread_id, viewer_url=arguments.viewer_url,
                          operation=arguments.operation)
    if document.get("response_fields"):
        from response_access import connection
        arguments.html.write_text(render(document, connection(inbox_directory(), identifier, arguments.viewer_url)), encoding="utf-8")
    print(identifier)


if __name__ == "__main__":
    main()

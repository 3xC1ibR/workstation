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

from build_status import validate


def inbox_directory():
    return Path(os.environ.get("AGENT_STATUS_INBOX", Path.home() / ".local/state/agent-status/inbox")).expanduser()


def register(document, html, *, workspace, agent=None, provider=None, thread_id=None, root=None):
    validate(document)
    if not isinstance(html, str) or not html.strip() or len(html.encode()) > 8 * 1024 * 1024:
        raise ValueError("A nonempty HTML report of at most 8 MB is required")
    origin = {"workspace": str(workspace), "agent": agent or None, "provider": provider or None,
              "thread_id": thread_id or None, "host": socket.gethostname()}
    canonical = json.dumps({"document": document, "origin": origin}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    identifier = hashlib.sha256(canonical.encode()).hexdigest()
    root = Path(root) if root else inbox_directory()
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
    arguments = parser.parse_args()
    identifier = register(json.loads(arguments.document.read_text()), arguments.html.read_text(),
                          workspace=arguments.workspace, agent=arguments.agent, provider=arguments.provider,
                          thread_id=arguments.thread_id)
    print(identifier)


if __name__ == "__main__":
    main()

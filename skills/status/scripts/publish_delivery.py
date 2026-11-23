#!/usr/bin/env python3
"""Publish unrequested work to the user's proactive feed on the review page."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from delivery_store import Deliveries, publish
from register_status import add_interactive_arguments, inbox_directory, interactive_arguments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path, help="JSON file: title, summary, and optional recommended_default, decision, category, links, thread, created_at")
    parser.add_argument("--document", type=Path, help="Markdown file with the full delivery, retained and shown in the page")
    parser.add_argument("--attach", type=Path, action="append", default=[], help="Text file retained with the delivery; repeat for each. "
                        "Relative links to its file name in the document open the retained copy.")
    parser.add_argument("--workspace", default=os.getcwd(), help="Workspace the work belongs to")
    parser.add_argument("--agent", help="Stable name of the producing agent")
    parser.add_argument("--provider", help="Producing provider, when known")
    parser.add_argument("--thread-id", default=os.environ.get("AGENT_COORD_SESSION_ID") or os.environ.get("CODEX_THREAD_ID"),
                        help="Ribbon Field conversation for discussion; defaults to the current conversation")
    parser.add_argument("--inbox", type=Path, default=inbox_directory())
    versions = parser.add_mutually_exclusive_group()
    versions.add_argument("--key", help="Stable key of a living delivery (lowercase letters, digits, hyphens); every delivery published "
                          "with it is a new version of the same delivery, and the user's responses stay with it")
    versions.add_argument("--replaces", metavar="DELIVERY-ID", help="Publish a new version of an existing delivery that has no key")
    add_interactive_arguments(parser)
    arguments = parser.parse_args()
    try:
        document = json.loads(arguments.delivery.read_text(encoding="utf-8"))
        body = arguments.document.read_text(encoding="utf-8") if arguments.document else None
        root = arguments.inbox.expanduser()
        identifier = publish(document, workspace=arguments.workspace, agent=arguments.agent, provider=arguments.provider,
                             thread_id=arguments.thread_id, body=body, attachments=arguments.attach, root=root,
                             key=arguments.key, replaces=arguments.replaces, **interactive_arguments(arguments, root))
        record = Deliveries(root).record(identifier)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    # `url` opens on every device and comes first when the service has a recorded tailnet address; `local_url` is the fallback on this Mac.
    from status_server import DEFAULT_PORT, saved_public_url
    result, public = {"delivery": identifier, "series": record["series"], "version_number": record["number"]}, saved_public_url(root)
    if public:
        result["url"] = f"{public}/deliveries/{identifier}"
    result["local_url"] = f"http://127.0.0.1:{DEFAULT_PORT}/deliveries/{identifier}"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

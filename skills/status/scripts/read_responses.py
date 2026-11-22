#!/usr/bin/env python3
"""Read saved Status responses as JSON without starting the viewer or marking them read."""
import argparse
import json
from pathlib import Path

from build_status import timestamp
from status_store import StatusReports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, help="Shared inbox directory (defaults to AGENT_STATUS_INBOX or the local inbox)")
    parser.add_argument("--report", help="Exact report ID printed by build_status.py")
    parser.add_argument("--workspace", help="Exact origin workspace")
    parser.add_argument("--agent", help="Exact stable agent name")
    parser.add_argument("--provider", help="Exact producing provider")
    parser.add_argument("--thread-id", help="Exact originating conversation ID")
    parser.add_argument("--since", help="Only answers saved after this timezone-aware ISO timestamp")
    args = parser.parse_args()
    if not any((args.report, args.workspace, args.agent, args.thread_id)):
        parser.error("Select --report, --workspace, --agent, or --thread-id to scope the responses.")
    reports = StatusReports(args.inbox)
    try:
        since = timestamp(args.since) if args.since else None
        listing = {"reports": [reports._manifest(args.report)], "unreadable": 0} if args.report else reports.list()
        results = []
        for report in listing["reports"]:
            if any(value is not None and report["origin"].get(key) != value for key, value in (
                    ("workspace", args.workspace), ("agent", args.agent), ("provider", args.provider), ("thread_id", args.thread_id))):
                continue
            if not args.report and not report.get("response_field_count"):
                continue
            response = reports.responses(report["id"])
            if since and (response["updated_at"] is None or timestamp(response["updated_at"]) <= since):
                continue
            results.append(response)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({"responses": results, "unreadable": listing["unreadable"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

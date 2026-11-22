#!/usr/bin/env python3
"""Read the user's saved responses as JSON without starting the service or marking them read.

By default the output covers answers to report response fields. With --deliveries
it covers the user's responses to proactive deliveries instead.
"""
import argparse
import json
from pathlib import Path

from build_status import timestamp
from delivery_store import Deliveries
from register_status import inbox_directory
from status_store import StatusReports


def read_deliveries(parser, args):
    """Print each selected delivery with the user's current response and the times of every response."""
    deliveries = Deliveries(args.inbox.expanduser() if args.inbox else inbox_directory())
    try:
        since = timestamp(args.since) if args.since else None
        listing = {"deliveries": [deliveries.record(args.delivery)], "unreadable": 0} if args.delivery else deliveries.list()
        results = []
        for delivery in listing["deliveries"]:
            if any(value is not None and delivery["origin"].get(key) != value for key, value in (
                    ("workspace", args.workspace), ("agent", args.agent), ("provider", args.provider), ("thread_id", args.thread_id))):
                continue
            changed = max((timestamp(event["at"]) for event in delivery["history"]), default=None)
            if since and (changed is None or changed <= since):
                continue
            results.append({key: delivery.get(key) for key in (
                "id", "title", "origin", "received_at", "status", "read_at", "response", "discussed_at", "history",
                "recommended_default", "decision")})
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({"deliveries": results, "unreadable": listing["unreadable"]}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, help="Shared inbox directory (defaults to AGENT_STATUS_INBOX or the local inbox)")
    parser.add_argument("--report", help="Exact report ID printed by build_status.py")
    parser.add_argument("--workspace", help="Exact origin workspace")
    parser.add_argument("--agent", help="Exact stable agent name")
    parser.add_argument("--provider", help="Exact producing provider")
    parser.add_argument("--thread-id", help="Exact originating conversation ID")
    parser.add_argument("--since", help="Only answers saved after this timezone-aware ISO timestamp")
    parser.add_argument("--deliveries", action="store_true", help="Read responses to proactive deliveries instead of report fields")
    parser.add_argument("--delivery", help="Exact delivery ID printed by publish_delivery.py; implies --deliveries")
    args = parser.parse_args()
    if not any((args.report, args.workspace, args.agent, args.thread_id, args.delivery)):
        parser.error("Select --report, --delivery, --workspace, --agent, or --thread-id to scope the responses.")
    if args.deliveries or args.delivery:
        if args.report:
            parser.error("--report selects a status report; use --delivery for a proactive delivery.")
        return read_deliveries(parser, args)
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

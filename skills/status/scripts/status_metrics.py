#!/usr/bin/env python3
"""Report how the review page is used: opens per day, delivery latency and outcomes, operation report opens."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from build_status import timestamp
from delivery_store import Deliveries
from register_status import inbox_directory
from status_store import StatusReports
from usage_events import UsageEvents, summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, default=inbox_directory())
    parser.add_argument("--days", type=int, default=7, help="Length of the period ending now or at --until (default 7)")
    parser.add_argument("--since", help="Period start, ISO 8601 with a timezone; overrides --days")
    parser.add_argument("--until", help="Period end, ISO 8601 with a timezone; defaults to now")
    parser.add_argument("--timezone", default="America/Chicago", help="Timezone used to assign page opens to days")
    arguments = parser.parse_args()
    try:
        until = timestamp(arguments.until) if arguments.until else datetime.now(timezone.utc)
        since = timestamp(arguments.since) if arguments.since else until - timedelta(days=arguments.days)
        if arguments.days < 1 or since >= until:
            raise ValueError("The period must cover at least one day and end after it starts.")
        root = arguments.inbox.expanduser()
        result = summarize(StatusReports(root), Deliveries(root), UsageEvents(root).read(since, until),
                           since=since, until=until, zone=ZoneInfo(arguments.timezone))
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

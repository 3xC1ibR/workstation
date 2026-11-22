"""Content-free usage measurement for the review page.

Events record when a page or item was opened and when a response was given.
They hold identifiers, view names and times only: no titles, summaries, notes
or answers. The metrics answer whether the page is used and whether proactive
work is read and acted on.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import statistics

from status_store import IDENTIFIER, StatusError, moment

EVENT_TYPES = {"page_open", "item_open", "response", "ask_resolution"}
VIEWS = {"review", "operation", "delivery"}
KINDS = {"operation", "delivery", "ask"}
ASK_IDENTIFIER = re.compile(r"[1-9][0-9]{0,17}\Z")         # Ribbon Field's own ask number; nothing about its content
IGNORED_AFTER = timedelta(hours=24)


class UsageEvents:
    def __init__(self, root):
        self.root = Path(root) / "usage"

    def record(self, kind, *, view=None, item_kind=None, item=None, action=None, narrow=None, remote=None, moment_=None):
        """Append one event. Invalid events are rejected rather than stored."""
        if kind not in EVENT_TYPES or (view is not None and view not in VIEWS):
            raise StatusError("Unsupported usage event.")
        pattern = ASK_IDENTIFIER if item_kind == "ask" else IDENTIFIER
        if (item_kind is None) != (item is None) or (item_kind is not None and (item_kind not in KINDS or not pattern.fullmatch(str(item)))):
            raise StatusError("A usage event item requires a kind and an identifier.")
        if (kind == "ask_resolution") != (item_kind == "ask") or (kind == "ask_resolution" and not action):
            raise StatusError("An ask resolution names the ask and the resolution.")
        if action is not None and (not isinstance(action, str) or not action.isidentifier() or len(action) > 32):
            raise StatusError("Unsupported usage event action.")
        now = moment_ or datetime.now(timezone.utc)
        event = {"at": now.isoformat(), "type": kind, "view": view, "item_kind": item_kind, "item": item,
                 "action": action, "narrow": narrow if type(narrow) is bool else None,
                 "remote": remote if type(remote) is bool else None}
        self.root.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.root / (now.strftime("%Y-%m") + ".jsonl"), os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as log:
            fcntl.flock(log, fcntl.LOCK_EX)
            log.write(json.dumps(event, separators=(",", ":")) + "\n")
        return event

    def read(self, since=None, until=None):
        events = []
        if self.root.exists():
            for path in sorted(self.root.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].jsonl")):
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        event = json.loads(line)
                        at = moment(event["at"])
                    except (ValueError, KeyError, TypeError):
                        continue                    # a torn final line never invalidates the log
                    if (since is None or at >= since) and (until is None or at < until):
                        events.append(event)
        return events


def median(values):
    return round(statistics.median(values), 1) if values else None


def summarize(reports, deliveries, events, *, since, until, zone):
    """Usage of the review page for deliveries and events inside [since, until)."""
    opens_per_day, operation_opens = {}, {}
    page_opens = [event for event in events if event["type"] == "page_open"]
    for event in page_opens:
        day = moment(event["at"]).astimezone(zone).date().isoformat()
        opens_per_day[day] = opens_per_day.get(day, 0) + 1
    operations = {operation["id"]: operation for operation in reports.operations()["operations"]}
    version_operation = {version["id"]: operation["id"] for operation in operations.values() for version in operation["versions"]}
    for event in events:
        if event["type"] == "item_open" and event.get("item_kind") == "operation":
            operation = version_operation.get(event["item"], event["item"])
            operation_opens[operation] = operation_opens.get(operation, 0) + 1
    delivered = [delivery for delivery in deliveries.list()["deliveries"] if since <= moment(delivery["received_at"]) < until]
    first_open, to_response, outcome = [], [], {"accepted": 0, "dismissed": 0, "discussed_only": 0, "ignored": 0, "pending": 0}
    for delivery in delivered:
        received = moment(delivery["received_at"])
        if delivery["read_at"]:
            first_open.append((moment(delivery["read_at"]) - received).total_seconds() / 60)
        responded = [moment(event["at"]) for event in delivery["history"] if event["action"] in {"accept", "dismiss", "discuss"}]
        if responded:
            to_response.append((min(responded) - received).total_seconds() / 60)
        if delivery["response"]:
            outcome[delivery["response"]["type"]] += 1
        elif delivery["discussed_at"]:
            outcome["discussed_only"] += 1
        else:
            outcome["ignored" if until - received >= IGNORED_AFTER else "pending"] += 1
    total = len(delivered)
    resolutions = [event for event in events if event["type"] == "ask_resolution"]
    by_resolution = {}
    for event in resolutions:
        by_resolution[event["action"]] = by_resolution.get(event["action"], 0) + 1
    share = lambda count: round(count / total, 3) if total else None
    days = max(1, (until - since).days)
    return {
        "period": {"since": since.isoformat(), "until": until.isoformat(), "timezone": str(zone)},
        "page_opens": {"total": len(page_opens), "per_day": dict(sorted(opens_per_day.items())),
                       "mean_per_day": round(len(page_opens) / days, 2),
                       "narrow_viewport": sum(1 for event in page_opens if event.get("narrow")),
                       "over_tailnet": sum(1 for event in page_opens if event.get("remote")),
                       "by_view": {view: sum(1 for event in page_opens if event.get("view") == view) for view in sorted(VIEWS)}},
        "proactive_deliveries": {
            "delivered": total, "opened": len(first_open),
            "median_minutes_to_first_open": median(first_open), "median_minutes_to_response": median(to_response),
            "counts": outcome, "share_acted_on": share(outcome["accepted"] + outcome["discussed_only"]),
            "share_accepted": share(outcome["accepted"]), "share_dismissed": share(outcome["dismissed"]),
            "share_ignored": share(outcome["ignored"]), "share_pending": share(outcome["pending"])},
        "asks_resolved_on_page": {
            "total": len(resolutions), "by_resolution": by_resolution,
            "narrow_viewport": sum(1 for event in resolutions if event.get("narrow"))},
        "operation_report_opens": sorted(
            ({"operation": identifier, "title": operations[identifier]["title"] if identifier in operations else None,
              "workspace": operations[identifier]["origin"].get("workspace") if identifier in operations else None,
              "opens": count} for identifier, count in operation_opens.items()), key=lambda row: -row["opens"]),
        "definitions": {
            "acted_on": "accepted, or discussed in the linked thread without another response",
            "ignored": "no acceptance, dismissal or discussion 24 hours or more after delivery, measured at the period end",
            "pending": "no response yet and delivered less than 24 hours before the period end",
            "response": "the first acceptance, dismissal or discussion; opening alone is counted under first open",
            "asks_resolved_on_page": "asks resolved or snoozed from this page through Ribbon Field; compare with "
                                     "'agent-coord ask --metrics', which counts every resolution wherever it was made"},
    }

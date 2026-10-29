#!/usr/bin/env python3
"""Read existing OKC records into a status document; no network or judge calls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from build_status import timestamp, validate


def collect(root, *, agent=None, problem=None, now=None):
    now = now or datetime.now(timezone.utc)
    notices = []
    sources = []

    def read(relative, *, lines=False):
        path = root / relative
        sources.append({"label": relative, "location": str(path)})
        try:
            content = path.read_text(encoding="utf-8")
            if not lines:
                result = json.loads(content)
                if not isinstance(result, dict):
                    raise ValueError("expected an object")
                return result
            records = []
            for number, line in enumerate(content.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError("expected an object")
                    timestamp(record["ts"])
                    records.append(record)
                except (ValueError, KeyError, TypeError):
                    notices.append({"title": "Incomplete evidence", "text": f"{relative}, line {number} is unreadable or lacks a valid timestamp. Counts and event coverage may be incomplete."})
            return sorted(records, key=lambda record: timestamp(record["ts"]))
        except (OSError, ValueError) as error:
            notices.append({"title": "Source unavailable", "text": f"{relative}: {error}. Missing data is not zero."})
            return [] if lines else {}

    snapshot = read("data/leaderboard/latest.json")
    experiments = read("ledger/experiments.jsonl", lines=True)
    ideas = read("ledger/ideas.jsonl", lines=True)
    observed = snapshot.get("taken_at")
    try:
        captured = timestamp(observed)
    except (ValueError, TypeError, AttributeError):
        captured, observed = None, None
    current_day = captured is not None and captured.astimezone(timezone.utc).date() == now.astimezone(timezone.utc).date()
    snapshot_old = captured is None or (now - captured).total_seconds() > 900
    if snapshot_old:
        notices.append({"title": "Last known observations", "text": "The saved leaderboard snapshot is older than 15 minutes or has no valid observation time. Rankings and quotas require a read-only source refresh before treating them as current."})
    if not current_day:
        notices.append({"title": "Today's allowance is unknown", "text": "The snapshot does not establish this UTC day's usage. Historical budget rows below do not show today's remaining trials."})

    def in_scope(record):
        return (not agent or record.get("agent") == agent) and (not problem or record.get("problem") == problem)

    completed = [r for r in experiments if in_scope(r) and r.get("status") == "done"
                 and not r.get("duplicate_of") and r.get("mode") in {"check", "submit"}]
    latest = completed[-1] if completed else None
    overall = snapshot.get("overall") or {}
    overall_rank = overall.get("our_rank")
    observed_fields = {"observed_at": observed} if observed else {}
    metrics = [{"label": "Overall kernel rank", "value": f'#{overall_rank} / {overall.get("entries", "unknown")}' if overall_rank else None,
                "detail": "Official overall kernel board; campaign-wide context.",
                "source": "data/leaderboard/latest.json · overall", "freshness_minutes": 15, **observed_fields}]
    if latest:
        event = timestamp(latest["ts"])
        elapsed = max(0, int((now - event).total_seconds() // 60))
        result = "passed" if latest.get("passed") is True else "failed" if latest.get("passed") is False else "outcome unknown"
        speedup = latest.get("speedup")
        speedup_text = f"{speedup:.4f}×" if isinstance(speedup, (int, float)) else "speedup unknown"
        metrics.append({"label": "Latest completed experiment", "value": f"{elapsed // 60}h {elapsed % 60}m ago",
                        "detail": f'{event.astimezone(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S %Z")} · {latest.get("problem")} · {latest.get("mode")} · {result} · {speedup_text}',
                        "source": f'ledger/experiments.jsonl · job {latest.get("job", "unknown")}', "observed_at": latest["ts"]})
    else:
        metrics.append({"label": "Latest completed experiment", "value": None,
                        "detail": "No completed, nonduplicate judge event found in the selected scope.", "source": "ledger/experiments.jsonl"})

    boards, limits = snapshot.get("problems") or {}, snapshot.get("limits") or {}
    selected = [problem] if problem else sorted(set(boards) | set(limits))
    standing_rows, budget_rows = [], []

    def value(value):
        return "Unknown" if value is None else str(value)

    for identifier in selected:
        board = boards.get(identifier) or {}
        standing_rows.append([identifier, value(board.get("our_rank")), value(board.get("entries")),
                              value(board.get("our_speedup")), value((board.get("speedup_at_rank") or {}).get("50"))])
        for mode in ("checks", "scored"):
            limit = (limits.get(identifier) or {}).get(mode) or {}
            budget_rows.append([identifier, mode, value(limit.get("used")), value(limit.get("per_day")), value(limit.get("left"))])

    sections = [
        {"title": "Official standing", "columns": ["Problem", "Rank", "Entries", "Scored speedup ×", "#50 speedup ×"],
         "rows": standing_rows, "source": "data/leaderboard/latest.json · problems", "freshness_minutes": 15, **observed_fields},
        {"title": "Daily trial usage" if current_day else "Historical trial usage",
         "text": f'Account allowance per problem, shared across agents. Accounting day: {captured.astimezone(timezone.utc).date() if captured else "unknown"}; resets at 00:00 UTC. An individual allocation is not established by this snapshot.',
         "columns": ["Problem", "Kind", "Used", "Allotted", "Remaining"], "rows": budget_rows,
         "source": "data/leaderboard/latest.json · limits", "freshness_minutes": 15, **observed_fields},
    ]
    if agent:
        today = [r for r in completed if timestamp(r["ts"]).astimezone(timezone.utc).date() == now.astimezone(timezone.utc).date()]
        sections.append({"title": "Agent activity", "text": "Recorded completed judge events today (UTC), not authoritative quota consumption or an allocation.",
                         "columns": ["Agent", "Checks", "Scored submissions"],
                         "rows": [[agent, str(sum(r["mode"] == "check" for r in today)), str(sum(r["mode"] == "submit" for r in today))]],
                         "source": "ledger/experiments.jsonl"})

    folded = {}
    for record in ideas:
        identifier = record.get("id")
        if record.get("type") == "idea" and identifier:
            folded[identifier] = dict(record)
        elif record.get("type") == "status" and identifier in folded:
            folded[identifier].update(status=record.get("status"), updated=record["ts"])
    candidates = [r for r in folded.values() if in_scope(r) and r.get("status") in {"proposed", "active"}]
    candidates.sort(key=lambda r: timestamp(r.get("updated", r["ts"])), reverse=True)
    sections.append({"title": "Recorded candidate work", "text": "Latest open ledger ideas, ordered by update time. These records do not establish priority or a current commitment.",
                     "columns": ["Idea", "Owner", "State", "Work"],
                     "rows": [[value(r.get("id")), value(r.get("agent")), value(r.get("status")), value(r.get("title"))] for r in candidates[:8]],
                     "source": "ledger/ideas.jsonl · folded status events"})
    report = {
        "title": "Open Kernel Challenge status", "subject": " / ".join(filter(None, [snapshot.get("team", "Team unknown"), agent or "campaign", problem])),
        "generated_at": now.isoformat(), "timezone": "America/Chicago",
        "summary": "Saved official standings, recorded experiments, and daily account allowances. The current plan requires review of recent decisions and the active conversation.",
        "notices": notices, "metrics": metrics, "sections": sections, "sources": sources,
        "actions": [{"action": "Confirm the next experiment from current decisions", "owner": agent or "campaign lead", "status": "recommended",
                     "reason": "The collector can identify open ideas, but cannot infer the owner's current plan or blockers from them.",
                     "source": "ledger/decisions.jsonl and active conversation require review"}],
    }
    validate(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--agent")
    parser.add_argument("--problem")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = collect(args.workspace.resolve(), agent=args.agent, problem=args.problem)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()

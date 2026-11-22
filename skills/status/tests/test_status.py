"""Verify reporting invariants: scope, accounting periods, disclosure, and escaping."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_status import render, validate
from collect_okc import collect


class ReportTests(unittest.TestCase):
    def document(self):
        return {"title": "Release status", "subject": "release-owner", "generated_at": "2026-10-29T05:00:00Z",
                "summary": "Current release has passed staging checks."}

    def test_unconfigured_material_information_is_visible_and_escaped(self):
        document = self.document()
        document["notices"] = [{"title": "New finding", "text": "Migration exceeds the release window."}]
        document["sections"] = [{"title": "Unrequested observation", "text": '<script>alert("x")</script>'}]
        document["sources"] = [{"label": "Untrusted address", "location": "javascript:alert(1)"}]
        document["metrics"] = [{"label": "Routine metric", "value": "18 / 18"}]
        output = render(document)
        self.assertLess(output.index("Current release has"), output.index("Migration exceeds"))     # assessment, then exceptions,
        self.assertLess(output.index("Migration exceeds"), output.index("Routine metric"))          # both before routine metrics
        self.assertIn("Unrequested observation", output)
        self.assertIn("&lt;script&gt;", output)
        self.assertNotIn("<script>", output)
        self.assertNotIn('href="javascript:', output)

    def test_fresh_generation_does_not_refresh_old_observations(self):
        document = self.document()
        document["metrics"] = [{"label": "Result", "value": "Passed", "observed_at": "2026-10-28T05:00:00Z", "freshness_minutes": 15},
                               {"label": "Unknown result", "value": None, "freshness_minutes": 15}]
        output = render(document)
        self.assertIn("Last known: refresh needed", output)
        self.assertIn("Observation time unknown", output)
        self.assertIn("Unknown", output)

    def test_invalid_data_fails_instead_of_silently_dropping_content(self):
        document = self.document()
        document["important_finding"] = "This must not disappear."
        with self.assertRaises(ValueError):
            validate(document)
        document.pop("important_finding")
        document["sections"] = [{"title": "Evidence", "columns": ["A", "B"], "rows": [["Missing B"]]}]
        with self.assertRaises(ValueError):
            validate(document)
        document.pop("sections")
        document["generated_at"] = "2026-10-29T05:00:00"
        with self.assertRaises(ValueError):
            validate(document)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "data/leaderboard").mkdir(parents=True)
        (self.root / "ledger").mkdir()
        self.now = datetime(2026, 10, 29, 0, 5, tzinfo=timezone.utc)
        self.snapshot = {"taken_at": "2026-10-29T00:04:00Z", "team": "example", "overall": {"our_rank": 2, "entries": 10},
                         "problems": {"kernel": {"our_rank": 3, "entries": 10}},
                         "limits": {"kernel": {"checks": {"used": 4, "per_day": 20, "left": 16}}}}
        self.write_snapshot()
        self.write_lines("ideas", [])
        self.write_lines("experiments", [])

    def write_snapshot(self):
        (self.root / "data/leaderboard/latest.json").write_text(json.dumps(self.snapshot))

    def write_lines(self, name, records):
        (self.root / "ledger" / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in records))

    def test_previous_day_allowance_is_historical_even_when_recent(self):
        self.snapshot["taken_at"] = "2026-10-28T23:59:00Z"
        self.write_snapshot()
        report = collect(self.root, now=self.now)
        self.assertIn("Today's allowance is unknown", [r["title"] for r in report["notices"]])
        budget = next(s for s in report["sections"] if s["title"] == "Historical trial usage")
        self.assertIn("2026-10-28", budget["text"])
        self.assertEqual(budget["rows"][0][2:], ["4", "20", "16"])

    def test_latest_event_scoped_sorted_and_not_duplicate(self):
        common = {"agent": "owner", "problem": "kernel", "mode": "check", "status": "done", "passed": False}
        self.write_lines("experiments", [dict(common, ts="2026-10-29T00:03:00Z", job="latest"),
                                         dict(common, ts="2026-10-29T00:02:00Z", job="older"),
                                         dict(common, ts="2026-10-29T00:04:00Z", job="duplicate", duplicate_of="latest"),
                                         dict(common, ts="2026-10-29T00:04:00Z", job="other-owner", agent="other")])
        report = collect(self.root, agent="owner", problem="kernel", now=self.now)
        latest = report["metrics"][1]
        self.assertTrue(latest["source"].endswith("job latest"))
        self.assertIn("failed", latest["detail"])
        budget = next(s for s in report["sections"] if s["title"] == "Daily trial usage")
        self.assertEqual(budget["rows"][0][2:], ["4", "20", "16"])
        activity = next(s for s in report["sections"] if s["title"] == "Agent activity")
        self.assertEqual(activity["rows"], [["owner", "2", "0"]])

    def test_status_events_preserve_idea_owner(self):
        self.write_lines("ideas", [{"ts": "2026-10-29T00:01:00Z", "type": "idea", "id": "idea-1", "agent": "owner", "status": "proposed", "title": "Measure memory traffic"},
                                   {"ts": "2026-10-29T00:02:00Z", "type": "status", "id": "idea-1", "agent": "lead", "status": "active"}])
        report = collect(self.root, agent="owner", now=self.now)
        candidates = next(s for s in report["sections"] if s["title"] == "Recorded candidate work")
        self.assertEqual(candidates["rows"][0][1:3], ["owner", "active"])

    def test_missing_and_partial_sources_are_not_zero(self):
        (self.root / "data/leaderboard/latest.json").unlink()
        (self.root / "ledger/experiments.jsonl").write_text('{"partial":')
        report = collect(self.root, now=self.now)
        titles = [n["title"] for n in report["notices"]]
        self.assertIn("Source unavailable", titles)
        self.assertIn("Incomplete evidence", titles)
        self.assertIsNone(report["metrics"][0]["value"])
        self.assertIsNone(report["metrics"][1]["value"])


if __name__ == "__main__":
    unittest.main()

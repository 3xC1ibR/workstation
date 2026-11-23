"""Visual blocks: validation, rendering, escaping, trends across versions, the review list, and the advisory checks."""
import copy
import json
import re
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_status import previous_versions, render, validate
from register_status import register
from report_checks import check
from status_store import StatusReports

EXAMPLE = Path(__file__).resolve().parents[1] / "references" / "briefing-example.json"


def base():
    return {"title": "Release", "subject": "release-owner", "generated_at": "2026-11-23T12:00:00Z", "summary": "Staging passed."}


class ValidationTests(unittest.TestCase):
    def test_the_example_is_valid_and_uses_every_block(self):
        document = json.loads(EXAMPLE.read_text())
        validate(document)
        for key in ("state", "needs_you", "changes", "phases", "timeline", "timeline_window", "workstreams", "charts"):
            self.assertIn(key, document)

    def test_invalid_blocks_are_refused_with_their_location(self):
        cases = [
            ({"state": {"level": "fine"}}, "state.level"),
            ({"needs_you": [{"action": "Approve", "due": "tomorrow"}]}, "needs_you[0].due"),
            ({"phases": [{"name": "Plan", "state": "started"}]}, "phases[0].state"),
            ({"timeline": [{"at": "2026-11-23T12:00:00", "title": "Check"}]}, "timezone"),
            ({"timeline": [{"at": "2026-11-23T12:00:00Z", "end": "2026-11-23T11:00:00Z", "title": "Window"}]}, "end must not precede"),
            ({"workstreams": [{"name": "Lane", "state": "green", "now": "x"}]}, "workstreams[0].state"),
            ({"charts": [{"title": "T", "kind": "pie", "series": [{"name": "a", "points": [["x", 1]]}]}]}, "kind"),
            ({"charts": [{"title": "T", "kind": "line", "series": [{"name": "a", "points": [["2026-11-23T12:00:00Z", 1], [3, 2]]}]}]}, "all timestamps"),
            ({"charts": [{"title": "T", "kind": "bar", "series": [{"name": "a", "points": [[1, 1]]}]}]}, "category"),
            ({"charts": [{"title": "T", "kind": "line", "series": [{"name": "a", "points": [[1, True]]}]}]}, "finite number"),
            ({"metrics": [{"label": "Revenue", "value": "$5", "target": 10}]}, "target needs current"),
            ({"changes": [{"text": "x", "direction": "up"}]}, "direction"),
            ({"unknown_block": []}, "unknown"),
        ]
        for extra, message in cases:
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(ValueError, re.escape(message)):
                    validate({**base(), **extra})

    def test_documents_without_blocks_render_as_before(self):
        output = render(base())
        for marker in ("sheet-state", "block-needs-you", "phases", "events", "workstreams", "plot"):
            self.assertNotIn(f'class="{marker}', output)


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(EXAMPLE.read_text())
        self.output = render(self.document)

    def test_the_four_questions_come_in_order(self):
        positions = [self.output.index(marker) for marker in
                     ('class="sheet-state"', 'class="assessment', 'id="block-needs-you"', 'class="block-changes"',
                      'class="block-phases"', 'class="block-timeline"', 'class="block-workstreams"', 'class="block-chart"')]
        self.assertEqual(positions, sorted(positions))

    def test_state_and_lane_words_carry_their_tone(self):
        self.assertIn('<span class="state-word tone-attention">At risk</span>', self.output)
        self.assertIn('<span class="state-word tone-critical">Blocked</span>', self.output)

    def test_needs_you_leads_with_the_deadline_and_time_left(self):
        self.assertIn('<span class="todo-due">By 12:30 PM, in 5 h</span>', self.output)
        overdue = {**base(), "needs_you": [{"action": "Sign", "due": "2026-11-23T10:00:00Z"}]}
        self.assertIn("Overdue since", render(overdue))

    def test_timeline_marks_the_present_between_past_and_future(self):
        events = self.output[self.output.index('<ol class="events">'):]
        self.assertLess(events.index("Lag above limit"), events.index("Now 7:30 AM"))
        self.assertLess(events.index("Now 7:30 AM"), events.index("Lag check"))
        self.assertIn('class="axis"', self.output)                      # a fixed window draws its axis
        without_window = copy.deepcopy(self.document)
        without_window.pop("timeline_window")
        self.assertNotIn('class="axis"', render(without_window))

    def test_many_past_events_fold_all_but_the_last_four(self):
        events = [{"at": f"2026-11-23T0{hour}:00:00Z", "title": f"Event {hour}"} for hour in range(10)]
        output = render({**base(), "timeline": events})
        self.assertIn("6 earlier events", output)

    def test_charts_draw_without_inline_styles_or_scripts_and_keep_their_data(self):
        self.assertIn('<svg class="plot"', self.output)
        self.assertIn('class="target"', self.output)
        self.assertIn("<summary>Data</summary>", self.output)
        self.assertNotIn(' style="', self.output)
        self.assertNotIn("<script", self.output)

    def test_missing_values_are_gaps_not_zero(self):
        chart = {"title": "T", "kind": "line", "series": [{"name": "a", "points": [[1, 1], [2, None], [3, 3]]}]}
        output = render({**base(), "charts": [chart]})
        self.assertEqual(output.count('<line class="series'), 0)          # neither segment touches the missing point
        self.assertIn("No value", output)

    def test_author_text_in_blocks_is_escaped(self):
        hostile = '<img src=x onerror=alert(1)>'
        document = {**base(), "state": {"level": "blocked", "label": hostile},
                    "needs_you": [{"action": hostile, "link": "javascript:alert(1)"}],
                    "workstreams": [{"name": hostile, "state": "on_track", "now": hostile}],
                    "charts": [{"title": hostile, "kind": "bar", "series": [{"name": hostile, "points": [[hostile, 1]]}]}]}
        output = render(document)
        self.assertNotIn("<img", output)
        self.assertNotIn('href="javascript:', output)


class VersionTests(unittest.TestCase):
    def test_measures_show_their_last_value_and_trend_across_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            for hour, revenue in ((8, 0), (10, 150)):
                document = {**base(), "generated_at": f"2026-11-23T{hour:02d}:00:00Z",
                            "metrics": [{"label": "Revenue", "value": f"${revenue}", "current": revenue, "target": 1000, "better": "higher"}]}
                register(document, render(document), workspace="/work", agent="lead", root=directory, operation="campaign")
            latest = {**base(), "metrics": [{"label": "Revenue", "value": "$400", "current": 400, "target": 1000, "better": "higher"}],
                      "changes": [{"text": "First sales", "direction": "better"}]}
            previous = previous_versions(latest, workspace="/work", agent="lead", operation="campaign", root=directory)
            self.assertEqual([version["generated_at"] for version in previous], ["2026-11-23T10:00:00Z", "2026-11-23T08:00:00Z"])
            output = render(latest, previous=previous)
            self.assertIn('<span class="metric-change tone-positive">Was $150</span>', output)
            self.assertIn('<svg class="sparkline"', output)
            self.assertIn("since Nov 23, 10:00 AM", output)
            self.assertEqual(previous_versions(latest, workspace="/work", agent="lead", operation="other", root=directory), [])

    def test_the_review_list_receives_state_and_actions_for_the_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            document = {**base(), "state": {"level": "blocked"}, "needs_you": [{"action": "Approve"}, {"action": "Sign"}]}
            register(document, render(document), workspace="/work", root=directory, operation="campaign")
            operation = StatusReports(directory).operations()["operations"][0]
            self.assertEqual((operation["state"], operation["needs_you_count"]), ("blocked", 2))
            plain = {**base(), "title": "Other"}
            register(plain, render(plain), workspace="/work", root=directory, operation="plain")
            other = next(o for o in StatusReports(directory).operations()["operations"] if o["title"] == "Other")
            self.assertEqual((other["state"], other["needs_you_count"]), (None, 0))


class CheckTests(unittest.TestCase):
    def test_the_example_passes_the_checks(self):
        self.assertEqual(check(json.loads(EXAMPLE.read_text()), operation=True), [])

    def test_a_wall_of_text_is_flagged(self):
        document = {**base(), "summary": " ".join(["word"] * 80) + " agent 01a205d9 at 09:00, 13:00 and 18:00",
                    "notices": [{"title": "Needs you: one list", "text": "Log in."}],
                    "metrics": [{"label": "Shots", "value": "0 / 20"}],
                    "sections": [{"title": "Pipeline", "columns": ["Lane", "Owner", "State"], "rows": [["a", "b", "c"]]}]}
        advice = " ".join(check(document, operation=True))
        for expected in ("summary has", "no state", "no timeline", "needs_you with", "raw identifiers", "current and target",
                         "use workstreams", "no changes", "neither needs_you nor actions"):
            self.assertIn(expected, advice)


if __name__ == "__main__":
    unittest.main()

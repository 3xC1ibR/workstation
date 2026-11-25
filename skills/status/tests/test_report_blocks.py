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
from report_checks import check, check_delivery
from status_store import StatusReports

EXAMPLE = Path(__file__).resolve().parents[1] / "references" / "briefing-example.json"


def base():
    return {"title": "Release", "subject": "release-owner", "generated_at": "2026-11-23T12:00:00Z", "summary": "Staging passed."}


class ValidationTests(unittest.TestCase):
    def test_the_example_is_valid_and_uses_every_block(self):
        document = json.loads(EXAMPLE.read_text())
        validate(document)
        for key in ("state", "decisions", "needs_you", "changes", "phases", "timeline", "timeline_window", "workstreams", "charts"):
            self.assertIn(key, document)

    def test_invalid_blocks_are_refused_with_their_location(self):
        cases = [
            ({"state": {"level": "fine"}}, "state.level"),
            ({"state": {"level": "on_track", "confidence": "sure"}}, "state.confidence"),
            ({"state": {"level": "on_track", "confidence_basis": "direct check"}}, "confidence_basis needs confidence"),
            ({"decisions": [{"question": "Q", "recommendation": "R", "why": "W", "reversibility": "maybe"}]}, "decisions[0].reversibility"),
            ({"decisions": [{"question": "Q", "recommendation": "R", "why": "W", "reversibility_note": "n"}]}, "reversibility_note needs reversibility"),
            ({"decisions": [{"question": "Q", "recommendation": "R", "why": "W", "confidence": "very"}]}, "decisions[0].confidence"),
            ({"decisions": [{"question": "Q", "recommendation": "R", "why": "W", "confidence_basis": "b"}]}, "confidence_basis needs confidence"),
            ({"decisions": [{"question": "Q", "recommendation": "R", "why": "W", "options": [{"label": "Only one"}]}]}, "2 to 6 options"),
            ({"decisions": [{"question": "Q", "recommendation": "R", "why": "W",
                             "options": [{"label": "A", "recommended": True}, {"label": "B", "recommended": True}]}]}, "at most one option"),
            ({"decisions": [{"question": "Q", "recommendation": "R", "why": "W", "assumptions": []}]}, "1 to 8 nonempty"),
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
        for marker in ("sheet-state", "state-confidence", "block-decisions", "block-needs-you", "phases", "events", "workstreams", "plot"):
            self.assertNotIn(f'class="{marker}', output)


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(EXAMPLE.read_text())
        self.output = render(self.document)

    def test_the_four_questions_come_in_order(self):
        positions = [self.output.index(marker) for marker in
                     ('class="sheet-state"', 'class="state-confidence"', 'class="assessment', 'id="block-decisions"',
                      'id="block-needs-you"', 'class="block-changes"', 'class="block-phases"', 'class="block-timeline"',
                      'class="block-workstreams"', 'class="block-chart"')]
        self.assertEqual(positions, sorted(positions))

    def test_state_and_lane_words_carry_their_tone(self):
        self.assertIn('<span class="state-word tone-attention">At risk</span>', self.output)
        self.assertIn('<span class="state-word tone-critical">Blocked</span>', self.output)
        self.assertIn('<span class="decision-flag tone-attention">Costly to reverse</span>', self.output)
        self.assertIn('<span class="tone-quiet">Moderate confidence</span>', self.output)

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
        document = {**base(), "state": {"level": "blocked", "label": hostile, "confidence": "low", "confidence_basis": hostile},
                    "decisions": [{"question": hostile, "recommendation": hostile, "why": hostile,
                                   "reversibility": "irreversible", "reversibility_note": hostile,
                                   "options": [{"label": hostile, "upside": hostile, "downside": hostile}, {"label": "Wait"}],
                                   "assumptions": [hostile], "if_wrong": hostile, "link": "javascript:alert(1)"}],
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
            self.assertIn(">Since Nov 23, 10:00 AM</h2>", output)
            self.assertEqual(previous_versions(latest, workspace="/work", agent="lead", operation="other", root=directory), [])

    def test_the_review_list_receives_state_and_actions_for_the_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            document = {**base(), "state": {"level": "blocked"},
                        "decisions": [{"question": "Choose plan", "recommendation": "Plan A", "why": "Cheaper"}],
                        "needs_you": [{"action": "Approve"}, {"action": "Sign"}]}
            register(document, render(document), workspace="/work", root=directory, operation="campaign")
            operation = StatusReports(directory).operations()["operations"][0]
            self.assertEqual((operation["state"], operation["decision_count"], operation["needs_you_count"]), ("blocked", 1, 2))
            plain = {**base(), "title": "Other"}
            register(plain, render(plain), workspace="/work", root=directory, operation="plain")
            other = next(o for o in StatusReports(directory).operations()["operations"] if o["title"] == "Other")
            self.assertEqual((other["state"], other["decision_count"], other["needs_you_count"]), (None, 0, 0))


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
                         "use workstreams", "no changes", "neither decisions, needs_you, nor actions"):
            self.assertIn(expected, advice)

    def test_decision_packet_report_checks(self):
        document = {**base(), "state": {"level": "blocked"},
                    "changes": [{"text": "Stripe acct_1UeSj5Gj26oDTVCY verified (, nonmember)"}],
                    "needs_you": [{"action": "Choose an imprint address"}]}
        advice = " ".join(check(document, operation=True))
        self.assertIn("acct_1UeSj5Gj26oDTVCY", advice)
        self.assertIn("missing dollar amount", advice)
        self.assertIn("needs_you asks the reader to decide", advice)

        irreversible = {**base(), "state": {"level": "at_risk"},
                        "decisions": [{"question": "Delete stack?", "recommendation": "Delete", "why": "Unused",
                                       "reversibility": "irreversible"}]}
        advice2 = " ".join(check(irreversible))
        self.assertIn("has no options", advice2)
        self.assertIn("missing reversibility or confidence", advice2)
        self.assertIn("marked irreversible", advice2)

    def test_delivery_checks_catch_live_failure_modes(self):
        bad = {
            "title": "AWS cleanup",
            "summary": " ".join(["cost"] * 90) + " on acct_1UeSj5Gj26oDTVCY for  pilot",
            "recommended_default": "Execute safe bundle + stop com.rquinonez.ribbon-field-tunnel",
            "decision": {
                "question": "Approve?",
                "options": ["Execute safe bundle and stop com.rquinonez.ribbon-field-tunnel", "Hold"],
            },
        }
        body = "We audited AWS.\n\nReply \"bundle\" to approve 1-6."
        advice = " ".join(check_delivery(bad, body=body))
        for expected in ("summary has", "duplicates recommended_default", "without reversibility or confidence",
                         "acct_1UeSj5Gj26oDTVCY", "missing dollar amount", "chat-reply instructions",
                         "com.rquinonez.ribbon-field-tunnel"):
            self.assertIn(expected, advice)

        clean = {
            "title": "Cut AWS bill 29%",
            "summary": "Live audit found $44/mo in verified idle resources.",
            "recommended_default": "Clean up the 5 verified idle resources and add a $100 budget alert.",
            "decision": {"question": "Approve the 5-item cleanup or include Datadog too?",
                         "options": ["Include Datadog deletion too (saves $56/mo)", "Hold"]},
            "reversibility": "costly",
            "confidence": "high",
        }
        self.assertEqual(check_delivery(clean, body="## Options\n\nAll 5 resources listed."), [])


if __name__ == "__main__":
    unittest.main()

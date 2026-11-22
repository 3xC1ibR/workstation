import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import read_context as reader


# Public system edition. Exercise the same routing table used by the installed skill.
EVENT_RULE = (
    "When implementing an event listener, initialize a new cursor from after=latest and save it. "
    "Preserve an existing cursor on restart. Save each subsequent cursor only after handling its events, "
    "deduplicate by event ID, drain remaining pages and read the current job before acting on old events."
)
HEADING = "## Source writes and tool use"


class ContextReaderTests(unittest.TestCase):
    def test_owner_addition_under_a_deferred_heading(self):
        addition = "Ask me before subscribing to a new feed."
        document = "\n\n".join([HEADING, EVENT_RULE, addition])
        startup = reader.select_instructions(document, set())
        self.assertNotIn(EVENT_RULE, startup)
        self.assertIn(addition, startup)
        self.assertIn("events —", startup)
        selected = reader.select_instructions(document, {"events"})
        self.assertIn(EVENT_RULE, selected)
        self.assertIn(addition, selected)

    def test_reworded_or_relocated_instruction_is_always_visible(self):
        changed = EVENT_RULE.replace("after=latest", "a specified event")
        for heading, rule in [(HEADING, changed), ("## All requests", EVENT_RULE)]:
            document = heading + "\n\n" + rule
            for topics in [set(), {"events"}, {"memory"}]:
                with self.subTest(heading=heading, topics=topics):
                    self.assertIn(document, reader.select_instructions(document, topics))

    def test_deduplication_preserves_distinct_context_and_snapshot_metadata(self):
        brief = "A two-line\nshared brief."
        snapshot = {"content": brief, "revision": "r1"}
        for rendered in ["Context before\n" + brief + "\nContext after", "A different snapshot."]:
            sections = {"long_term_memory": rendered, "new_field": "Keep this detail."}
            bundle = {
                "context": "<context_sections>\n" + json.dumps(sections) + "\n</context_sections>",
                "long_term_memory": snapshot,
                "llm_directives": "Prefer exact dates.",
                "conversation_context": "A pending question.",
            }
            result = json.loads(reader.display_context(bundle))
            displayed = result["context"]["long_term_memory"]
            restored = displayed.replace("[see long_term_memory.content]", brief)
            self.assertEqual(restored, rendered)
            self.assertNotIn(brief, displayed)
            expected_sections = {**sections, "long_term_memory": displayed}
            self.assertEqual(result, {**bundle, "context": expected_sections})
        future = {"context": "Another format", "long_term_memory": snapshot}
        self.assertEqual(json.loads(reader.display_context(future)), future)

    def test_api_lookup_rejects_ambiguous_titles(self):
        guide = "# API\n\n## Jobs\n\nRead jobs.\n\n## Jobs and events\n\nRead events."
        self.assertEqual(reader.guide_section(guide, None), "Jobs\nJobs and events")
        self.assertEqual(reader.guide_section(guide, "jobs"), "## Jobs\n\nRead jobs.")
        self.assertEqual(reader.guide_section(guide, "events"), "## Jobs and events\n\nRead events.")
        with self.assertRaises(ValueError):
            reader.guide_section(guide, "job")


if __name__ == "__main__":
    unittest.main()

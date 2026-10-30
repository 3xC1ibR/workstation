from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from register_status import register


class InboxRegistrationTests(unittest.TestCase):
    def test_builder_delivers_by_default_and_preview_does_not_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "status.json"
            document.write_text(json.dumps({"title": "Status", "subject": "Agent", "summary": "Completed",
                                            "generated_at": "2026-10-30T10:00:00Z"}))
            command = [sys.executable, "-B", str(Path(__file__).resolve().parents[1] / "scripts/build_status.py"),
                       str(document), "--output", str(root / "status.html"), "--workspace", "/project",
                       "--agent", "project-owner", "--provider", "codex", "--thread-id", "example-thread"]
            environment = dict(os.environ, AGENT_STATUS_INBOX=str(root / "inbox"))
            subprocess.run([*command, "--no-register"], env=environment, check=True, capture_output=True)
            self.assertTrue((root / "status.html").is_file())
            self.assertFalse((root / "inbox").exists())
            result = subprocess.run(command, env=environment, check=True, capture_output=True, text=True)
            self.assertIn("Status inbox receipt:", result.stdout)
            reports = list((root / "inbox/reports").iterdir())
            self.assertEqual(len(reports), 1)
            manifest = json.loads((reports[0] / "manifest.json").read_text())
            self.assertEqual(manifest["origin"]["thread_id"], "example-thread")
            self.assertEqual((reports[0] / "report.html").read_text(), (root / "status.html").read_text())

    def test_retry_is_idempotent_and_new_report_preserves_dismissed_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = {"title": "Status", "subject": "Agent", "summary": "Completed", "generated_at": "2026-10-30T10:00:00Z"}
            identifier = register(document, "<h1>First</h1>", workspace="/project", root=root)
            (root / "dismissed").mkdir()
            dismissal = root / "dismissed" / (identifier + ".json")
            dismissal.write_text('{"dismissed_at":"2026-10-30T11:00:00Z"}')
            self.assertEqual(register(document, "<h1>Retry</h1>", workspace="/project", root=root), identifier)
            self.assertEqual((root / "reports" / identifier / "report.html").read_text(), "<h1>First</h1>")
            document["generated_at"] = "2026-10-30T12:00:00Z"
            next_identifier = register(document, "<h1>Second</h1>", workspace="/project", root=root)
            self.assertNotEqual(identifier, next_identifier)
            self.assertTrue(dismissal.exists())
            self.assertFalse((root / "dismissed" / (next_identifier + ".json")).exists())

    def test_different_origins_remain_distinct_and_metadata_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = {"title": "Status", "subject": "Agent", "summary": "Completed", "generated_at": datetime.now(timezone.utc).isoformat()}
            first = register(document, "<h1>Result</h1>", workspace="/one", agent="owner-a", provider="codex", root=root)
            second = register(document, "<h1>Result</h1>", workspace="/two", agent="owner-b", provider="claude", root=root)
            self.assertNotEqual(first, second)
            manifest = json.loads((root / "reports" / second / "manifest.json").read_text())
            self.assertEqual(manifest["origin"]["provider"], "claude")
            self.assertEqual(manifest["origin"]["workspace"], "/two")
            self.assertEqual(len(list((root / "reports").iterdir())), 2)

"""Check text bounds and one-call submission without accessing printer hardware."""

from contextlib import redirect_stderr
from datetime import datetime, timezone
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/print_status.py"
SPECIFICATION = importlib.util.spec_from_file_location("print_status", SCRIPT)
status = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(status)


class PrintedStatusTests(unittest.TestCase):
    def test_receipt_preserves_information_and_wraps_native_text(self):
        update = (
            "Result: verification completed. "
            "Blocker: deployment approval is pending. "
            "Next: the release owner reviews the changes."
        )
        generated_at = datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc)
        receipt = status.prepare_receipt(update, "Workstation", generated_at)
        self.assertIn("2026-11-01 18:00 UTC", receipt)
        self.assertIn(update, " ".join(receipt.splitlines()[3:]))
        self.assertTrue(all(len(line) <= 48 for line in receipt.splitlines()))
        self.assertLessEqual(len(receipt.splitlines()), status.MAXIMUM_LINES)

    def test_rejects_invalid_updates_before_calling_printer(self):
        for update in ("", " \n ", "Status\x1b@", "Status \U0001f642", "Detail\n" * 26):
            with self.subTest(update=repr(update)):
                with patch.object(status.subprocess, "run") as submit:
                    with redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as error:
                            status.main(["--text", update])
                    self.assertEqual(error.exception.code, 2)
                    submit.assert_not_called()

    def test_subject_cannot_inject_additional_lines(self):
        for subject in ("", "Project\nInjected", "Project\rInjected", "x" * 48):
            with self.subTest(subject=repr(subject)):
                with self.assertRaises(ValueError):
                    status.prepare_receipt("Result: ready.", subject)

    def test_typographic_punctuation_uses_printer_normalization(self):
        receipt = status.prepare_receipt("Result: review complete\u2014next is deployment\u2026")
        self.assertIn("complete--next", receipt)
        self.assertIn("deployment...", receipt)
        receipt.encode("cp437")

    def test_normal_request_submits_exactly_once(self):
        with patch.object(status.subprocess, "run") as submit:
            submit.return_value = subprocess.CompletedProcess([], 0)
            self.assertEqual(status.main(["--text", "Result: ready."]), 0)
        submit.assert_called_once()
        self.assertIn("--submit", submit.call_args.args[0])

    def test_preview_prepares_without_submission_flag(self):
        with patch.object(status.subprocess, "run") as submit:
            submit.return_value = subprocess.CompletedProcess([], 0)
            self.assertEqual(status.main(["--preview", "--text", "Result: ready."]), 0)
        submit.assert_called_once()
        self.assertNotIn("--submit", submit.call_args.args[0])

    def test_stdin_needs_no_intermediate_file(self):
        with patch.object(status.sys, "stdin", io.StringIO("Result: ready.")):
            with patch.object(status.subprocess, "run") as submit:
                submit.return_value = subprocess.CompletedProcess([], 0)
                self.assertEqual(status.main([]), 0)
        self.assertIn("Result: ready.", submit.call_args.args[0][2])

    def test_helper_failure_is_returned_without_retry(self):
        with patch.object(status.subprocess, "run") as submit:
            submit.return_value = subprocess.CompletedProcess([], 1)
            self.assertEqual(status.main(["--text", "Result: ready."]), 1)
        submit.assert_called_once()


if __name__ == "__main__":
    unittest.main()

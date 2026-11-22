import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ribbon_field_asks import resolve_ask  # noqa: E402

ADDRESS = "http://127.0.0.1:57523/"


class RecordingOpener:
    def __init__(self, failure=None):
        self.requests, self.failure = [], failure

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if request.full_url.endswith("api/browser/config"):
            return io.BytesIO(json.dumps({"token": "csrf-token"}).encode())
        if self.failure:
            raise self.failure
        return io.BytesIO(json.dumps({"id": 7, "status": "resolved"}).encode())


class ResolveAskTests(unittest.TestCase):
    def test_forwards_resolution_with_ribbon_field_token(self):
        opener = RecordingOpener()
        result = resolve_ask(7, {"resolution": "done", "note": "Uploaded"}, address=ADDRESS, opener=opener)
        self.assertEqual(result["status"], "resolved")
        post = opener.requests[1]
        self.assertEqual(post.full_url, ADDRESS + "api/browser/asks/7")
        self.assertEqual(post.get_method(), "POST")
        self.assertEqual(post.get_header("X-agent-coord-token"), "csrf-token")
        self.assertEqual(json.loads(post.data), {"resolution": "done", "note": "Uploaded"})

    def test_snooze_uses_snooze_endpoint_and_only_until(self):
        opener = RecordingOpener()
        resolve_ask(7, {"until": 1795400000}, snooze=True, address=ADDRESS, opener=opener)
        self.assertEqual(opener.requests[1].full_url, ADDRESS + "api/browser/asks/7/snooze")
        with self.assertRaises(ValueError):
            resolve_ask(7, {"resolution": "done"}, snooze=True, address=ADDRESS, opener=RecordingOpener())

    def test_rejects_invalid_identifiers_and_fields(self):
        for ask_id in (0, -1, True, "7"):
            with self.assertRaises(ValueError):
                resolve_ask(ask_id, {"resolution": "done"}, address=ADDRESS, opener=RecordingOpener())
        with self.assertRaises(ValueError):
            resolve_ask(7, {"resolution": "done", "session_id": "x"}, address=ADDRESS, opener=RecordingOpener())

    def test_reports_ribbon_field_refusal(self):
        failure = urllib.error.HTTPError(ADDRESS, 409, "Conflict", {}, io.BytesIO(b'{"error": "Ask 7 is already resolved."}'))
        with self.assertRaisesRegex(ValueError, "already resolved"):
            resolve_ask(7, {"resolution": "done"}, address=ADDRESS, opener=RecordingOpener(failure))


if __name__ == "__main__":
    unittest.main()

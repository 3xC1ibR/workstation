"""Exercise the user-to-agent response contract across storage, HTTP, and CLI."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from build_status import render, validate
from register_status import register
from status_server import make_server
from status_store import ResponseConflict, StatusError, StatusReports


def document():
    return {"title": "Release status", "subject": "release-owner", "generated_at": "2026-11-21T18:00:00Z",
            "summary": "Choose the next action.", "response_fields": [
                {"id": "instructions", "label": "Instructions <agent>", "type": "multiline"},
                {"id": "owner", "label": "Responsible person", "type": "text"},
                {"id": "limit", "label": "Trial limit", "type": "number"},
                {"id": "proceed", "label": "Proceed?", "type": "boolean", "required": True},
                {"id": "window", "label": "Release window", "type": "choice", "options": ["Monday", "Defer"]}]}


class ResponseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.document = document()
        self.identifier = register(self.document, render(self.document), workspace="/project-one", agent="release-owner",
                                   provider="codex", thread_id="thread-one", root=self.root)
        self.reports = StatusReports(self.root)

    def test_user_answers_survive_restart_dismissal_and_reregistration(self):
        initial = self.reports.responses(self.identifier)
        self.assertEqual((initial["revision"], initial["values"], initial["updated_at"]), (0, {}, None))
        values = {"instructions": "Preserve the trial budget.\nCheck staging.", "proceed": False, "limit": 0, "window": "Defer"}
        saved = self.reports.save_responses(self.identifier, values, 0)
        self.assertEqual(saved["revision"], 1)
        self.assertTrue(saved["updated_at"])
        self.reports.dismiss(self.identifier, True)
        identifier = register(self.document, render(self.document), workspace="/project-one", agent="release-owner",
                              provider="codex", thread_id="thread-one", root=self.root)
        self.assertEqual(identifier, self.identifier)
        self.assertEqual(StatusReports(self.root).responses(identifier)["values"], values)
        self.document["generated_at"] = "2026-11-21T19:00:00Z"
        later = register(self.document, render(self.document), workspace="/project-one", agent="release-owner", root=self.root)
        self.assertEqual(self.reports.responses(later)["values"], {})
        self.assertEqual(self.reports.save_responses(identifier, {"proceed": True}, 1)["values"], {"proceed": True})

    def test_invalid_answers_cannot_overwrite_saved_values(self):
        invalid = [{}, {"proceed": "false"}, {"proceed": False, "limit": True},
                   {"proceed": False, "limit": float("nan")}, {"proceed": False, "limit": 10**1000},
                   {"proceed": False, "window": "Friday"}, {"proceed": False, "foreign": "value"},
                   {"proceed": False, "instructions": "é" * 10001}, []]
        for values in invalid:
            with self.subTest(values=str(values)[:80]), self.assertRaises(ValueError):
                self.reports.save_responses(self.identifier, values, 0)
            self.assertEqual(self.reports.responses(self.identifier)["revision"], 0)
        for revision in (True, -1, "0"):
            with self.assertRaises(ValueError):
                self.reports.save_responses(self.identifier, {"proceed": True}, revision)

    def test_competing_writers_cannot_silently_overwrite_answers(self):
        def save(index):
            try:
                return self.reports.save_responses(self.identifier, {"proceed": True, "limit": index}, 0)["values"]
            except ResponseConflict:
                return None
        with ThreadPoolExecutor(max_workers=10) as workers:
            results = list(workers.map(save, range(10)))
        successes = [result for result in results if result is not None]
        self.assertEqual(len(successes), 1)
        self.assertEqual(self.reports.responses(self.identifier)["values"], successes[0])

    def test_corrupt_and_symlinked_answers_are_not_treated_as_unanswered(self):
        self.reports.save_responses(self.identifier, {"proceed": False}, 0)
        response = self.root / "responses" / (self.identifier + ".json")
        response.write_text('{"partial":')
        with self.assertRaises(StatusError):
            self.reports.responses(self.identifier)
        response.unlink()
        response.symlink_to(self.root / "reports" / self.identifier / "report.json")
        with self.assertRaises(StatusError):
            self.reports.save_responses(self.identifier, {"proceed": True}, 0)

    def test_agent_cli_scopes_origin_and_reads_answers_without_viewer(self):
        self.reports.save_responses(self.identifier, {"proceed": False, "limit": 0}, 0)
        command = [sys.executable, "-B", str(SCRIPTS / "read_responses.py"), "--inbox", str(self.root)]
        def read(*arguments):
            return json.loads(subprocess.check_output(command + list(arguments), text=True))
        answers = read("--workspace", "/project-one", "--agent", "release-owner", "--thread-id", "thread-one")["responses"]
        self.assertEqual(answers[0]["values"], {"proceed": False, "limit": 0})
        self.assertEqual(read("--report", self.identifier, "--agent", "other-agent")["responses"], [])
        self.assertEqual(read("--thread-id", "thread-one", "--since", "2099-01-01T00:00:00Z")["responses"], [])
        self.assertEqual(read("--report", self.identifier)["responses"][0]["fields"], self.document["response_fields"])
        failure = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(failure.returncode, 0)

    def test_field_schema_rejects_ambiguous_definitions_and_snapshot_stays_inert(self):
        for fields in ([{"id": "name", "label": "Name", "type": "unsupported"}],
                       [{"id": "../name", "label": "Name", "type": "text"}],
                       [{"id": "name", "label": "Name", "type": "choice", "options": ["A", "A"]}],
                       [{"id": "name", "label": "Name", "type": "text", "required": "true"}],
                       [self.document["response_fields"][0]] * 2):
            with self.assertRaises(ValueError):
                validate({**self.document, "response_fields": fields})
        snapshot = render(self.document)
        self.assertIn("Instructions &lt;agent&gt;", snapshot)
        self.assertNotIn("<script", snapshot)
        self.assertNotIn("<input", snapshot)

    def test_http_save_requires_origin_token_and_revision(self):
        server = make_server(self.root, 0)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f"http://127.0.0.1:{server.server_port}"
        def request(path, body=None, headers=None):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request("GET" if body is None else "POST", path,
                                   body=None if body is None else json.dumps(body), headers=headers or {})
                response = connection.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                connection.close()
        token = json.loads(request("/api/config")[2])["token"]
        headers = {"Origin": origin, "X-Status-Token": token, "Content-Type": "application/json"}
        body = {"id": self.identifier, "revision": 0, "values": {"proceed": False, "limit": 0}}
        for changed in ({"Origin": "https://elsewhere.invalid"}, {"X-Status-Token": ""}, {"Host": "elsewhere.invalid"}):
            self.assertEqual(request("/api/responses", body, {**headers, **changed})[0], 403)
        self.assertEqual(request("/api/responses/" + self.identifier)[0], 200)
        self.assertEqual(request("/api/responses", body, headers)[0], 200)
        self.assertEqual(request("/api/responses", body, headers)[0], 409)
        self.assertEqual(request("/api/responses", {**body, "revision": 1, "values": {}}, headers)[0], 400)
        result = json.loads(request("/api/responses/" + self.identifier)[2])
        self.assertEqual(result["values"], body["values"])
        self.assertEqual(request("/api/responses/../private")[0], 404)
        self.assertEqual(request("/responses.js")[0], 200)
        self.assertNotIn("allow-scripts", request("/reports/" + self.identifier)[1]["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()

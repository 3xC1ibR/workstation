from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from register_status import register
from status_store import StatusReports, StatusError
from status_server import make_server

def publish(root, identifier="a" * 64, workspace="/project-one", provider="codex"):
    directory = root / "reports" / identifier
    directory.mkdir(parents=True)
    manifest = {"version": 1, "id": identifier, "title": "Status", "subject": "Worker", "summary": "Complete",
                "generated_at": "2026-10-30T10:00:00Z", "received_at": "2026-10-30T10:01:00Z",
                "origin": {"workspace": workspace, "agent": "owner", "provider": provider, "host": "machine"}}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    (directory / "report.html").write_text('<h1>Retained report</h1><script>parent.compromised=true</script>')
    return identifier


class StatusReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.reports = StatusReports(self.root)

    def test_all_origins_and_persistent_dismissal_without_deleting_content(self):
        first = publish(self.root)
        second = publish(self.root, "b" * 64, "/project-two", "claude")
        self.assertEqual(len(self.reports.list()["reports"]), 2)
        self.reports.dismiss(first, True)
        reopened = StatusReports(self.root)
        records = {report["id"]: report for report in reopened.list()["reports"]}
        self.assertTrue(records[first]["dismissed_at"])
        self.assertIsNone(records[second]["dismissed_at"])
        self.assertIn("Retained report", reopened.content(first))
        reopened.dismiss(first, False)
        self.assertIsNone(reopened._manifest(first)["dismissed_at"])

    def test_new_report_from_dismissed_agent_is_visible_and_partial_records_are_ignored(self):
        first = publish(self.root)
        self.reports.dismiss(first, True)
        next_identifier = publish(self.root, "b" * 64)
        (self.root / "reports" / ".pending-test").mkdir()
        (self.root / "reports" / ("c" * 64)).mkdir()
        result = self.reports.list()
        self.assertEqual(result["unreadable"], 1)
        self.assertEqual([report["id"] for report in result["reports"] if not report["dismissed_at"]], [next_identifier])

    def test_traversal_symlinks_and_special_files_are_not_served(self):
        identifier = publish(self.root)
        for value in ("../private", "", "a" * 65, []):
            with self.subTest(value=value), self.assertRaises(StatusError):
                self.reports.content(value)
        report = self.root / "reports" / identifier / "report.html"
        report.unlink()
        secret = self.root / "private.txt"
        secret.write_text("private")
        report.symlink_to(secret)
        with self.assertRaises(StatusError):
            self.reports.content(identifier)
        report.unlink()
        os.mkfifo(report)
        with self.assertRaises(StatusError):
            self.reports.content(identifier)

    def test_ten_agents_publish_without_an_application(self):
        def generate(index):
            document = {"title": f"Agent {index}", "subject": "Campaign", "summary": "Experiment completed",
                        "generated_at": "2026-10-30T10:00:00Z"}
            return register(document, "<h1>Standalone sheet</h1>", workspace=f"/project-{index}",
                            agent=f"agent-{index}", provider="claude" if index % 2 else "codex", root=self.root)
        with ThreadPoolExecutor(max_workers=10) as workers:
            identifiers = list(workers.map(generate, range(10)))
        self.assertEqual(len(set(identifiers)), 10)
        self.assertEqual(len(self.reports.list()["reports"]), 10)
        self.reports.dismiss(identifiers[0], True)
        self.assertEqual(generate(0), identifiers[0])
        self.assertTrue(self.reports._manifest(identifiers[0])["dismissed_at"])


class StatusServerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.identifier = publish(self.root)
        self.server = make_server(self.root, 0)
        worker = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
        self.token = json.loads(self.request("/api/config")[2])["token"]

    def request(self, path, body=None, *, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            actual = {"Content-Type": "application/json", "Origin": getattr(self, "origin", ""),
                      "X-Status-Token": getattr(self, "token", "")}
            actual.update(headers or {})
            connection.request("GET" if body is None else "POST", path, body=None if body is None else json.dumps(body), headers=actual)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_collection_and_reports_are_served_without_coordination_runtime(self):
        for path in ("/", "/style.css", "/review.css", "/review.js", "/report_page.js", "/delivery.js", "/api/reports",
                     "/api/review", "/health"):
            self.assertEqual(self.request(path)[0], 200)
        self.assertEqual(json.loads(self.request("/api/reports")[2])["reports"][0]["id"], self.identifier)
        self.assertEqual(self.request("/style.css")[2], (Path(__file__).resolve().parents[1] / "assets/style.css").read_bytes())
        status, headers, content = self.request("/reports/" + self.identifier)
        self.assertEqual(status, 200)
        self.assertIn(b"Retained report", content)
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        self.assertNotIn("allow-scripts", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(self.request("/../../private")[0], 404)

    def test_dismissal_requires_local_origin_and_token_and_is_reversible(self):
        body = {"id": self.identifier, "dismissed": True}
        for headers in ({"X-Status-Token": ""}, {"Origin": "https://elsewhere.invalid"}, {"Host": "elsewhere.invalid"}):
            self.assertEqual(self.request("/api/dismiss", body, headers=headers)[0], 403)
        self.assertEqual(self.request("/api/dismiss", body)[0], 200)
        self.assertTrue(StatusReports(self.root)._manifest(self.identifier)["dismissed_at"])
        self.assertEqual(self.request("/api/dismiss", {**body, "dismissed": "false"})[0], 400)
        self.assertEqual(self.request("/api/dismiss", {**body, "dismissed": False})[0], 200)
        self.assertIsNone(StatusReports(self.root)._manifest(self.identifier)["dismissed_at"])

    def test_foreign_hosts_and_unexpected_payloads_are_rejected(self):
        self.assertEqual(self.request("/api/config", headers={"Host": "untrusted.invalid"})[0], 403)
        for body in ([], {"id": self.identifier}, {"id": self.identifier, "dismissed": False, "extra": True}):
            self.assertEqual(self.request("/api/dismiss", body)[0], 400)

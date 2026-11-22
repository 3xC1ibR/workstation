"""Operations, proactive deliveries and their versions, interactive documents, links, asks, public address handling, and usage metrics."""
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from build_status import render
import delivery_store
from delivery_store import Deliveries
from document_state import DocumentStates
import interactive_documents
import markdown_text
from register_status import register
from ribbon_field_asks import AskReader, for_operation, read_asks, title_and_detail
from status_server import make_server, public_address
from status_store import ResponseConflict, StatusError, StatusReports
from usage_events import UsageEvents, summarize

PUBLIC = "https://machine.example.ts.net/status"
RELAY = {"Host": "machine.example.ts.net", "Origin": "https://machine.example.ts.net"}
SANDBOX = "allow-scripts allow-forms allow-modals allow-popups allow-downloads"
INTERACTIVE = "<!doctype html><title>Plan</title><h1 id=agent-heading>Plan</h1><script>window.agentCode = 1</script>"


def report(summary="First version", **fields):
    return {"title": "HoldCo bridge", "subject": "operator", "generated_at": "2026-11-22T10:00:00Z", "summary": summary, **fields}


def delivery(**fields):
    return {"title": "CI is green again", "summary": "Every run had failed since October.",
            "recommended_default": "Merge pull request 3.", "decision": {"question": "Merge it?", "options": ["Hold for changes"]},
            "category": "Projects", "links": [{"label": "Pull request", "target": "https://example.com/pull/3"},
                                             {"label": "Report", "target": "/work/REPORT.md"}], **fields}


class Workspace(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.reports, self.deliveries = StatusReports(self.root), Deliveries(self.root)

    def register(self, document, **origin):
        origin.setdefault("workspace", "/work/holdco")
        return register(document, render(document), root=self.root, **origin)

    def publish(self, document=None, **arguments):
        arguments.setdefault("workspace", "/work")
        return delivery_store.publish(document or delivery(), root=self.root, **arguments)

    def serve(self, **arguments):
        server = make_server(self.root, 0, **arguments)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_port
        self.token = json.loads(self.request("/api/config")[2])["token"]
        return server

    def request(self, path, body=None, *, headers=None, method=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            actual = {"Origin": f"http://127.0.0.1:{self.port}", "X-Status-Token": getattr(self, "token", "")}
            if body is not None:
                actual["Content-Type"] = "application/json"
            actual.update(headers or {})
            connection.request(method or ("GET" if body is None else "POST"), path,
                               body=None if body is None else json.dumps(body), headers=actual)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()


class OperationTests(Workspace):
    def test_versions_group_by_agent_then_thread_then_title_and_explicit_key_spans_workspaces(self):
        first = self.register(report("First"), agent="operator", thread_id="thread-a")
        second = self.register(report("Second"), agent="operator", thread_id="thread-b")
        self.register(report("Other agent"), agent="analyst")
        self.register(report("No agent"), thread_id="thread-a")
        self.register(report("No agent again"), thread_id="thread-a")
        self.register(report("Title only"))
        self.register(report("Keyed"), operation="holdco-bridge", workspace="/work/one")
        self.register(report("Keyed elsewhere"), operation="holdco-bridge", workspace="/work/two", agent="operator")
        operations = self.reports.operations()["operations"]
        self.assertEqual(sorted(len(operation["versions"]) for operation in operations), [1, 1, 2, 2, 2])
        operator = next(operation for operation in operations if {version["id"] for version in operation["versions"]} == {first, second})
        self.assertEqual(operator["latest"], second)
        self.assertEqual(operator["summary"], "Second")
        self.assertEqual(operator["threads"], ["thread-a", "thread-b"])
        for invalid in ("Holdco", "holdco bridge", "-holdco", "a" * 81, ""):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.register(report("Invalid key"), operation=invalid)

    def test_snapshots_registered_before_operations_keep_their_identifiers_and_group(self):
        document = report("Earlier snapshot")
        identifier = self.register(document, agent="operator")
        manifest = json.loads((self.root / "reports" / identifier / "manifest.json").read_text())
        self.assertNotIn("operation", manifest["origin"])       # the origin record is unchanged without an explicit key
        self.assertEqual(self.register(document, agent="operator"), identifier)
        self.assertEqual(len(self.reports.operations()["operations"]), 1)

    def test_unread_means_a_version_newer_than_the_last_one_opened(self):
        first = self.register(report("First"), agent="operator")
        operation = self.reports.operations()["operations"][0]
        self.assertTrue(operation["unread"])
        self.assertTrue(self.reports.mark_opened(first)["latest"])
        self.assertFalse(StatusReports(self.root).operations()["operations"][0]["unread"])
        second = self.register(report("Second"), agent="operator")
        self.assertTrue(self.reports.operations()["operations"][0]["unread"])
        self.assertFalse(self.reports.mark_opened(first)["latest"])      # an earlier version never clears a newer one
        self.assertTrue(self.reports.operations()["operations"][0]["unread"])
        self.reports.mark_opened(second)
        self.assertFalse(self.reports.operations()["operations"][0]["unread"])
        (self.root / "operation-state" / (operation["id"] + ".json")).write_text("not json")
        self.assertTrue(self.reports.operations()["operations"][0]["unread"])

    def test_dismissal_hides_an_operation_only_until_its_next_version(self):
        first = self.register(report("First"), agent="operator")
        self.reports.dismiss(first, True)
        self.assertTrue(self.reports.operations()["operations"][0]["dismissed_at"])
        self.register(report("Second"), agent="operator")
        operation = self.reports.operations()["operations"][0]
        self.assertIsNone(operation["dismissed_at"])
        self.assertEqual([bool(version["dismissed_at"]) for version in operation["versions"]], [False, True])

    def test_served_report_shows_history_and_older_version_notice(self):
        first = self.register(report("First"), agent="operator")
        second = self.register(report("Second", response_fields=[{"id": "proceed", "label": "Proceed?", "type": "boolean"}]), agent="operator")
        self.serve()
        status, headers, latest = self.request("/reports/" + second)
        self.assertEqual(status, 200)
        self.assertIn(b"Version 2 of 2", latest)
        self.assertNotIn(b"Open the latest version", latest)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        earlier = self.request("/reports/" + first)[2]
        self.assertIn(b"You are reading version 1 of 2", earlier)
        self.assertIn(f'href="/reports/{second}"'.encode(), earlier)
        operation = self.reports.operations()["operations"][0]["id"]
        status, headers, _ = self.request("/operations/" + operation)
        self.assertEqual((status, headers["Location"]), (302, "/reports/" + second))
        self.assertEqual(self.request("/operations/" + "0" * 64)[0], 404)
        opened = json.loads(self.request("/api/events", {"type": "item_open", "view": "operation", "item_kind": "operation", "item": second})[2])
        self.assertEqual(opened["opened"], {"operation": operation, "latest": True})
        self.assertFalse(json.loads(self.request("/api/review")[2])["operations"][0]["unread"])


class DeliveryTests(Workspace):
    def test_publication_is_idempotent_and_retains_document_and_attachments(self):
        attachment = self.root / "options.md"
        attachment.write_text("# Options\n\n<script>alert(1)</script>")
        identifier = self.publish(agent="proactive", thread_id="thread-1", body="See [options](options.md).", attachments=[attachment])
        self.assertEqual(self.publish(agent="proactive", thread_id="thread-1", body="See [options](options.md).", attachments=[attachment]), identifier)
        attachment.unlink()
        record = self.deliveries.record(identifier)
        self.assertEqual((record["status"], record["thread"], record["attachments"]), ("new", "agentcoord://thread/thread-1", ["options.md"]))
        self.assertEqual(self.deliveries.attachment(identifier, 0)[0], "options.md")
        self.assertEqual(len(self.deliveries.list()["deliveries"]), 1)
        with self.assertRaises(StatusError):
            self.deliveries.attachment(identifier, 1)

    def test_invalid_deliveries_are_rejected_instead_of_losing_content(self):
        for change in ({"title": ""}, {"summary": None}, {"unknown": "field"}, {"decision": {"options": ["A"]}},
                       {"decision": {"question": "Q", "options": ["A", "A"]}}, {"decision": {"question": "Q", "options": ["recommended_default"]}},
                       {"links": [{"label": "L", "target": "javascript:alert(1)"}]}, {"links": [{"label": "L", "target": "relative/path"}]},
                       {"thread": "https://example.com"}, {"created_at": "2026-11-22T10:00:00"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.publish({**delivery(), **change})
        binary = self.root / "archive.zip"
        binary.write_bytes(b"PK")
        with self.assertRaises(ValueError):
            self.publish(attachments=[binary])

    def test_each_response_is_recorded_with_its_time_and_can_be_reopened(self):
        identifier = self.publish(thread_id="thread-1")
        self.assertEqual(self.deliveries.respond(identifier, "read")["status"], "read")
        read_at = self.deliveries.record(identifier)["read_at"]
        self.assertEqual(self.deliveries.respond(identifier, "read")["read_at"], read_at)      # only the first opening counts
        accepted = self.deliveries.respond(identifier, "accept", choice="recommended_default", note=" Go ahead. ")
        self.assertEqual(accepted["response"]["type"], "accepted")
        self.assertEqual(accepted["response"]["note"], "Go ahead.")
        self.assertEqual(self.deliveries.respond(identifier, "accept", choice="Hold for changes")["response"]["choice"], "Hold for changes")
        self.assertIsNone(self.deliveries.respond(identifier, "reopen")["response"])
        dismissed = self.deliveries.respond(identifier, "dismiss", note="Not now")
        self.assertEqual((dismissed["status"], dismissed["response"]["note"]), ("dismissed", "Not now"))
        self.assertTrue(self.deliveries.respond(identifier, "discuss")["discussed_at"])
        history = Deliveries(self.root).record(identifier)["history"]
        self.assertEqual([event["action"] for event in history], ["read", "accept", "accept", "reopen", "dismiss", "discuss"])
        self.assertTrue(all(datetime.fromisoformat(event["at"]).utcoffset() is not None for event in history))
        for action, arguments in (("accept", {"choice": "Invented option"}), ("accept", {}), ("dismiss", {"choice": "Hold for changes"}),
                                  ("approve", {}), ("dismiss", {"note": "x" * 4001})):
            with self.subTest(action=action, arguments=arguments), self.assertRaises(StatusError):
                self.deliveries.respond(identifier, action, **arguments)
        plain = self.publish({"title": "Reading", "summary": "For information."})
        with self.assertRaises(StatusError):
            self.deliveries.respond(plain, "accept", choice="recommended_default")
        with self.assertRaises(StatusError):
            self.deliveries.respond(plain, "discuss")
        self.assertEqual(self.deliveries.respond(plain, "dismiss")["read_at"], self.deliveries.record(plain)["response"]["at"])

    def test_corrupt_state_is_reported_and_never_read_as_no_response(self):
        identifier = self.publish()
        self.deliveries.respond(identifier, "dismiss")
        (self.root / "delivery-state" / (identifier + ".json")).write_text("{}")
        with self.assertRaises(StatusError):
            self.deliveries.record(identifier)
        self.assertEqual(self.deliveries.list(), {"deliveries": [], "unreadable": 1})

    def test_agent_reads_delivery_responses_without_the_service(self):
        identifier = self.publish(agent="proactive", thread_id="thread-1")
        other = self.publish({"title": "Other", "summary": "Other agent."}, agent="someone-else")
        self.deliveries.respond(identifier, "accept", choice="Hold for changes", note="After Tuesday")
        command = [sys.executable, "-B", str(SCRIPTS / "read_responses.py"), "--inbox", str(self.root)]
        result = json.loads(subprocess.run(command + ["--deliveries", "--agent", "proactive"], check=True, capture_output=True, text=True).stdout)
        self.assertEqual([entry["id"] for entry in result["deliveries"]], [identifier])
        self.assertEqual(result["deliveries"][0]["response"]["choice"], "Hold for changes")
        self.assertEqual(result["deliveries"][0]["response"]["note"], "After Tuesday")
        exact = json.loads(subprocess.run(command + ["--delivery", other], check=True, capture_output=True, text=True).stdout)
        self.assertEqual(exact["deliveries"][0]["status"], "new")
        future = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
        later = json.loads(subprocess.run(command + ["--deliveries", "--agent", "proactive", "--since", future], check=True, capture_output=True, text=True).stdout)
        self.assertEqual(later["deliveries"], [])

    def test_publish_command_prints_identifier_and_reports_invalid_input(self):
        source = self.root / "delivery.json"
        source.write_text(json.dumps(delivery()))
        body = self.root / "delivery.md"
        body.write_text("# Finished\n\nDetails.")
        command = [sys.executable, "-B", str(SCRIPTS / "publish_delivery.py"), str(source), "--document", str(body),
                   "--workspace", "/work", "--agent", "proactive", "--inbox", str(self.root)]
        environment = {key: value for key, value in os.environ.items() if key not in {"AGENT_COORD_SESSION_ID", "CODEX_THREAD_ID"}}
        result = json.loads(subprocess.run(command, check=True, capture_output=True, text=True, env=environment).stdout)
        self.assertEqual(self.deliveries.record(result["delivery"])["origin"]["agent"], "proactive")
        self.assertNotIn("url", result)
        source.write_text(json.dumps({"title": "No summary"}))
        failed = subprocess.run(command, capture_output=True, text=True, env=environment)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("summary", failed.stderr)

    def test_delivery_pages_escape_content_and_link_only_safe_targets(self):
        attachment = self.root / "options.md"
        attachment.write_text("# Options\n\n<img src=x onerror=alert(1)>")
        identifier = self.publish({**delivery(), "title": "<script>alert(1)</script>"}, thread_id="thread-1",
                                  body="[options](options.md) [bad](javascript:alert(1)) <b>raw</b>", attachments=[attachment])
        self.serve()
        status, headers, content = self.request("/deliveries/" + identifier)
        page = content.decode()
        self.assertEqual(status, 200)
        self.assertNotIn("<script>alert", page)
        self.assertNotIn('href="javascript:', page)
        self.assertNotIn("<b>raw</b>", page)
        self.assertIn(f'href="/deliveries/{identifier}/attachments/0"', page)
        self.assertIn('data-path="/work/REPORT.md"', page)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        attached = self.request(f"/deliveries/{identifier}/attachments/0")[2].decode()
        self.assertNotIn("<img", attached)
        for missing in (f"/deliveries/{identifier}/attachments/9", f"/deliveries/{identifier}/other", "/deliveries/" + "0" * 64):
            self.assertEqual(self.request(missing)[0], 404)

    def test_responses_over_http_require_the_page_token_and_are_measured(self):
        identifier = self.publish(thread_id="thread-1")
        self.serve()
        body = {"id": identifier, "action": "accept", "choice": "recommended_default"}
        for headers in ({"X-Status-Token": ""}, {"Origin": "https://elsewhere.invalid"}, {"Host": "elsewhere.invalid"}):
            self.assertEqual(self.request("/api/delivery-response", body, headers=headers)[0], 403)
        self.assertEqual(self.request("/api/delivery-response", {"id": identifier, "action": "read"})[0], 200)
        self.assertEqual(json.loads(self.request("/api/delivery-response", body)[2])["status"], "accepted")
        self.assertEqual(self.request("/api/delivery-response", {**body, "choice": "Invented"})[0], 400)
        self.assertEqual(self.request("/api/delivery-response", {**body, "extra": True})[0], 400)
        self.assertEqual(self.request("/api/events", {"type": "page_open", "view": "review", "narrow": True})[0], 200)
        for invalid in ({"type": "response"}, {"type": "page_open", "view": "elsewhere"}, {"type": "item_open", "item_kind": "delivery"},
                        {"type": "item_open", "item_kind": "delivery", "item": "../x"}):
            self.assertEqual(self.request("/api/events", invalid)[0], 400)
        events = UsageEvents(self.root).read()
        self.assertEqual([(event["type"], event["action"]) for event in events], [("response", "accept"), ("page_open", None)])
        self.assertNotIn("CI is green", json.dumps(events))        # measurements hold identifiers and times only
        review = json.loads(self.request("/api/review")[2])
        self.assertEqual(review["deliveries"][0]["response"]["type"], "accepted")


class DeliveryVersionTests(Workspace):
    def test_deliveries_sharing_a_key_are_versions_of_one_delivery(self):
        first = self.publish(delivery(summary="First plan."), key="thanksgiving-plan")
        self.assertEqual(self.publish(delivery(summary="First plan."), key="thanksgiving-plan"), first)      # unchanged: no new version
        second = self.publish(delivery(summary="Corrected plan."), key="thanksgiving-plan", workspace="/elsewhere")
        self.assertEqual(self.publish(delivery(summary="Corrected plan."), key="thanksgiving-plan", workspace="/elsewhere"), second)
        third = self.publish(delivery(summary="First plan."), key="thanksgiving-plan")                      # a correction may return to earlier content
        self.assertEqual(len({first, second, third}), 3)
        self.publish(delivery(summary="First plan."))                                                       # no key: its own delivery
        listing = self.deliveries.list()["deliveries"]
        self.assertEqual(len(listing), 2)
        living = next(entry for entry in listing if entry["key"])
        self.assertEqual((living["id"], living["version"], living["version_count"], living["number"], living["latest"]), (third, third, 3, 3, True))
        self.assertEqual([version["id"] for version in living["versions"]], [third, second, first])
        series = living["series"]
        self.assertRegex(series, r"\A[a-f0-9]{64}\Z")
        self.assertNotIn(series, {first, second, third})
        self.assertEqual(self.deliveries.record(series)["id"], third)                # the series address shows the latest version
        earlier = self.deliveries.record(first)
        self.assertEqual((earlier["id"], earlier["number"], earlier["latest"], earlier["series"], earlier["summary"]), (first, 1, False, series, "First plan."))
        for invalid in ("Plan", "thanksgiving plan", "-plan", "a" * 81, ""):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.publish(key=invalid)
        with self.assertRaises(ValueError):
            self.publish(key="thanksgiving-plan", replaces=first)

    def test_a_delivery_without_a_key_keeps_its_identifier_record_and_state(self):
        document = delivery()
        identifier = self.publish(document, agent="proactive")
        origin = {"workspace": "/work", "agent": "proactive", "provider": None, "thread_id": None, "host": socket.gethostname()}
        canonical = json.dumps({"delivery": document, "origin": origin, "body": None, "attachments": []},
                               sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(identifier, hashlib.sha256(canonical.encode()).hexdigest())      # the identifier from before versions existed
        manifest = json.loads((self.root / "deliveries" / identifier / "delivery.json").read_text())
        self.assertFalse({"key", "series", "content_digest", "interactive"} & manifest.keys())
        self.assertFalse((self.root / "deliveries" / identifier / "interactive.html").exists())
        record = self.deliveries.record(identifier)
        self.assertEqual((record["series"], record["version"], record["version_count"], record["key"], record["interactive"]),
                         (identifier, identifier, 1, None, None))
        self.assertIsNone(record["document_state"])

    def test_a_replacement_joins_the_series_and_keeps_the_responses_given_before_versions(self):
        first = self.publish(thread_id="thread-1")
        at = "2026-11-22T10:00:00+00:00"                      # a state record in the shape written before versions
        (self.root / "delivery-state").mkdir()
        (self.root / "delivery-state" / (first + ".json")).write_text(json.dumps({
            "read_at": at, "discussed_at": None, "response": {"type": "accepted", "choice": "recommended_default", "note": None, "at": at},
            "history": [{"action": "read", "at": at}, {"action": "accept", "choice": "recommended_default", "note": None, "at": at}]}))
        before = self.deliveries.record(first)
        self.assertEqual((before["unread"], before["status"], before["response"]["version"], before["read_version"]), (False, "accepted", first, first))
        second = self.publish(delivery(summary="Corrected.", decision={"question": "Merge it?", "options": ["Wait a week"]}), replaces=first, thread_id="thread-1")
        self.assertEqual(self.publish(delivery(summary="Corrected.", decision={"question": "Merge it?", "options": ["Wait a week"]}), replaces=first, thread_id="thread-1"), second)
        record = self.deliveries.list()["deliveries"][0]
        self.assertEqual(len(self.deliveries.list()["deliveries"]), 1)
        self.assertEqual((record["id"], record["series"], record["version_count"]), (second, first, 2))
        self.assertTrue(record["unread"])                                            # a newer version than the one he read
        self.assertEqual((record["status"], record["response"]["version"], record["response_version_number"], record["number"]), ("accepted", first, 1, 2))
        third = self.publish(delivery(summary="Corrected again."), replaces=second)   # naming any version continues the same series
        self.assertEqual(self.deliveries.record(third)["series"], first)
        self.assertEqual(self.deliveries.record(first)["id"], first)                  # a version's own address always shows that version
        keyed = self.publish(key="living")
        for invalid in (keyed, "0" * 64, "not-an-identifier"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.publish(delivery(summary="Other."), replaces=invalid)

    def test_responses_are_given_on_the_latest_version_and_record_it(self):
        first = self.publish(key="plan")
        self.deliveries.respond(first, "read")
        self.deliveries.respond(first, "accept", choice="Hold for changes")
        second = self.publish(delivery(summary="Second.", decision={"question": "Now?", "options": ["Wait a week"]}), key="plan")
        with self.assertRaises(ResponseConflict):                                    # he was looking at a superseded version
            self.deliveries.respond(first, "dismiss")
        with self.assertRaises(ResponseConflict):
            self.deliveries.respond(first, "reopen")
        self.assertTrue(self.deliveries.respond(first, "read")["unread"])             # opening an earlier version clears nothing
        series = self.deliveries.record(second)["series"]
        with self.assertRaises(StatusError):
            self.deliveries.respond(series, "dismiss")                               # a response names the version it answers
        with self.assertRaises(StatusError):
            self.deliveries.respond(second, "accept", choice="Hold for changes")      # choices are those of the version answered
        stale = self.deliveries.record(second)
        self.assertEqual((stale["status"], stale["unread"], stale["response"]["version"], stale["response_version_number"]), ("accepted", True, first, 1))
        self.assertFalse(self.deliveries.respond(second, "read")["unread"])
        self.assertEqual(self.deliveries.record(second)["response"]["choice"], "Hold for changes")       # reading keeps his response
        self.assertIsNone(self.deliveries.respond(second, "reopen")["response"])
        accepted = self.deliveries.respond(second, "accept", choice="Wait a week")
        self.assertEqual((accepted["response"]["version"], accepted["response_version_number"]), (second, 2))
        history = self.deliveries.record(second)["history"]
        self.assertEqual([(event["action"], event["version"]) for event in history],
                         [("read", first), ("accept", first), ("read", second), ("reopen", second), ("accept", second)])
        self.assertEqual(sorted(path.name for path in (self.root / "delivery-state").glob("*.json")), [series + ".json"])

    def test_pages_list_one_row_and_show_versions_with_an_earlier_version_notice(self):
        first = self.publish(delivery(summary="First plan."), key="plan")
        self.deliveries.respond(first, "accept", choice="recommended_default")
        second = self.publish(delivery(summary="Second plan."), key="plan")
        single = self.publish(delivery(title="Single"))
        self.serve()
        review = json.loads(self.request("/api/review")[2])
        self.assertEqual(len(review["deliveries"]), 2)
        row = next(entry for entry in review["deliveries"] if entry["key"] == "plan")
        self.assertEqual((row["id"], row["version_count"], row["unread"], row["response"]["version"], row["response_version_number"]),
                         (second, 2, True, first, 1))
        self.assertNotIn("document_state", row)
        series = row["series"]
        for address in (series, second):
            page = self.request("/deliveries/" + address)[2].decode()
            self.assertIn("Second plan.", page)
            self.assertIn("Version 2 of 2", page)
            self.assertNotIn("Open the latest version", page)
            self.assertIn(f'href="/deliveries/{first}"', page)
        earlier = self.request("/deliveries/" + first)[2].decode()
        self.assertIn("First plan.", earlier)
        self.assertIn("You are reading version 1 of 2", earlier)
        self.assertIn(f'href="/deliveries/{second}">Open the latest version', earlier)
        self.assertNotIn("version-history", self.request("/deliveries/" + single)[2].decode())
        body = {"id": first, "action": "dismiss"}
        self.assertEqual(self.request("/api/delivery-response", body)[0], 409)        # refused: a newer version exists
        self.assertEqual(self.request("/api/delivery-response", {"id": second, "action": "read"})[0], 200)
        self.assertFalse(next(entry for entry in json.loads(self.request("/api/review")[2])["deliveries"] if entry["key"] == "plan")["unread"])

    def test_agents_read_the_series_and_metrics_count_it_once(self):
        first = self.publish(key="plan", agent="proactive")
        self.deliveries.respond(first, "accept", choice="recommended_default")
        second = self.publish(delivery(summary="Second."), key="plan", agent="proactive")
        command = [sys.executable, "-B", str(SCRIPTS / "read_responses.py"), "--inbox", str(self.root)]
        result = json.loads(subprocess.run(command + ["--deliveries", "--agent", "proactive"], check=True, capture_output=True, text=True).stdout)
        self.assertEqual(len(result["deliveries"]), 1)
        entry = result["deliveries"][0]
        series = self.deliveries.record(second)["series"]
        self.assertEqual((entry["id"], entry["key"], entry["series"], entry["version"], entry["version_count"], entry["response"]["version"]),
                         (second, "plan", series, second, 2, first))
        for address in (series, first):                         # the series or any of its versions selects the delivery
            exact = json.loads(subprocess.run(command + ["--delivery", address], check=True, capture_output=True, text=True).stdout)
            self.assertEqual(exact["deliveries"][0]["series"], series)
        now = datetime.now(timezone.utc)
        summary = summarize(self.reports, self.deliveries, [], since=now - timedelta(days=1), until=now + timedelta(minutes=1), zone=ZoneInfo("UTC"))
        self.assertEqual(summary["proactive_deliveries"]["delivered"], 1)
        self.assertEqual(summary["proactive_deliveries"]["counts"]["accepted"], 1)

    def test_publish_command_publishes_versions_and_reports_conflicting_options(self):
        source = self.root / "delivery.json"
        source.write_text(json.dumps(delivery()))
        command = [sys.executable, "-B", str(SCRIPTS / "publish_delivery.py"), str(source), "--workspace", "/work", "--inbox", str(self.root)]
        first = json.loads(subprocess.run(command + ["--key", "plan"], check=True, capture_output=True, text=True).stdout)
        source.write_text(json.dumps(delivery(summary="Second.")))
        second = json.loads(subprocess.run(command + ["--key", "plan"], check=True, capture_output=True, text=True).stdout)
        self.assertEqual((first["version_number"], second["version_number"], first["series"]), (1, 2, second["series"]))
        plain = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
        source.write_text(json.dumps(delivery(summary="Third.")))
        replaced = json.loads(subprocess.run(command + ["--replaces", plain["delivery"]], check=True, capture_output=True, text=True).stdout)
        self.assertEqual((replaced["series"], replaced["version_number"]), (plain["delivery"], 2))
        for arguments in (["--key", "plan", "--replaces", plain["delivery"]], ["--replaces", second["delivery"]], ["--key", "Not Valid"]):
            failed = subprocess.run(command + arguments, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)


class InteractiveDocumentTests(Workspace):
    def interactive_report(self, **arguments):
        document = report("Interactive")
        return register(document, render(document), root=self.root, workspace="/work/holdco", agent="operator", **arguments)

    def test_a_retained_document_is_served_only_under_the_sandbox_policy(self):
        identifier = self.publish(interactive_document=INTERACTIVE)
        report_id = self.interactive_report(interactive_document=INTERACTIVE)
        plain, plain_report = self.publish(delivery(title="Plain")), self.register(report("Plain"), agent="analyst")
        self.serve(public_url=PUBLIC)
        for path, headers in ((f"/deliveries/{identifier}/interactive", None), (f"/reports/{report_id}/interactive", None),
                              (f"/status/deliveries/{identifier}/interactive", RELAY), (f"/reports/{report_id}/interactive", RELAY)):
            with self.subTest(path=path, relayed=bool(headers)):
                status, response, content = self.request(path, headers=headers)
                self.assertEqual((status, content.decode()), (200, INTERACTIVE))
                policy = response["Content-Security-Policy"]
                self.assertEqual(policy, f"sandbox {SANDBOX}; frame-ancestors 'self'")
                for forbidden in ("allow-same-origin", "allow-top-navigation", "allow-popups-to-escape-sandbox"):
                    self.assertNotIn(forbidden, policy)
                self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                self.assertTrue(response["Content-Type"].startswith("text/html"))
                self.assertNotIn("Access-Control-Allow-Origin", response)
        self.assertIn("sandbox", self.request(f"/deliveries/{identifier}/interactive", method="HEAD")[1]["Content-Security-Policy"])
        for missing in (f"/deliveries/{plain}/interactive", f"/reports/{plain_report}/interactive", f"/reports/{report_id}/other",
                        "/deliveries/" + "0" * 64 + "/interactive"):
            self.assertEqual(self.request(missing)[0], 404)

    def test_the_item_page_frames_the_document_without_its_origin_and_never_inlines_it(self):
        identifier = self.publish(interactive_document=INTERACTIVE, body="# Write-up\n\nStill here.")
        report_id = self.interactive_report(interactive_document=INTERACTIVE)
        self.serve(public_url=PUBLIC)
        frame = (f'<iframe id="embedded-document" class="embedded-document" src="{{}}" sandbox="{SANDBOX}" '
                 f'referrerpolicy="no-referrer" loading="lazy" title="Interactive document: {{}}"></iframe>')
        for path, source, title, headers in ((f"/deliveries/{identifier}", f"/deliveries/{identifier}/interactive", "CI is green again", None),
                                             (f"/reports/{report_id}", f"/reports/{report_id}/interactive", "HoldCo bridge", None),
                                             (f"/status/deliveries/{identifier}", f"/status/deliveries/{identifier}/interactive", "CI is green again", RELAY)):
            with self.subTest(path=path):
                status, response, content = self.request(path, headers=headers)
                page = content.decode()
                self.assertEqual(status, 200)
                self.assertIn(frame.format(source, title), page)
                self.assertEqual(page.count("<iframe"), 1)
                self.assertNotIn("allow-same-origin", page)
                self.assertNotIn("agentCode", page)                      # agent markup is never written into the host page
                self.assertNotIn("agent-heading", page)
                self.assertIn("embedded_host.js", page)
                policy = response["Content-Security-Policy"]
                self.assertEqual(policy, "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src data:; "
                                         "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; frame-src 'self' https://machine.example.ts.net")
                self.assertEqual(response["X-Frame-Options"], "DENY")
                self.assertEqual(response["Cross-Origin-Resource-Policy"], "same-origin")
        page = self.request(f"/deliveries/{identifier}")[2].decode()
        self.assertLess(page.index('id="delivery-response"'), page.index("<iframe"))          # after the response controls,
        self.assertLess(page.index("<iframe"), page.index("Still here."))                     # before the write-up
        served = self.request(f"/reports/{report_id}")[2].decode()
        self.assertLess(served.index('class="assessment text"'), served.index("<iframe"))
        configuration = json.loads(page.split('id="status-configuration">')[1].split("</script>")[0])
        self.assertEqual(configuration["embedded"], {"kind": "delivery", "item": identifier, "latest": True, "public_url": PUBLIC})
        self.assertEqual(configuration["delivery"]["interactive"], {"kind": "document", "address": None})
        self.assertEqual(json.loads(self.request("/api/review")[2])["operations"][0]["interactive"], {"kind": "document", "address": None})

    def test_without_a_public_address_pages_frame_only_this_origin(self):
        self.serve()
        self.assertTrue(self.request("/")[1]["Content-Security-Policy"].endswith("frame-ancestors 'none'; frame-src 'self'"))

    def test_an_item_without_an_interactive_document_is_unchanged(self):
        identifier = self.publish(body="# Write-up\n\nDetails.")
        report_id = self.register(report("Plain"), agent="operator")
        manifest = json.loads((self.root / "reports" / report_id / "manifest.json").read_text())
        self.assertEqual(set(manifest), {"version", "id", "title", "subject", "summary", "generated_at", "received_at", "origin", "response_field_count"})
        origin = {"workspace": "/work/holdco", "agent": "operator", "provider": None, "thread_id": None, "host": socket.gethostname()}
        canonical = json.dumps({"document": report("Plain"), "origin": origin}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(report_id, hashlib.sha256(canonical.encode()).hexdigest())
        self.assertEqual(sorted(path.name for path in (self.root / "reports" / report_id).iterdir()), ["manifest.json", "report.html", "report.json"])
        self.serve()
        for path in ("/deliveries/" + identifier, "/reports/" + report_id):
            page = self.request(path)[2].decode()
            for absent in ("<iframe", "embedded_host.js", 'class="embedded', '"embedded"'):
                self.assertNotIn(absent, page)
        self.assertIsNone(json.loads(self.request("/api/review")[2])["deliveries"][0]["interactive"])
        self.assertEqual(self.request(f"/api/document-state/delivery/{identifier}")[0], 404)
        self.assertEqual(self.request("/api/document-state", {"kind": "delivery", "id": identifier, "state": 1})[0], 400)

    def test_one_form_is_accepted_and_an_address_is_a_plain_path_of_another_application(self):
        for address in ("/thanksgiving/", "/thanksgiving", "/apps/plan-2026/index.html", "/a_b/c~d/"):
            with self.subTest(address=address):
                self.assertEqual(interactive_documents.validate_address(address, "/status"), address)
        for address in ("/", "", "thanksgiving/", "//evil.example/", "https://evil.example/", "/a/../b", "/a/./b", "/..", "/a?b=1", "/a#b", "/a b",
                        "/a%2e%2e/b", "/a\\b", "/status", "/status/", "/status/reports/x", "/a/" * 300, None, 7):
            with self.subTest(address=address), self.assertRaises(ValueError):
                interactive_documents.validate_address(address, "/status")
        with self.assertRaises(ValueError):
            interactive_documents.validate_address("/thanksgiving/", "")              # the review page occupies the whole host
        with self.assertRaises(ValueError):
            self.publish(interactive_document=INTERACTIVE, embed="/thanksgiving/")
        with self.assertRaises(ValueError):
            self.publish(interactive_document="x" * (4 * 1024 * 1024 + 1))
        with self.assertRaises(ValueError):
            self.publish(interactive_document="   ")
        with self.assertRaises(ValueError):
            self.publish(embed="/status/deliveries/", public_prefix="/status")
        with self.assertRaises(ValueError):
            self.interactive_report(embed="//evil.example/")
        self.assertEqual(self.deliveries.list()["deliveries"], [])
        plain, embedding = self.publish(), self.publish(embed="/thanksgiving/")
        self.assertNotEqual(plain, embedding)                                        # the document is part of what was delivered
        self.assertNotEqual(self.publish(interactive_document=INTERACTIVE), self.publish(interactive_document=INTERACTIVE + " "))
        path = self.root / "deliveries" / embedding / "delivery.json"
        manifest = json.loads(path.read_text())
        self.assertEqual(manifest["interactive"], {"kind": "address", "address": "/thanksgiving/"})
        self.assertFalse((path.parent / "interactive.html").exists())                # an address is recorded, never fetched
        path.write_text(json.dumps({**manifest, "interactive": {"kind": "address", "address": "https://evil.example/"}}))
        with self.assertRaises(StatusError):
            self.deliveries.record(embedding)                                        # a tampered record is unreadable, not framed

    def test_an_address_is_framed_on_the_public_origin_and_explained_on_the_local_one(self):
        identifier = self.publish(embed="/thanksgiving/")
        report_id = self.interactive_report(embed="/thanksgiving/menu.html")
        self.serve(public_url=PUBLIC)
        page = self.request("/status/deliveries/" + identifier, headers=RELAY)[2].decode()
        self.assertIn(f'<iframe id="embedded-document" class="embedded-document" src="https://machine.example.ts.net/thanksgiving/" sandbox="{SANDBOX}" '
                      'referrerpolicy="no-referrer" loading="lazy"', page)
        self.assertNotIn("allow-same-origin", page)
        self.assertIn('src="https://machine.example.ts.net/thanksgiving/menu.html"', self.request("/reports/" + report_id, headers=RELAY)[2].decode())
        self.assertEqual(self.request(f"/status/deliveries/{identifier}/interactive", headers=RELAY)[0], 404)      # nothing is retained or relayed
        local = self.request("/deliveries/" + identifier)[2].decode()
        self.assertNotIn("<iframe", local)
        self.assertIn("served on the tailnet address", local)
        self.assertIn(f'href="{PUBLIC}/deliveries/{identifier}">Open this delivery there', local)
        self.assertIn(f'href="{PUBLIC}/reports/{report_id}">Open this report there', self.request("/reports/" + report_id)[2].decode())

    def test_an_address_without_a_public_address_is_explained_and_never_framed(self):
        identifier = self.publish(embed="/thanksgiving/")
        self.serve()
        page = self.request("/deliveries/" + identifier)[2].decode()
        self.assertNotIn("<iframe", page)
        self.assertIn("served on the tailnet address", page)

    def test_the_document_helper_alone_is_readable_from_an_opaque_origin(self):
        self.serve()
        status, headers, content = self.request("/document_bridge.js", headers={"Origin": "null"})
        self.assertEqual((status, headers["Cross-Origin-Resource-Policy"], headers["Access-Control-Allow-Origin"]), (200, "cross-origin", "*"))
        self.assertIn(b"StatusDocument", content)
        for path in ("/embedded_host.js", "/controls.js", "/api/config"):
            headers = self.request(path, headers={"Origin": "null"})[1]
            self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")
            self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_document_state_is_saved_for_the_item_through_the_page_only(self):
        first = self.publish(key="plan", interactive_document=INTERACTIVE)
        report_id = self.interactive_report(interactive_document=INTERACTIVE)
        self.serve()
        body = {"kind": "delivery", "id": first, "state": {"picked": ["B"], "guests": 9}}
        for headers in ({"X-Status-Token": ""}, {"Origin": "null"}, {"Origin": "https://elsewhere.invalid"}, {"Host": "elsewhere.invalid"}):
            self.assertEqual(self.request("/api/document-state", body, headers=headers)[0], 403)      # a sandboxed frame's origin is null
        self.assertEqual(json.loads(self.request(f"/api/document-state/delivery/{first}")[2]),
                         {"state": None, "saved_at": None, "revision": 0, "version": None})
        saved = json.loads(self.request("/api/document-state", body)[2])
        self.assertEqual((saved["revision"], saved["version"]), (1, first))
        self.assertEqual(json.loads(self.request("/api/document-state", {**body, "state": "second"})[2])["revision"], 2)
        series = self.deliveries.record(first)["series"]
        self.assertEqual(sorted(path.name for path in (self.root / "document-state").glob("*.json")), [series + ".json"])
        self.assertEqual(DocumentStates(self.root).read(series)["state"], "second")
        for invalid in ({**body, "state": "x" * (64 * 1024)}, {**body, "kind": "ask"}, {**body, "id": "0" * 64}, {**body, "id": series},
                        {"kind": "delivery", "id": first}, {**body, "extra": 1}):
            self.assertIn(self.request("/api/document-state", invalid)[0], (400, 404))
        self.assertEqual(self.request("/api/document-state", {**body, "state": "x" * (90 * 1024)})[0], 400)
        self.assertEqual(DocumentStates(self.root).read(series)["revision"], 2)
        self.assertIsNone(self.deliveries.record(first)["response"])                  # saved state is never a response
        second = self.publish(delivery(summary="Second."), key="plan", interactive_document=INTERACTIVE)
        self.assertEqual(self.request("/api/document-state", body)[0], 409)           # an earlier version cannot overwrite
        self.assertEqual(json.loads(self.request(f"/api/document-state/delivery/{second}")[2])["state"], "second")      # state stays with the delivery
        self.assertEqual(json.loads(self.request("/api/document-state", {**body, "id": second, "state": None})[2])["version"], second)
        self.request("/api/document-state", {"kind": "report", "id": report_id, "state": {"row": 3}})
        operation = self.reports.operations()["operations"][0]["id"]
        self.assertEqual(DocumentStates(self.root).read(operation)["state"], {"row": 3})
        command = [sys.executable, "-B", str(SCRIPTS / "read_responses.py"), "--inbox", str(self.root)]
        answered = json.loads(subprocess.run(command + ["--report", report_id], check=True, capture_output=True, text=True).stdout)["responses"][0]
        self.assertEqual((answered["document_state"]["state"], answered["document_state"]["version"], answered["operation"]), ({"row": 3}, report_id, operation))
        listed = json.loads(subprocess.run(command + ["--workspace", "/work/holdco"], check=True, capture_output=True, text=True).stdout)["responses"]
        self.assertEqual([entry["id"] for entry in listed], [report_id])
        delivered = json.loads(subprocess.run(command + ["--delivery", series], check=True, capture_output=True, text=True).stdout)["deliveries"][0]
        self.assertEqual((delivered["document_state"]["state"], delivered["document_state"]["revision"], delivered["interactive"]["kind"]), (None, 3, "document"))
        (self.root / "document-state" / (series + ".json")).write_text("{}")
        self.assertTrue(self.deliveries.record(second)["document_state"]["unreadable"])       # reported, never shown as nothing saved

    def test_opening_an_interactive_document_is_measured_without_content(self):
        identifier = self.publish(interactive_document=INTERACTIVE)
        report_id = self.interactive_report(interactive_document=INTERACTIVE)
        self.serve()
        opened = {"type": "item_open", "view": "operation", "item_kind": "operation", "item": report_id, "action": "interactive_document"}
        self.assertIsNone(json.loads(self.request("/api/events", opened)[2])["opened"])
        self.assertTrue(self.reports.operations()["operations"][0]["unread"])         # the document's event is not the report being opened
        self.assertEqual(self.request("/api/events", {**opened, "view": "delivery", "item_kind": "delivery", "item": identifier})[0], 200)
        self.assertEqual(self.request("/api/events", {**opened, "action": "something_else"})[0], 400)
        self.request("/api/events", {key: value for key, value in opened.items() if key != "action"})
        events = UsageEvents(self.root).read()
        self.assertEqual({key for event in events for key in event}, {"at", "type", "view", "item_kind", "item", "action", "narrow", "remote"})
        now = datetime.now(timezone.utc)
        summary = summarize(self.reports, self.deliveries, events, since=now - timedelta(days=1), until=now + timedelta(minutes=1), zone=ZoneInfo("UTC"))
        self.assertEqual(summary["interactive_document_opens"], {"total": 2, "by_kind": {"delivery": 1, "operation": 1}})
        self.assertEqual([row["opens"] for row in summary["operation_report_opens"]], [1])

    def test_commands_publish_a_document_or_an_address(self):
        page, source = self.root / "plan.html", self.root / "delivery.json"
        page.write_text(INTERACTIVE)
        source.write_text(json.dumps(delivery()))
        command = [sys.executable, "-B", str(SCRIPTS / "publish_delivery.py"), str(source), "--workspace", "/work", "--inbox", str(self.root)]
        published = json.loads(subprocess.run(command + ["--interactive", str(page)], check=True, capture_output=True, text=True).stdout)["delivery"]
        self.assertEqual(self.deliveries.interactive_document(published), INTERACTIVE)
        embedded = json.loads(subprocess.run(command + ["--embed", "/thanksgiving/"], check=True, capture_output=True, text=True).stdout)["delivery"]
        self.assertEqual(self.deliveries.record(embedded)["interactive"], {"kind": "address", "address": "/thanksgiving/"})
        for arguments in (["--interactive", str(page), "--embed", "/thanksgiving/"], ["--embed", "https://evil.example/"],
                          ["--embed", "/"], ["--interactive", str(self.root / "missing.html")]):
            failed = subprocess.run(command + arguments, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0, arguments)
        status = self.root / "status.json"
        status.write_text(json.dumps(report("Interactive")))
        environment = {**os.environ, "AGENT_STATUS_INBOX": str(self.root)}
        build = [sys.executable, "-B", str(SCRIPTS / "build_status.py"), str(status), "--output", str(self.root / "status.html"), "--workspace", "/work"]
        receipt = subprocess.run(build + ["--interactive", str(page)], check=True, capture_output=True, text=True, env=environment).stdout
        built = receipt.split("Status inbox receipt: ")[1].splitlines()[0]
        self.assertEqual(self.reports.interactive_document(built), INTERACTIVE)
        self.assertNotIn("agentCode", (self.root / "status.html").read_text())        # the portable file stays the plain report
        self.assertNotEqual(subprocess.run(build + ["--embed", "/a/../b"], capture_output=True, text=True, env=environment).returncode, 0)
        self.assertNotEqual(subprocess.run(build + ["--no-register", "--embed", "/thanksgiving/"], capture_output=True, text=True, env=environment).returncode, 0)
        (self.root / "status.html").write_text(render(report("Registered")))
        status.write_text(json.dumps(report("Registered")))
        registered = subprocess.run([sys.executable, "-B", str(SCRIPTS / "register_status.py"), str(status), "--html", str(self.root / "status.html"),
                                     "--workspace", "/work", "--embed", "/thanksgiving/"], check=True, capture_output=True, text=True, env=environment).stdout.strip()
        self.assertEqual(self.reports._manifest(registered)["interactive"], {"kind": "address", "address": "/thanksgiving/"})


class LinkTests(Workspace):
    def test_the_embedded_view_frames_another_application_inside_the_page(self):
        identifier = self.publish()
        report_id = self.register(report("Served"), agent="operator")
        self.serve(public_url=PUBLIC)
        status, headers, content = self.request(f"/status/embedded?address=/thanksgiving/&from={identifier}", headers=RELAY)
        page = content.decode()
        self.assertEqual(status, 200)
        self.assertIn(f'<iframe id="embedded-document" class="embedded-document" src="https://machine.example.ts.net/thanksgiving/" sandbox="{SANDBOX}" '
                      'referrerpolicy="no-referrer" loading="lazy" title="Application at /thanksgiving/"></iframe>', page)
        self.assertNotIn("allow-same-origin", page)
        self.assertIn(f'<a class="back-link" href="/status/deliveries/{identifier}">CI is green again</a>', page)
        self.assertIn('<a href="https://machine.example.ts.net/thanksgiving/">Open on its own</a>', page)
        self.assertIn("frame-src 'self' https://machine.example.ts.net", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn(f'href="/status/reports/{report_id}">HoldCo bridge</a>',
                      self.request(f"/embedded?address=/thanksgiving/menu.html&from={report_id}", headers=RELAY)[2].decode())
        for origin in ("", "&from=" + "0" * 64, "&from=%22%3E%3Cscript%3E"):
            page = self.request("/embedded?address=/thanksgiving/" + origin, headers=RELAY)[2].decode()
            self.assertIn('<a class="back-link" href="/status/">Review</a>', page)
            self.assertNotIn("<script>", page.replace('<script src=', "").replace('<script type="application/json"', ""))
        for address in ("/", "", "/status/", "/status/reports/x", "//evil.example/", "https://evil.example/", "/a/../b", "/a%3Fb",
                        "/thanksgiving/%22%3E%3Cscript%3Ealert(1)%3C/script%3E", "javascript:alert(1)"):
            with self.subTest(address=address):
                self.assertEqual(self.request("/embedded?address=" + address, headers=RELAY)[0], 404)
        local = self.request(f"/embedded?address=/thanksgiving/&from={identifier}")[2].decode()
        self.assertNotIn("<iframe", local)
        self.assertIn(f'href="{PUBLIC}/embedded?address=/thanksgiving/&amp;from={identifier}">Open it there', local)
        self.assertIn(f'<a class="back-link" href="/deliveries/{identifier}">', local)

    def test_links_to_this_host_stay_in_the_tab_and_other_applications_open_embedded(self):
        other = self.publish(delivery(title="Other"))
        report_id = self.register(report("Served"), agent="operator")
        attachment = self.root / "options.md"
        attachment.write_text("[menu](/thanksgiving/menu)")
        existing = self.root / "notes.txt"
        existing.write_text("local")
        targets = {"App": "/thanksgiving/", "App page": "https://machine.example.ts.net/thanksgiving/menu.html",
                   "Report": f"{PUBLIC}/reports/{report_id}", "Delivery": f"/deliveries/{other}", "Website": "https://example.com/pull/3",
                   "File": str(existing), "Elsewhere file": "/work/REPORT.md", "Query": "https://machine.example.ts.net/thanksgiving/?tab=2",
                   "Ribbon Field root": "https://machine.example.ts.net/", "Thread": "agentcoord://thread/abc", "Attached": "/work/options.md"}
        body = " ".join(f"[{label}]({target})" for label, target in targets.items()) + " and https://machine.example.ts.net/thanksgiving/ bare"
        identifier = self.publish({**delivery(), "links": [{"label": label, "target": target} for label, target in targets.items()]},
                                  body=body, attachments=[attachment])
        self.serve(public_url=PUBLIC)
        port = self.port
        embedded = "/status/embedded?address={}&amp;from=" + identifier
        page = self.request("/status/deliveries/" + identifier, headers=RELAY)[2].decode()
        listing, written = page.split('class="link-list">')[1], page.split('<section class="document">')[1].split("</section>")[0]
        for section in (listing, written):
            with self.subTest(section=section[:40]):
                self.assertIn(f'<a href="{embedded.format("/thanksgiving/")}"', section)
                self.assertIn(f'<a href="{embedded.format("/thanksgiving/menu.html")}"', section)
                self.assertIn(f'<a href="/status/reports/{report_id}"', section)
                self.assertIn(f'<a href="/status/deliveries/{other}"', section)
                self.assertIn(f'<a href="/status/deliveries/{identifier}/attachments/0"', section)
                self.assertIn('href="https://example.com/pull/3"', section)
                self.assertIn('href="agentcoord://thread/abc"', section)
                self.assertNotIn('href="https://machine.example.ts.net/thanksgiving/"', section)       # never straight to the shared origin
                for internal in ("/status/embedded", "/status/reports", "/status/deliveries"):
                    for link in section.split("<a ")[1:]:
                        if link.startswith(f'href="{internal}'):
                            self.assertNotIn("target=", link.split(">")[0])                              # internal targets never open a new tab
        self.assertIn('target="_blank" rel="noreferrer noopener">Website', listing)
        self.assertIn(f'data-path="{existing}"', listing)                           # a file of this machine stays a path to copy
        self.assertIn('data-path="/work/REPORT.md"', listing)
        self.assertIn(f"<code>{existing}</code>", written)
        self.assertIn('>https://machine.example.ts.net/thanksgiving/</a> bare', written)       # a bare address keeps its text and opens embedded
        self.assertEqual(written.count(embedded.format("/thanksgiving/") + '"'), 2)
        attached = self.request(f"/status/deliveries/{identifier}/attachments/0", headers=RELAY)[2].decode()
        self.assertIn(f'<a href="{embedded.format("/thanksgiving/menu")}"', attached)
        local = self.request("/deliveries/" + identifier)[2].decode()
        self.assertIn(f'<a href="/reports/{report_id}"', local)                     # the same page on the address being used
        self.assertIn(f'<a href="/embedded?address=/thanksgiving/&amp;from={identifier}"', local)
        linked = self.publish({**delivery(title="Local link"), "links": [{"label": "Local", "target": f"http://127.0.0.1:{port}/deliveries/{other}"}]})
        self.assertIn(f'<li><a href="/status/deliveries/{other}">Local</a></li>', self.request("/status/deliveries/" + linked, headers=RELAY)[2].decode())

    def test_without_a_public_address_a_bare_path_is_not_an_application(self):
        identifier = self.publish({**delivery(), "links": [{"label": "App", "target": "/thanksgiving/"}]}, body="[App](/thanksgiving/)")
        self.serve()
        page = self.request("/deliveries/" + identifier)[2].decode()
        self.assertNotIn("/embedded?", page)
        self.assertIn('data-path="/thanksgiving/"', page)


class PublicAddressTests(Workspace):
    def test_configured_relay_host_serves_prefixed_links_and_accepts_its_origin(self):
        identifier = self.publish(thread_id="thread-1")
        report_id = self.register(report("Served"), agent="operator")
        self.serve(public_url=PUBLIC)
        relay = {"Host": "machine.example.ts.net", "Origin": "https://machine.example.ts.net"}
        for path in ("/", "/status/"):                           # the relay may or may not remove the prefix
            status, _, content = self.request(path, headers=relay)
            self.assertEqual(status, 200)
            self.assertIn(b'href="/status/style.css"', content)
            self.assertIn(b'data-base="/status"', content)
        status, headers, _ = self.request("/status", headers=relay)
        self.assertEqual((status, headers["Location"]), (308, "/status/"))
        self.assertIn(b'href="/status/"', self.request("/reports/" + report_id, headers=relay)[2])
        self.assertIn(b'src="/status/delivery.js"', self.request("/status/deliveries/" + identifier, headers=relay)[2])
        self.assertIn(b'href="/"', self.request("/reports/" + report_id)[2])       # the local address keeps unprefixed links
        body = {"id": identifier, "action": "dismiss", "note": "From the phone"}
        self.assertEqual(self.request("/status/api/delivery-response", body, headers=relay)[0], 200)
        self.assertEqual(self.request("/api/delivery-response", body, headers={**relay, "Origin": "https://other.example.ts.net"})[0], 403)
        self.assertEqual(self.request("/", headers={"Host": "other.example.ts.net"})[0], 403)
        self.assertTrue(UsageEvents(self.root).read()[0]["remote"])
        self.assertEqual(json.loads(self.request("/health")[2])["public_url"], PUBLIC)

    def test_only_installation_records_the_public_address(self):
        import status_server
        self.assertIsNone(status_server.saved_public_url(self.root))
        status_server.save_public_url(self.root, PUBLIC)
        self.assertEqual(status_server.saved_public_url(self.root), PUBLIC)
        source = (SCRIPTS / "status_server.py").read_text()
        serve = source[source.index('if arguments.command == "serve":'):source.index("else:", source.index('if arguments.command == "serve":'))]
        self.assertNotIn("save_public_url", serve)                 # a development serve must not redirect the installed page's links

    def test_without_a_public_address_only_local_hosts_are_served(self):
        self.serve()
        self.assertEqual(self.request("/", headers={"Host": "machine.example.ts.net"})[0], 403)
        self.assertEqual(self.request("/status/", headers={"Host": f"127.0.0.1:{self.port}"})[0], 404)
        for invalid in ("http://machine.example/status", "https://user@machine.example/status", "https://machine.example/a?b=1",
                        "https://machine.example/<script>"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                public_address(invalid)


class AskTests(Workspace):
    def command(self, body):
        path = self.root / "agent-coord"
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return str(path)

    def test_listing_is_read_through_and_unavailability_is_stated(self):
        records = [{"id": 7, "session_id": "thread-a", "kind": "approval", "question": "Approve the payout\nDetails follow.", "blocking": True,
                    "context": None, "unblocks": "Pricing for 18 actors.", "effort_minutes": 5, "link": None, "due_at": None, "status": "open",
                    "created_at": "2026-11-22T09:00:00+00:00", "thread_title": "HoldCo operator", "project_label": "HoldCo",
                    "cwd": "/work/holdco", "stale": False, "overdue": False, "snoozed": False, "thread_closed": False},
                   {"id": 8, "session_id": "thread-z", "kind": "decision", "question": "Snoozed", "blocking": False, "status": "open",
                    "created_at": "2026-11-22T09:00:00+00:00", "snoozed": True, "cwd": "/elsewhere"},
                   {"id": 9, "session_id": "thread-z", "kind": "decision", "question": "Elsewhere", "blocking": False, "status": "open",
                    "created_at": "2026-11-22T09:00:00+00:00", "snoozed": False, "cwd": "/elsewhere"}]
        listing = self.root / "asks.json"
        listing.write_text(json.dumps(records))
        result = read_asks(self.command(f'[ "$1 $2 $3" = "ask --list --all-sessions" ] || exit 2\ncat "{listing}"\n'))
        self.assertTrue(result["available"])
        self.assertEqual([ask["id"] for ask in result["asks"]], [7, 9])
        self.assertEqual((result["asks"][0]["title"], result["asks"][0]["detail"]), ("Approve the payout", "Details follow."))
        self.assertEqual(result["asks"][0]["thread_link"], "agentcoord://thread/thread-a")
        self.register(report("Operation"), agent="operator", thread_id="thread-a")
        operation = self.reports.operations()["operations"][0]
        self.assertEqual([ask["id"] for ask in for_operation(result["asks"], operation)], [7])
        self.assertFalse((self.root / "asks").exists())             # nothing is copied into the Status store

        older = read_asks(self.command('echo "agent-coord: error: unrecognized arguments: --all-sessions" >&2\nexit 2\n'))
        self.assertEqual((older["available"], older["asks"]), (False, []))
        self.assertIn("does not provide the asks listing yet", older["reason"])
        self.assertFalse(read_asks(self.command("exit 1\n"))["available"])
        self.assertFalse(read_asks(self.command("echo not-json\n"))["available"])
        self.assertFalse(read_asks(str(self.root / "missing-command"))["available"])
        self.assertFalse(read_asks(self.command("sleep 5\n"), timeout=.2)["available"])

    def test_review_and_operation_views_carry_asks_or_the_reason_they_are_missing(self):
        self.register(report("Operation"), agent="operator", thread_id="thread-a")
        ask = {"id": 7, "session_id": "thread-a", "kind": "approval", "title": "Approve", "detail": None, "blocking": True,
               "created_at": "2026-11-22T09:00:00+00:00", "cwd": "/elsewhere", "thread_link": "agentcoord://thread/thread-a"}
        calls = []
        def reader():
            calls.append(1)
            return {"available": True, "reason": None, "asks": [ask]}
        self.serve(ask_reader=AskReader(reader, lifetime=60))
        review = json.loads(self.request("/api/review")[2])
        self.assertEqual((review["asks"]["asks"][0]["id"], review["operations"][0]["ask_count"]), (7, 1))
        operation = json.loads(self.request("/api/operations/" + review["operations"][0]["id"])[2])
        self.assertEqual(len(operation["asks"]["asks"]), 1)
        self.assertEqual(len(calls), 1)                              # one recent listing serves both requests

    def test_title_is_one_line_and_the_whole_question_is_kept(self):
        self.assertEqual(title_and_detail("Short question?"), ("Short question?", None))
        self.assertEqual(title_and_detail("First line\n\n1. Step one\n2. Step two"), ("First line", "1. Step one\n2. Step two"))
        long = "One step is left that only you can do. " + "It blocks pricing and takes ten minutes to finish in the console. " * 3
        title, detail = title_and_detail(long + "\nReply done.")
        self.assertEqual(title, "One step is left that only you can do.")
        self.assertTrue(detail.startswith("It blocks pricing") and detail.endswith("Reply done."))
        self.assertEqual((title + " " + detail).split(), (long + " Reply done.").split())          # no word is dropped
        unbroken = "A" * 300
        self.assertEqual(title_and_detail(unbroken), (unbroken, None))                             # never cut mid-sentence

    def test_listing_carries_choices_and_resolutions_and_refreshes_on_request(self):
        record = {"id": 7, "session_id": "thread-a", "kind": "action", "question": "Verify the payout", "blocking": False, "status": "open",
                  "created_at": "2026-11-22T09:00:00+00:00", "snoozed": False, "cwd": "/work", "options": [],
                  "resolutions": ["done", "not_done", "dismissed"]}
        listing = self.root / "asks.json"
        listing.write_text(json.dumps([record]))
        result = read_asks(self.command(f'cat "{listing}"\n'))
        self.assertEqual((result["asks"][0]["options"], result["asks"][0]["resolutions"]), ([], ["done", "not_done", "dismissed"]))
        calls = []
        def reader():
            calls.append(1)
            return {"available": True, "reason": None, "asks": []}
        self.serve(ask_reader=AskReader(reader, lifetime=60), public_url=PUBLIC)
        self.request("/api/review")
        self.request("/api/review")
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(self.request("/api/review?fresh=asks")[2])["public_url"], PUBLIC)
        self.assertEqual(len(calls), 2)                              # after a resolution the page reads Ribbon Field again
        self.assertFalse((self.root / "asks").exists())

    def test_an_expired_listing_is_served_at_once_while_one_background_read_renews_it(self):
        release, started, calls = threading.Event(), threading.Event(), []
        def reader():
            calls.append(len(calls) + 1)
            if len(calls) == 2:                                      # the renewal is slow, as Ribbon Field sometimes is
                started.set()
                self.assertTrue(release.wait(5))
            return {"available": True, "reason": None, "asks": [{"id": len(calls)}]}
        asks = AskReader(reader, lifetime=0)
        self.addCleanup(release.set)
        self.assertEqual(asks.current()["asks"], [{"id": 1}])        # the first read waits for the command
        began = time.monotonic()
        for _ in range(5):                                           # expired: every read returns the last listing without waiting
            self.assertEqual(asks.current()["asks"], [{"id": 1}])
        self.assertLess(time.monotonic() - began, 1)
        self.assertTrue(started.wait(5))
        self.assertEqual(calls, [1, 2])                              # one renewal, not one per read
        release.set()
        for _ in range(200):
            if asks.current()["asks"] == [{"id": 2}]:
                break
            time.sleep(.01)
        else:
            self.fail("The renewed listing was never served.")
        fresh = AskReader(reader, lifetime=60)
        fresh.current()
        count = len(calls)
        fresh.invalidate()
        self.assertEqual(fresh.current()["asks"], [{"id": count + 1}])     # after invalidate() the next read waits for a new listing

    def test_a_renewal_started_before_a_resolution_never_replaces_the_listing_read_after_it(self):
        release, started, calls = threading.Event(), threading.Event(), []
        def reader():
            calls.append(len(calls) + 1)
            number = len(calls)
            if number == 2:
                started.set()
                self.assertTrue(release.wait(5))
            return {"available": True, "reason": None, "asks": [{"id": number}]}
        asks = AskReader(reader, lifetime=0)
        self.addCleanup(release.set)
        asks.current()
        asks.current()                                               # starts the slow renewal (read 2)
        self.assertTrue(started.wait(5))
        asks.invalidate()                                            # the user resolved an ask while it ran
        self.assertEqual(asks.current()["asks"], [{"id": 3}])
        release.set()
        time.sleep(.05)
        self.assertNotEqual(asks.current()["asks"], [{"id": 2}])     # the earlier read's result was discarded

    def test_resolutions_made_on_the_page_are_measured_without_content(self):
        self.serve(ask_reader=AskReader(lambda: {"available": True, "reason": None, "asks": []}))
        event = {"type": "ask_resolution", "view": "review", "item_kind": "ask", "item": "24", "action": "answered", "narrow": True}
        self.assertEqual(self.request("/api/events", event)[0], 200)
        self.assertEqual(self.request("/api/events", {**event, "action": "snoozed"})[0], 200)
        for invalid in ({**event, "item": "abc"}, {**event, "item": "0"}, {**event, "item_kind": "delivery"},
                        {key: value for key, value in event.items() if key != "action"}, {**event, "action": "an answer with words"},
                        {"type": "page_open", "item_kind": "ask", "item": "24"}):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.request("/api/events", invalid)[0], 400)
        events = UsageEvents(self.root).read()
        self.assertEqual([(entry["type"], entry["item"], entry["action"]) for entry in events],
                         [("ask_resolution", "24", "answered"), ("ask_resolution", "24", "snoozed")])
        now = datetime.now(timezone.utc) + timedelta(minutes=1)
        summary = summarize(self.reports, self.deliveries, events, since=now - timedelta(days=1), until=now, zone=ZoneInfo("UTC"))
        self.assertEqual(summary["asks_resolved_on_page"], {"total": 2, "by_resolution": {"answered": 1, "snoozed": 1}, "narrow_viewport": 2})

    def test_unavailable_asks_do_not_break_the_page(self):
        self.register(report("Operation"), agent="operator")
        self.serve(ask_reader=AskReader(lambda: {"available": False, "reason": "Ribbon Field is not installed.", "asks": []}))
        review = json.loads(self.request("/api/review")[2])
        self.assertEqual(review["asks"], {"available": False, "reason": "Ribbon Field is not installed.", "asks": []})
        self.assertIsNone(review["operations"][0]["ask_count"])


class MetricsTests(Workspace):
    def test_summary_reports_opens_latency_and_outcomes(self):
        now = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)
        usage = UsageEvents(self.root)
        first = self.register(report("First"), agent="operator")
        second = self.register(report("Second"), agent="operator")
        for hours, narrow in ((30, False), (5, True), (4, True)):
            usage.record("page_open", view="review", narrow=narrow, remote=narrow, moment_=now - timedelta(hours=hours))
        for version in (first, second, second):
            usage.record("item_open", view="operation", item_kind="operation", item=version, moment_=now - timedelta(hours=3))
        usage.record("page_open", view="review", moment_=now - timedelta(days=30))        # outside the period

        def delivered(title, hours_ago, state):
            identifier = self.publish({"title": title, "summary": "Summary.", "recommended_default": "Do it."}, thread_id="thread-1")
            path = self.root / "deliveries" / identifier / "delivery.json"
            manifest = json.loads(path.read_text())
            manifest["received_at"] = (now - timedelta(hours=hours_ago)).isoformat()
            path.write_text(json.dumps(manifest))
            if state:
                (self.root / "delivery-state").mkdir(exist_ok=True)
                (self.root / "delivery-state" / (identifier + ".json")).write_text(json.dumps(state))
        at = lambda hours_ago: (now - timedelta(hours=hours_ago)).isoformat()
        delivered("Accepted", 10, {"read_at": at(9), "discussed_at": None, "response": {"type": "accepted", "choice": "recommended_default", "note": None, "at": at(8)},
                                   "history": [{"action": "read", "at": at(9)}, {"action": "accept", "at": at(8)}]})
        delivered("Dismissed", 10, {"read_at": at(7), "discussed_at": None, "response": {"type": "dismissed", "choice": None, "note": None, "at": at(6)},
                                    "history": [{"action": "read", "at": at(7)}, {"action": "dismiss", "at": at(6)}]})
        delivered("Ignored", 40, None)
        delivered("Pending", 2, {"read_at": at(1), "discussed_at": None, "response": None, "history": [{"action": "read", "at": at(1)}]})
        since = now - timedelta(days=7)
        result = summarize(self.reports, self.deliveries, usage.read(since, now), since=since, until=now, zone=ZoneInfo("America/Chicago"))
        self.assertEqual(result["page_opens"]["total"], 3)
        self.assertEqual(result["page_opens"]["per_day"], {"2026-11-21": 1, "2026-11-22": 2})
        self.assertEqual((result["page_opens"]["narrow_viewport"], result["page_opens"]["over_tailnet"]), (2, 2))
        deliveries = result["proactive_deliveries"]
        self.assertEqual(deliveries["counts"], {"accepted": 1, "dismissed": 1, "discussed_only": 0, "ignored": 1, "pending": 1})
        self.assertEqual((deliveries["delivered"], deliveries["opened"]), (4, 3))
        self.assertEqual(deliveries["median_minutes_to_first_open"], 60.0)        # 60, 180 and 60 minutes
        self.assertEqual(deliveries["median_minutes_to_response"], 180.0)         # 120 and 240 minutes
        self.assertEqual((deliveries["share_acted_on"], deliveries["share_dismissed"], deliveries["share_ignored"]), (.25, .25, .25))
        self.assertEqual([(row["title"], row["opens"]) for row in result["operation_report_opens"]], [("HoldCo bridge", 3)])
        command = [sys.executable, "-B", str(SCRIPTS / "status_metrics.py"), "--inbox", str(self.root), "--until", now.isoformat(), "--days", "7"]
        printed = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
        self.assertEqual(printed["page_opens"]["total"], 3)

    def test_empty_period_reports_no_data_instead_of_zero_latency(self):
        now = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)
        result = summarize(self.reports, self.deliveries, [], since=now - timedelta(days=7), until=now, zone=ZoneInfo("UTC"))
        self.assertIsNone(result["proactive_deliveries"]["median_minutes_to_first_open"])
        self.assertIsNone(result["proactive_deliveries"]["share_acted_on"])
        self.assertEqual(result["page_opens"]["total"], 0)
        (self.root / "usage").mkdir()
        (self.root / "usage" / "2026-11.jsonl").write_text('{"at":"2026-11-22T10:00:00+00:00","type":"page_open"}\n{"at": "2026-11-2')
        self.assertEqual(len(UsageEvents(self.root).read()), 1)        # a torn final line is skipped


class MarkdownTests(unittest.TestCase):
    def test_structure_renders_and_untrusted_markup_stays_text(self):
        output = markdown_text.render(
            "# Title\n\nA **strong** point with `code` and <https://example.com/a>.\n\n- one\n  - nested\n- two\n\n"
            "| Name | Price |\n|---|---|\n| Allis | $60 |\n\n```\n<script>x</script>\n```\n\n> quoted\n\n1. first\n2. second\n\n"
            "<script>alert(1)</script> [x](javascript:alert(1)) [ok](https://example.com/?q=1&r=2) [thread](agentcoord://thread/abc)")
        for expected in ("<h2>Title</h2>", "<strong>strong</strong>", "<code>code</code>", "<ul>", "<ol>", "<table>", "<th scope=\"col\">Name</th>",
                         "<blockquote>", "&lt;script&gt;x&lt;/script&gt;", 'href="https://example.com/?q=1&amp;r=2"', 'href="agentcoord://thread/abc"'):
            self.assertIn(expected, output)
        self.assertNotIn("<script>", output)
        self.assertNotIn('href="javascript', output)
        self.assertEqual(output.count("<ul>"), output.count("</ul>"))
        self.assertEqual(output.count("<li>"), output.count("</li>"))


if __name__ == "__main__":
    unittest.main()

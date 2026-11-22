"""Operations, proactive deliveries, read-through asks, public address handling, and usage metrics."""
from datetime import datetime, timedelta, timezone
import http.client
import json
import os
from pathlib import Path
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
import markdown_text
from register_status import register
from ribbon_field_asks import AskReader, for_operation, read_asks, title_and_detail
from status_server import make_server, public_address
from status_store import StatusError, StatusReports
from usage_events import UsageEvents, summarize

PUBLIC = "https://machine.example.ts.net/status"


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

    @staticmethod
    def refuse_resolution(ask_id, body, *, snooze=False):
        raise StatusError("Tests do not resolve asks in Ribbon Field.")

    def serve(self, **arguments):
        arguments.setdefault("ask_resolver", self.refuse_resolution)      # never the real Ribbon Field
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

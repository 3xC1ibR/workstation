"""Optional real-browser regression test; run with Playwright and Chromium installed."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sync_playwright = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_status import render
from register_status import register
from status_server import make_server
from delivery_store import Deliveries, publish as publish_delivery
from document_state import DocumentStates
from ribbon_field_asks import AskReader
from status_store import StatusReports
from test_responses import document
from usage_events import UsageEvents


@unittest.skipUnless(sync_playwright, "Install Playwright and Chromium to run the browser regression")
class ReviewPageBrowserTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.server = make_server(self.root, 0, ask_reader=AskReader(lambda: {"available": True, "reason": None, "asks": [
            {"id": 7, "session_id": "thread-a", "kind": "approval", "title": "Approve the payout", "blocking": True,
             "detail": "First paragraph.\n\nSecond paragraph with https://example.com/console and more.", "options": [],
             "resolutions": ["approved", "declined", "dismissed"],
             "unblocks": "Live payouts.", "created_at": "2026-11-22T09:00:00+00:00", "cwd": "/project", "thread_title": "Operator",
             "thread_link": "agentcoord://thread/thread-a"}]}))
        worker = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        driver = sync_playwright().start()
        self.addCleanup(driver.stop)
        browser = driver.chromium.launch()
        self.addCleanup(browser.close)
        self.page = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="dark")
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
        self.failures = []
        self.page.on("pageerror", lambda error: self.failures.append(str(error)))

    def fits(self):
        self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= innerWidth"))

    def test_delivery_is_read_accepted_with_a_note_and_reopened(self):
        identifier = publish_delivery({"title": "CI is green again", "summary": "Every run had failed since October.",
                                       "recommended_default": "Merge pull request 3.",
                                       "decision": {"question": "Merge it?", "options": ["Hold for changes"]}},
                                      workspace="/project", agent="proactive", thread_id="thread-a", body="# CI is green again\n\nDetails.", root=self.root)
        page, deliveries = self.page, Deliveries(self.root)
        page.goto(self.origin + "/")
        row = page.locator("#deliveries .row")
        expect(row).to_have_attribute("data-state", "unread")
        expect(row).to_contain_text("Recommended: Merge pull request 3.")
        expect(page.locator("#asks .row")).to_contain_text("Approve the payout")
        expect(page.locator("#review-counts")).to_contain_text("1 ask (1 blocking) · 1 delivery to review")
        self.fits()
        row.locator(".row-title").click()
        expect(page.get_by_role("button", name="Do it", exact=True)).to_be_visible()
        expect(page.locator(".document h2")).to_have_count(0)            # the repeated title heading is not shown twice
        expect(page.get_by_role("link", name="Discuss in Ribbon Field")).to_have_attribute("href", "agentcoord://thread/thread-a")
        page.wait_for_function("document.querySelector('time').textContent.includes(',')")
        self.assertTrue(deliveries.record(identifier)["read_at"])
        page.get_by_role("button", name="Add a note", exact=True).click()
        page.get_by_label("Note for the agent").fill("After Tuesday")
        page.get_by_role("button", name="Hold for changes", exact=True).click()
        expect(page.locator(".response-outcome")).to_contain_text("Accepted")
        response = deliveries.record(identifier)["response"]
        self.assertEqual((response["type"], response["choice"], response["note"]), ("accepted", "Hold for changes", "After Tuesday"))
        self.fits()
        page.get_by_role("link", name="Review", exact=True).click()
        expect(page.locator("#deliveries")).to_be_hidden()                 # responded items leave the Open view
        page.get_by_role("radio", name="Done", exact=True).check()
        done = page.locator("#deliveries .row")
        expect(done).to_contain_text("Accepted")
        done.get_by_role("button", name="Reopen", exact=True).focus()
        done.get_by_role("button", name="Reopen", exact=True).click()
        expect(page.locator("#deliveries")).to_be_hidden()
        self.assertIsNone(deliveries.record(identifier)["response"])
        events = [(event["type"], event["action"]) for event in UsageEvents(self.root).read()]
        self.assertIn(("page_open", None), events)
        self.assertIn(("item_open", None), events)
        self.assertIn(("response", "accept"), events)
        self.assertEqual(self.failures, [])

    def test_ask_is_read_in_full_and_resolved_through_ribbon_field(self):
        page, sent = self.page, []
        state = {"paired": True, "fail": False}
        def ribbon_field(route):
            request = route.request
            if request.url.endswith("/api/browser/config"):
                if not state["paired"]:
                    return route.fulfill(status=401, content_type="application/json", body='{"error": "Pair this device using a fresh link from your Mac."}')
                return route.fulfill(content_type="application/json", body='{"token": "ribbon-field-token", "askKinds": true}')
            if state["fail"]:
                return route.fulfill(status=400, content_type="application/json", body='{"error": "Option is not one of the offered choices."}')
            sent.append((request.url.split("/api/browser/")[1], request.headers.get("x-agent-coord-token"), json.loads(request.post_data)))
            route.fulfill(content_type="application/json", body='{"id": 7, "status": "resolved"}')
        page.route("**/api/browser/**", ribbon_field)
        page.goto(self.origin + "/")
        row = page.locator("#asks .row")
        expect(row.locator(".ask-detail")).to_be_hidden()
        row.locator(".ask-toggle").click()
        expect(row.locator(".ask-text").first).to_contain_text("Second paragraph with https://example.com/console")
        expect(row.locator(".ask-text a")).to_have_attribute("href", "https://example.com/console")
        expect(row.locator(".row-summary")).to_be_hidden()               # the preview gives way to the whole text
        note = row.locator(".ask-note")
        note.fill("Only after Tuesday")
        state["fail"] = True
        row.get_by_role("button", name="Approve", exact=True).click()
        expect(row.get_by_role("alert")).to_contain_text("not one of the offered choices")
        expect(note).to_have_value("Only after Tuesday")                 # a refused resolution keeps the note
        state["fail"] = False
        row.get_by_role("button", name="Approve", exact=True).click()
        expect(page.locator("#review-notice")).to_contain_text("Approved")
        self.assertEqual(sent, [("asks/7", "ribbon-field-token", {"resolution": "approved", "note": "Only after Tuesday"})])
        self.assertEqual([(event["type"], event["item"], event["action"]) for event in UsageEvents(self.root).read() if event["type"] == "ask_resolution"],
                         [("ask_resolution", "7", "approved")])
        self.assertFalse((self.root / "asks").exists())
        self.fits()
        state["paired"] = False
        page.goto(self.origin + "/")
        page.locator("#asks .ask-toggle").click()
        expect(page.locator(".ask-unavailable")).to_contain_text("not paired")
        expect(page.locator("#asks .ask-links a").first).to_have_attribute("href", "agentcoord://thread/thread-a")
        self.assertEqual(self.failures, [])

    def test_operation_is_unread_until_its_latest_version_is_opened(self):
        first = {"title": "HoldCo bridge", "subject": "operator", "summary": "First version.", "generated_at": "2026-11-22T10:00:00Z"}
        second = {**first, "summary": "Second version."}
        register(first, render(first), workspace="/project", agent="operator", thread_id="thread-a", root=self.root)
        latest = register(second, render(second), workspace="/project", agent="operator", thread_id="thread-a", root=self.root)
        page = self.page
        page.goto(self.origin + "/")
        row = page.locator("#operations .row")
        expect(row).to_have_count(1)
        expect(row).to_have_attribute("data-state", "unread")
        expect(row).to_contain_text("Second version.")
        expect(row).to_contain_text("1 ask open")
        row.locator(".row-title").click()
        expect(page.locator(".version-history summary")).to_have_text("Version 2 of 2")
        expect(page.locator("#operation-asks")).to_contain_text("Approve the payout")
        self.fits()
        page.locator(".version-history summary").click()
        page.get_by_role("link", name="Version 1", exact=True).click()
        expect(page.locator(".version-notice")).to_contain_text("You are reading version 1 of 2")
        expect(page.locator(".assessment")).to_have_text("First version.")
        page.get_by_role("link", name="Review", exact=True).click()
        expect(page.locator("#operations .row")).to_have_attribute("data-state", "read")
        page.goto(self.origin + "/reports/" + latest)
        page.get_by_role("button", name="Dismiss", exact=True).click()
        expect(page.get_by_role("button", name="Restore to Review", exact=True)).to_be_visible()
        page.goto(self.origin + "/")
        expect(page.locator("#operations")).to_be_hidden()
        self.assertEqual(self.failures, [])

    def test_report_answers_detect_a_competing_edit_and_keep_unsaved_input(self):
        report = document()
        identifier = register(report, render(report), workspace="/project", agent="release-owner", root=self.root)
        page = self.page
        page.goto(self.origin + "/reports/" + identifier)
        owner = page.locator('input[name="owner"]')
        expect(owner).to_be_visible()
        expect(page.locator('.response-editor [role="status"]')).not_to_contain_text("Loading")
        page.get_by_role("button", name="Save responses", exact=True).click()
        expect(page.locator('.response-editor [role="alert"]')).to_contain_text("required")
        proceed = page.get_by_role("combobox", name="Proceed?")
        expect(proceed).to_be_focused()
        proceed.press("End")
        proceed.press("Enter")
        owner.fill("Release manager")
        page.get_by_role("button", name="Save responses", exact=True).click()
        expect(page.locator('.response-editor [role="status"]')).to_contain_text("The agent can read")
        owner.fill("Unsaved draft")
        StatusReports(self.root).save_responses(identifier, {"proceed": True, "owner": "Other page"}, 1)   # a second editor
        page.get_by_role("button", name="Save responses", exact=True).click()
        expect(page.locator('.response-editor [role="alert"]')).to_contain_text("another page")
        expect(owner).to_have_value("Unsaved draft")
        page.get_by_role("button", name="Discard edits and reload", exact=True).click()
        expect(owner).to_have_value("Other page")
        self.fits()
        self.assertEqual(self.failures, [])


    def interactive_document(self, other):
        """An agent-built document that uses the bridge and also tries what the sandbox must refuse."""
        return f"""<!doctype html><html><head><meta charset="utf-8"><title>Plan</title>
<script src="{self.origin}/document_bridge.js"></script></head><body>
<div id="content" style="height: 900px">Plan</div>
<p id="state">waiting</p><p id="attempts">running</p>
<button id="save">Save</button><button id="propose">Propose</button><button id="invent">Invent</button><button id="grow">Grow</button>
<a id="other" href="/deliveries/{other}">Other delivery</a><a id="scripted" href="javascript:void(document.title = 'ran')">Scripted</a>
<script>
const show = (id, text) => {{ document.getElementById(id).textContent = text; }};
const identifier = location.pathname.split("/")[2], service = "{self.origin}";
StatusDocument.loadState().then(({{state}}) => show("state", "loaded " + JSON.stringify(state)), error => show("state", "unavailable"));
document.getElementById("save").onclick = () => StatusDocument.saveState({{picked: "B"}}).then(() => show("state", "saved"), () => show("state", "refused"));
document.getElementById("propose").onclick = () => StatusDocument.propose({{action: "accept", choice: "Hold for changes", note: "From the plan"}});
document.getElementById("invent").onclick = () => {{
  parent.postMessage({{type: "status:propose", action: "accept", choice: "Invented option"}}, "*");
  parent.postMessage({{type: "status:record", action: "accept"}}, "*");
  parent.postMessage("status:propose", "*");
  show("state", "invented");
}};
document.getElementById("grow").onclick = () => {{ document.getElementById("content").style.height = "30000px"; }};
(async () => {{
  const results = [], attempt = async (name, action) => {{ try {{ results.push(name + ":" + await action()); }} catch {{ results.push(name + ":blocked"); }} }};
  const response = JSON.stringify({{id: identifier, action: "accept", choice: "recommended_default"}});
  await attempt("config", async () => (await (await fetch(service + "/api/config")).json()).token ? "read" : "empty");
  await attempt("respond", async () => (await fetch(service + "/api/delivery-response", {{method: "POST", headers: {{"Content-Type": "application/json"}}, body: response}})).status);
  await attempt("simple", async () => (await fetch(service + "/api/delivery-response", {{method: "POST", mode: "no-cors", body: response}})).type);
  await attempt("state", async () => (await fetch(service + "/api/document-state", {{method: "POST", mode: "no-cors", body: JSON.stringify({{kind: "delivery", id: identifier, state: 1}})}})).type);
  await attempt("page", async () => parent.document.title);
  await attempt("cookie", async () => document.cookie);
  await attempt("storage", async () => localStorage.length);
  await attempt("top", async () => {{ if (top === window) return "self"; top.location.href = service + "/"; return "navigated"; }});
  show("attempts", results.join(" "));
}})();
</script></body></html>"""

    def test_interactive_document_is_sandboxed_and_reaches_the_page_only_through_the_bridge(self):
        other = publish_delivery({"title": "Other delivery", "summary": "Linked from the plan."}, workspace="/project", root=self.root)
        identifier = publish_delivery({"title": "Thanksgiving plan", "summary": "Pick a menu.", "recommended_default": "Book the turkey.",
                                       "decision": {"question": "Which?", "options": ["Hold for changes"]}},
                                      workspace="/project", agent="proactive", interactive_document=self.interactive_document(other), root=self.root)
        page, deliveries, states = self.page, Deliveries(self.root), DocumentStates(self.root)
        refused = "config:blocked respond:blocked simple:blocked state:blocked page:blocked cookie:blocked storage:blocked top:blocked"
        page.goto(f"{self.origin}/deliveries/{identifier}")
        host = page.locator("#embedded-document")
        expect(host).to_have_attribute("sandbox", "allow-scripts allow-forms allow-modals allow-popups allow-downloads")
        document = page.frame_locator("#embedded-document")
        expect(document.locator("#state")).to_have_text("loaded null")              # nothing saved yet, answered by the page
        expect(document.locator("#attempts")).to_have_text(refused)
        self.assertEqual(page.url, f"{self.origin}/deliveries/{identifier}")         # the document could not navigate the page
        page.wait_for_function("document.getElementById('embedded-document').offsetHeight >= 900")      # sized to its content
        before = page.evaluate("document.getElementById('embedded-document').offsetHeight")
        page.evaluate("window.postMessage({type: 'status:resize', height: 5000}, '*')")                 # not from the item's frame: ignored
        page.evaluate("window.postMessage({type: 'status:propose', action: 'accept'}, '*')")
        document.locator("#grow").click()
        page.wait_for_function("document.getElementById('embedded-document').offsetHeight === 20000")   # clamped
        self.assertGreaterEqual(before, 900)
        self.assertLess(before, 5000)
        self.fits()
        document.locator("#save").click()
        expect(document.locator("#state")).to_have_text("saved")
        self.assertEqual(states.read(identifier)["state"], {"picked": "B"})
        self.assertEqual(states.read(identifier)["version"], identifier)
        document.locator("#invent").click()                                          # an option the delivery does not offer, an unknown type, a bare string
        expect(document.locator("#state")).to_have_text("invented")
        page.wait_for_timeout(300)
        expect(page.locator(".response-proposal")).to_have_count(0)
        page.wait_for_timeout(1000)                                                  # proposals are accepted at most once a second
        document.locator("#propose").click()
        proposal = page.locator(".response-proposal")
        expect(proposal).to_contain_text("The document proposes: accept “Hold for changes”.")
        expect(proposal).to_contain_text("With the note: From the plan")
        expect(proposal.get_by_role("button", name="Confirm", exact=True)).to_be_enabled()
        record = deliveries.record(identifier)
        self.assertIsNone(record["response"])                                        # the proposal alone recorded nothing
        self.assertEqual([event["action"] for event in record["history"]], ["read"])
        proposal.get_by_role("button", name="Ignore", exact=True).click()
        expect(page.locator(".response-proposal")).to_have_count(0)
        self.assertIsNone(deliveries.record(identifier)["response"])
        page.wait_for_timeout(1000)
        document.locator("#propose").click()
        page.locator(".response-proposal").get_by_role("button", name="Confirm", exact=True).click()
        expect(page.locator(".response-outcome")).to_contain_text("Accepted")
        response = deliveries.record(identifier)["response"]
        self.assertEqual((response["type"], response["choice"], response["note"], response["version"]),
                         ("accepted", "Hold for changes", "From the plan", identifier))
        page.reload()
        document = page.frame_locator("#embedded-document")
        expect(document.locator("#state")).to_have_text('loaded {"picked":"B"}')    # saved state returns through the page
        document.locator("#scripted").click()                                        # a javascript: address is never handed to the page
        page.wait_for_timeout(200)
        self.assertEqual(page.title(), "Thanksgiving plan")
        document.locator("#other").click()                                           # a page of the review page opens in this tab
        expect(page.locator("h1")).to_have_text("Other delivery")
        self.assertEqual(page.url, f"{self.origin}/deliveries/{other}")
        self.assertEqual(len(page.context.pages), 1)
        page.goto(f"{self.origin}/deliveries/{identifier}/interactive")              # opened directly, it still has no origin
        expect(page.locator("#attempts")).to_contain_text("config:blocked respond:blocked simple:blocked state:blocked")
        expect(page.locator("#attempts")).to_contain_text("cookie:blocked storage:blocked")
        expect(page.locator("#state")).to_have_text("unavailable")
        record = deliveries.record(identifier)
        self.assertEqual([event["action"] for event in record["history"]], ["read", "accept"])
        self.assertEqual(states.read(identifier)["revision"], 1)
        events = [(event["type"], event["action"]) for event in UsageEvents(self.root).read()]
        self.assertIn(("item_open", "interactive_document"), events)
        self.assertEqual(self.failures, [])

    def test_a_document_that_loads_before_the_page_listens_is_still_sized_and_answered(self):
        other = publish_delivery({"title": "Other delivery", "summary": "Linked from the plan."}, workspace="/project", root=self.root)
        identifier = publish_delivery({"title": "Thanksgiving plan", "summary": "Pick a menu."}, workspace="/project",
                                      interactive_document=self.interactive_document(other), root=self.root)
        page = self.page
        def delayed(route):
            page.wait_for_timeout(1500)                                              # the document finishes loading first
            route.continue_()
        page.route("**/embedded_host.js", delayed)
        page.goto(f"{self.origin}/deliveries/{identifier}")
        document = page.frame_locator("#embedded-document")
        expect(document.locator("#state")).to_have_text("loaded null")
        page.wait_for_function("document.getElementById('embedded-document').offsetHeight >= 900")
        self.assertEqual(self.failures, [])

    def test_a_newer_version_reopens_the_row_and_names_the_version_he_answered(self):
        first = publish_delivery({"title": "Thanksgiving plan", "summary": "First plan.", "recommended_default": "Book the turkey."},
                                 workspace="/project", agent="proactive", key="thanksgiving-plan", root=self.root)
        page, deliveries = self.page, Deliveries(self.root)
        page.goto(f"{self.origin}/deliveries/{first}")
        page.get_by_role("button", name="Do it", exact=True).click()
        expect(page.locator(".response-outcome")).to_contain_text("Accepted")
        expect(page.locator(".version-history")).to_have_count(0)                    # a single version has no version menu
        second = publish_delivery({"title": "Thanksgiving plan", "summary": "Second plan.", "recommended_default": "Book the ham."},
                                  workspace="/project", agent="proactive", key="thanksgiving-plan", root=self.root)
        page.goto(self.origin + "/")
        row = page.locator("#deliveries .row")
        expect(row).to_have_count(1)                                                 # one row for the delivery, back in Open
        expect(row).to_have_attribute("data-state", "unread")
        expect(row).to_contain_text("Accepted version 1")
        expect(row).to_contain_text("Second plan.")
        self.fits()
        row.locator(".row-title").click()
        expect(page.locator(".version-history summary")).to_have_text("Version 2 of 2")
        expect(page.locator(".response-version")).to_have_text("You accepted version 1; this is version 2.")
        expect(page.get_by_role("button", name="Change response", exact=True)).to_be_visible()
        expect(page.locator(".recommendation")).to_contain_text("Book the ham.")
        self.fits()
        page.locator(".version-history summary").click()
        page.get_by_role("link", name="Version 1", exact=True).click()
        expect(page.locator(".version-notice")).to_contain_text("You are reading version 1 of 2")
        expect(page.get_by_role("button", name="Change response", exact=True)).to_have_count(0)      # responses are given on the latest version
        page.get_by_role("link", name="Open the latest version").first.click()
        page.get_by_role("button", name="Change response", exact=True).click()
        page.get_by_role("button", name="Do it", exact=True).click()
        expect(page.locator(".response-outcome")).to_contain_text("Accepted")
        expect(page.locator(".response-version")).to_have_count(0)
        record = deliveries.record(second)
        self.assertEqual((record["response"]["version"], record["unread"]), (second, False))
        page.get_by_role("link", name="Review", exact=True).click()
        expect(page.locator("#deliveries")).to_be_hidden()                           # answered and read: it leaves Open
        self.assertEqual(self.failures, [])


@unittest.skipUnless(sync_playwright, "Install Playwright and Chromium to run the browser regression")
class ReportPageBrowserTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.server = make_server(self.root / "inbox", 0)
        worker = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        driver = sync_playwright().start()
        self.addCleanup(driver.stop)
        self.browser = driver.chromium.launch()
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="dark")
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))

    def save_in_page(self, owner):
        page = self.page
        expect(page.locator('input[name="owner"]')).to_be_visible()
        expect(page.locator('.response-editor [role="status"]')).not_to_contain_text("Loading")
        page.locator('input[name="owner"]').fill(owner)
        page.locator('input[name="limit"]').fill("0")
        proceed = page.get_by_role("combobox", name="Proceed?")
        proceed.press("End")
        proceed.press("Enter")
        page.get_by_role("button", name="Save responses", exact=True).click()
        expect(page.locator('.response-editor [role="status"]')).to_contain_text("The agent can read")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        self.assertEqual(self.errors, [])

    def test_served_report_edits_saves_and_reloads_in_place(self):
        report = document()
        identifier = register(report, render(report), workspace="/project", root=self.root / "inbox", viewer_url=self.origin)
        self.page.goto(self.origin + "/reports/" + identifier)
        self.save_in_page("Report release manager")
        self.assertEqual(self.page.url, self.origin + "/reports/" + identifier)
        response = StatusReports(self.root / "inbox").responses(identifier)
        self.assertEqual(response["values"], {"owner": "Report release manager", "limit": 0, "proceed": False})
        self.page.reload()
        expect(self.page.locator('input[name="owner"]')).to_have_value("Report release manager")

    def test_portable_file_saves_to_agent_store_and_preserves_failed_input(self):
        source = self.root / "source.json"
        source.write_text(json.dumps(document()))
        output = self.root / "report.html"
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        receipt = subprocess.check_output([sys.executable, "-B", str(scripts / "build_status.py"), str(source),
            "--output", str(output), "--viewer-url", self.origin, "--workspace", "/project"], text=True,
            env={**os.environ, "AGENT_STATUS_INBOX": str(self.root / "inbox")})
        identifier = receipt.split("Status inbox receipt: ")[1].splitlines()[0]
        self.page.goto(output.as_uri())
        self.save_in_page("Portable release manager")
        command = [sys.executable, "-B", str(scripts / "read_responses.py"), "--inbox", str(self.root / "inbox"), "--report", identifier]
        answers = json.loads(subprocess.check_output(command, text=True))["responses"][0]
        self.assertEqual(answers["values"]["owner"], "Portable release manager")
        self.page.reload()
        expect(self.page.locator('input[name="owner"]')).to_have_value("Portable release manager")
        self.page.locator('input[name="owner"]').fill("Unsaved portable edit")
        self.page.route("**/api/report-responses/*", lambda route: route.abort("failed"))
        self.page.get_by_role("button", name="Save responses", exact=True).click()
        expect(self.page.locator('.response-editor [role="alert"]')).to_contain_text("Could not reach")
        expect(self.page.locator('input[name="owner"]')).to_have_value("Unsaved portable edit")
        self.assertEqual(StatusReports(self.root / "inbox").responses(identifier)["values"]["owner"], "Portable release manager")


if __name__ == "__main__":
    unittest.main()

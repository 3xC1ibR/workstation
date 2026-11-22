"""Optional real-browser regression test; run with Playwright and Chromium installed."""
from pathlib import Path
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
from status_store import StatusReports
from test_responses import document


@unittest.skipUnless(sync_playwright, "Install Playwright and Chromium to run the browser regression")
class ResponseBrowserTests(unittest.TestCase):
    def test_answer_round_trip_conflict_and_refresh_preserve_input(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        report = document()
        identifier = register(report, render(report), workspace="/project", agent="release-owner", root=root)
        server = make_server(root, 0)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        driver = sync_playwright().start()
        self.addCleanup(driver.stop)
        browser = driver.chromium.launch()
        self.addCleanup(browser.close)
        context = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark")
        page = context.new_page()
        failures = []
        page.on("pageerror", lambda error: failures.append(str(error)))
        page.goto(f"http://127.0.0.1:{server.server_port}/")
        row = page.locator(f'[data-report-id="{identifier}"]')
        row.locator("summary").click()
        owner = row.locator('input[name="owner"]')
        expect(owner).to_be_visible()
        row.get_by_role("button", name="Save responses", exact=True).click()
        expect(row.get_by_role("alert")).to_contain_text("required")
        proceed = row.get_by_role("combobox", name="Proceed?")
        expect(proceed).to_be_focused()
        proceed.press("End")
        proceed.press("Enter")
        owner.fill("Release manager")
        row.locator('input[name="limit"]').fill("0")
        row.locator("textarea").fill("Preserve the trial budget.")
        row.get_by_role("button", name="Save responses", exact=True).click()
        expect(row.get_by_role("status")).to_contain_text("The agent can read")
        self.assertEqual(StatusReports(root).responses(identifier)["values"]["proceed"], False)
        self.assertEqual(StatusReports(root).responses(identifier)["values"]["limit"], 0)
        owner.fill("Unsaved draft")
        page.evaluate('document.querySelector("input[name=owner]").dataset.retained="yes"')
        another = {"title": "Other report", "subject": "Other agent", "summary": "Complete",
                   "generated_at": "2026-11-21T19:00:00Z"}
        register(another, render(another), workspace="/other-project", root=root)
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(page.locator(".collection-row")).to_have_count(2)
        expect(owner).to_have_value("Unsaved draft")
        expect(owner).to_have_attribute("data-retained", "yes")
        # Model a second editor through the same storage API used by the server.
        StatusReports(root).save_responses(identifier, {"proceed": True, "owner": "Other page"}, 1)
        row.get_by_role("button", name="Save responses", exact=True).click()
        expect(row.get_by_role("alert")).to_contain_text("another page")
        expect(owner).to_have_value("Unsaved draft")
        row.get_by_role("button", name="Discard edits and reload", exact=True).click()
        expect(owner).to_have_value("Other page")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        self.assertEqual(page.evaluate("getComputedStyle(document.body).backgroundColor"), "rgb(255, 255, 255)")
        page.reload()
        row.locator("summary").click()
        expect(owner).to_have_value("Other page")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()

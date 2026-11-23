#!/usr/bin/env python3
"""Serve the standalone review page for operations and proactive work, with optional startup management."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

from delivery_store import Deliveries
from document_state import DocumentStates
import interactive_documents
from register_status import inbox_directory
from response_access import response_key
import review_pages
from ribbon_field_asks import AskReader, for_operation, queue_message, reply_to_ask, resolve_ask, shared_workspaces
from status_store import REPORT_CSP, ResponseConflict, StatusError, StatusReports
from usage_events import INTERACTIVE_OPEN, UsageEvents

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SERVICE = "workstation-status"
LABEL = "com.workstation.status"
DEFAULT_PORT = 8766
VERSION = 5
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src data:; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
FILES = {"/tokens.css": "text/css", "/style.css": "text/css", "/review.css": "text/css", "/controls.js": "text/javascript",
         "/responses.js": "text/javascript", "/report.js": "text/javascript", "/review.js": "text/javascript",
         "/report_page.js": "text/javascript", "/delivery.js": "text/javascript", "/asks.js": "text/javascript",
         "/embedded_host.js": "text/javascript", "/document_bridge.js": "text/javascript", "/selection_messages.js": "text/javascript"}
DOCUMENT_HELPER = "/document_bridge.js"            # loaded by sandboxed documents, whose origin is opaque
POSTS = {"/api/dismiss": ({"id", "dismissed"}, set(), 4096),
         "/api/responses": ({"id", "revision", "values"}, set(), 4 * 1024 * 1024),
         "/api/delivery-response": ({"id", "action"}, {"choice", "note"}, 16 * 1024),
         "/api/document-state": ({"kind", "id", "state"}, set(), 80 * 1024),
         "/api/events": ({"type"}, {"view", "item_kind", "item", "action", "narrow"}, 4096),
         "/api/ask-resolution": ({"id", "body"}, {"snooze"}, 16 * 1024),
         "/api/ask-reply": ({"id", "text"}, set(), 32 * 1024),
         "/api/item-message": ({"kind", "id", "message"}, set(), 64 * 1024)}


def page_policy(public):
    """The policy of the service's own pages: they may frame this origin and the public one, and nothing else loosens."""
    return PAGE_CSP + "; frame-src 'self'" + (" " + public[0] if public else "")


def public_address(value):
    """Split the address another device uses into (origin, host, path prefix)."""
    if not value:
        return None
    address = urlsplit(value)
    if (address.scheme != "https" or not address.hostname or address.username or address.password
            or address.query or address.fragment or not all(part.replace("-", "").replace("_", "").isalnum()
                                                            for part in address.path.strip("/").split("/") if part)):
        raise ValueError("The public address must be an HTTPS address with an optional plain path, such as https://host.example/status.")
    return f"https://{address.netloc}", address.netloc, address.path.rstrip("/")


def make_server(root, port=DEFAULT_PORT, *, public_url=None, ask_reader=None, ask_resolver=resolve_ask, ask_replier=reply_to_ask,
                message_sender=queue_message):
    root = Path(root).resolve()
    reports, deliveries, usage, states = StatusReports(root), Deliveries(root), UsageEvents(root), DocumentStates(root)
    asks = ask_reader or AskReader()
    token = secrets.token_urlsafe(32)
    public = public_address(public_url)
    policy = page_policy(public)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, message, *arguments):
            # Keep the service log for failures rather than continual refreshes.
            if arguments and str(arguments[1] if len(arguments) > 1 else "").startswith(("4", "5")):
                super().log_message(message, *arguments)

        def send(self, status, content, content_type="application/json", *, policy=policy, cors=False, location=None,
                 framing="DENY", readers="same-origin"):
            """`framing` and `readers` loosen only for a sandboxed document and for the helper such documents load."""
            if not isinstance(content, bytes):
                content = json.dumps(content, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", policy)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", framing)
            self.send_header("Cross-Origin-Resource-Policy", readers)
            self.send_header("Referrer-Policy", "no-referrer")
            if readers == "cross-origin":
                self.send_header("Access-Control-Allow-Origin", "*")
            if location:
                self.send_header("Location", location)
            if cors and self.headers.get("Origin"):
                self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Status-Report-Token")
            try:
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(content)
            except ConnectionError:
                self.close_connection = True         # the reader left before the answer; nothing remains to send

        def local_hosts(self):
            return {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def remote(self):
            """True for a request relayed from the configured public address."""
            return bool(public) and self.headers.get("Host") == public[1]

        def accepted_host(self):
            return self.headers.get("Host") in self.local_hosts() or self.remote()

        def base(self):
            return public[2] if self.remote() else ""

        def route(self):
            """The request path without the public prefix, whether or not the relay removed it."""
            path = urlsplit(self.path).path
            prefix = self.base()
            if prefix and (path == prefix or path.startswith(prefix + "/")):
                path = path[len(prefix):] or "/"
            return path

        def trusted_origin(self):
            origin = self.headers.get("Origin")
            return origin in {"http://" + host for host in self.local_hosts()} or (bool(public) and origin == public[0])

        def report_access(self, identifier):
            try:
                reports._manifest(identifier)
                key = response_key(reports.root, identifier)
                return secrets.compare_digest(self.headers.get("X-Status-Report-Token", ""), key)
            except (ValueError, OSError):
                return False

        def public_url(self):
            return public[0] + public[2] if public else None

        def addresses(self):
            """Link handling for the address this request arrived on."""
            port = self.server.server_port
            return review_pages.Addresses(self.base(), public, {f"http://127.0.0.1:{port}", f"http://localhost:{port}"})

        def frame_source(self, interactive, route):
            """Where the frame of an item's interactive document loads from; None when this address cannot show it."""
            if interactive["kind"] == "document":
                return f"{self.base()}{route}/interactive"
            try:
                interactive_documents.validate_address(interactive["address"], public[2] if public else "")
            except ValueError:
                return None                         # no public address, or the path belongs to the review page itself
            return public[0] + interactive["address"] if self.remote() else None

        def send_interactive_document(self, content):
            """Agent-built HTML: always under the sandbox policy, so it never has this origin, in a frame or in a tab."""
            self.send(200, content.encode("utf-8"), "text/html", policy=interactive_documents.DOCUMENT_POLICY, framing="SAMEORIGIN")

        def with_replies(self, listing):
            """Mark asks the user replied to from this page: the time of the last reply event, nothing about its words."""
            if not listing["asks"]:
                return listing
            replied = {}
            for event in usage.read():
                if event["type"] == "ask_resolution" and event.get("action") == "replied":
                    replied[str(event.get("item"))] = event["at"]
            return {**listing, "asks": [{**ask, "replied_at": replied.get(str(ask["id"]))} for ask in listing["asks"]]}

        def review(self):
            operations, delivered, listing = reports.operations(), deliveries.list(), self.with_replies(asks.current())
            for delivery in delivered["deliveries"]:
                delivery.pop("document_state")       # the list needs no document data; agents read it with read_responses.py
            shared = shared_workspaces(operations["operations"])
            for operation in operations["operations"]:
                operation["ask_count"] = len(for_operation(listing["asks"], operation, shared)) if listing["available"] else None
                operation["version_count"] = len(operation.pop("versions"))
            return {"operations": operations["operations"], "deliveries": delivered["deliveries"], "asks": listing,
                    "unreadable": operations["unreadable"] + delivered["unreadable"], "public_url": self.public_url()}

        def conversation(self, kind, identifier):
            """The Ribbon Field conversation of the agent behind an item: an operation's latest publisher, a delivery's thread."""
            if kind == "report":
                manifest = reports._manifest(identifier)
                latest = reports._manifest(reports.operation(manifest["operation_id"])["latest"])
                session = latest["origin"].get("thread_id") or manifest["origin"].get("thread_id")
            elif kind == "delivery":
                thread = self.delivery_version(identifier).get("thread") or ""
                session = thread.removeprefix("agentcoord://thread/") if thread.startswith("agentcoord://thread/") else None
            else:
                raise ValueError("Messages go to a report's or a delivery's conversation.")
            if not session:
                raise ValueError("This item has no Ribbon Field conversation to send to.")
            return session

        def report_page(self, identifier):
            manifest = reports._manifest(identifier)
            document = reports.document(identifier)
            if document is None:
                return reports.content(identifier), REPORT_CSP          # retained HTML only: never run its scripts
            from build_status import render
            base, operation = self.base(), reports.operation(manifest["operation_id"])
            fields, interactive = document.get("response_fields"), manifest["interactive"]
            latest = operation["latest"] == identifier
            configuration = {"report": identifier, "operation": operation["id"], "latest": latest,
                             "dismissed": bool(manifest["dismissed_at"])}
            try:
                session = self.conversation("report", identifier)
            except ValueError:
                session = None
            if session:
                # What a selection message needs: where it goes, and how the agent publishes a new version of this report.
                origin = manifest["origin"]
                number = len(operation["versions"]) - [v["id"] for v in operation["versions"]].index(identifier)
                configuration["conversation"] = {
                    "session": session, "link": "agentcoord://thread/" + session, "title": manifest["title"], "version": number,
                    "generated_at": manifest["generated_at"], "operation_key": origin.get("operation"),
                    "workspace": origin.get("workspace"), "agent": origin.get("agent"),
                    "document": str(reports.root / "reports" / identifier / "report.json"),
                    "address": (self.public_url() or f"http://127.0.0.1:{port}") + "/reports/" + identifier}
            if fields:
                configuration["responses"] = {"fields": fields, "connection": {
                    "id": identifier, "url": f"{base}/api/report-responses/{identifier}",
                    "token": response_key(reports.root, identifier, create=True)}}
            embedded = ""
            if interactive:
                configuration["embedded"] = {"kind": "report", "item": identifier, "latest": latest, "public_url": self.public_url()}
                embedded = review_pages.interactive_section(
                    interactive, self.frame_source(interactive, "/reports/" + identifier), manifest["title"],
                    f"{self.public_url()}/reports/{identifier}" if public else None, "report")
            scripts = (("controls.js",) + (("responses.js", "report.js") if fields else ()) + ("asks.js", "report_page.js", "selection_messages.js")
                       + (("embedded_host.js",) if interactive else ()))
            # Earlier versions, newest first, give the measures their trend and their value last time.
            later = [version["id"] for version in operation["versions"]]
            previous = [earlier for earlier in (reports.document(version) for version in later[later.index(identifier) + 1:][:20])
                        if earlier is not None]
            return render(document, previous=previous, page={"base": base, "scripts": scripts, "configuration": configuration,
                                          "navigation": review_pages.report_navigation(base, operation, identifier),
                                          "after_header": review_pages.OPERATION_ASKS, "after_responses": embedded,
                                          "resolve": lambda target: self.addresses().internal(target, identifier)}), policy

        def delivery_page(self, record):
            interactive, embedded = record["interactive"], ""
            if interactive:
                embedded = review_pages.interactive_section(
                    interactive, self.frame_source(interactive, "/deliveries/" + record["id"]), record["title"],
                    self.public_url() + review_pages.delivery_route(record["series"], record["id"], record["latest"]) if public else None,
                    "delivery")
            return review_pages.delivery_page(self.addresses(), record, deliveries.document(record["id"]), embedded, self.public_url())

        def delivery_version(self, identifier):
            """The version a delivery address shows: the latest of the series it names, or the one ?version= names.

            A series continued with --replaces has the identifier of its first version, so that identifier alone
            names the delivery as it now stands; an earlier version is always addressed with ?version=.
            """
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            record, wanted = deliveries.record(identifier), query.get("version", [None])[0]
            if wanted is None:
                return record
            version = deliveries.version(wanted)
            if version["id"] != wanted or version["series"] != record["series"]:
                raise StatusError("This delivery has no such version.")
            return version

        def embedded_page(self):
            """The page frame around another application on this host, named by ?address= and optionally ?from=<item>."""
            query = parse_qs(urlsplit(self.path).query)
            address, origin = query.get("address", [""])[0], query.get("from", [""])[0]
            try:
                interactive_documents.validate_address(address, public[2] if public else None)
            except ValueError as error:
                raise StatusError("This address cannot be shown inside the review page.") from error
            back = item = None                       # the report or delivery version the reader came from, when ?from= names one
            try:
                record = deliveries.version(origin)
                if record["id"] == origin:
                    back = (review_pages.delivery_route(record["series"], origin, record["latest"]), record["title"])
                    item = ("delivery", origin, record["latest"], record["interactive"])
            except StatusError:
                pass
            if back is None:
                try:
                    manifest = reports._manifest(origin)
                    back = ("/reports/" + origin, manifest["title"])
                    item = ("report", origin, reports.operation(manifest["operation_id"])["latest"] == origin, manifest["interactive"])
                except StatusError:
                    pass
            # The application keeps the item's saved state only when it is that item's own interactive document.
            owner = item[:3] if item and item[3] == {"kind": "address", "address": address} else None
            elsewhere = f"{self.public_url()}/embedded?address={address}" + (f"&from={origin}" if back else "") if public else None
            return review_pages.embedded_page(self.base(), address, public[0] + address if self.remote() else None, back, elsewhere,
                                              self.public_url(), owner)

        def document_state_item(self, kind, identifier):
            """(state key, whether this version may save) for the item a document state request names."""
            if kind == "delivery":
                record = deliveries.version(identifier)
                if record["id"] != identifier or not record["interactive"]:
                    raise StatusError("This delivery version has no interactive document.")
                return record["series"], record["latest"]
            if kind == "report":
                manifest = reports._manifest(identifier)
                if not manifest["interactive"]:
                    raise StatusError("This report has no interactive document.")
                return manifest["operation_id"], reports.operation(manifest["operation_id"])["latest"] == identifier
            raise StatusError("Document state belongs to a delivery or a report.")

        def do_OPTIONS(self):
            path = self.route()
            if not self.accepted_host() or not path.startswith("/api/report-responses/"):
                self.send(403, {"error": "This action does not support cross-origin access."})
                return
            try:
                reports._manifest(path.removeprefix("/api/report-responses/"))
            except StatusError:
                self.send(404, {"error": "This report is unavailable."}, cors=True)
                return
            self.send(204, b"", cors=True)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self.accepted_host():
                self.send(403, {"error": "Use the Status address configured for this machine."})
                return
            path, base = self.route(), self.base()
            cors = path.startswith("/api/report-responses/")
            try:
                if path == "/":
                    if base and urlsplit(self.path).path == base:      # relative links need the trailing slash
                        self.send(308, b"", "text/plain", location=base + "/")
                        return
                    self.send(200, review_pages.review_page(base).encode("utf-8"), "text/html")
                elif path in FILES:
                    self.send(200, (ASSETS / path[1:]).read_bytes(), FILES[path],
                              readers="cross-origin" if path == DOCUMENT_HELPER else "same-origin")
                elif path == "/health":
                    self.send(200, {"service": SERVICE, "version": VERSION, "inbox": str(reports.root), "public_url": self.public_url()})
                elif path == "/api/config":
                    self.send(200, {"token": token})
                elif path == "/api/review":
                    if "fresh=asks" in urlsplit(self.path).query:
                        asks.invalidate()
                    self.send(200, self.review())
                elif path == "/api/reports":
                    self.send(200, reports.list())
                elif path.startswith("/api/operations/") and path.endswith("/latest"):
                    # What an open report polls to switch to a new version as soon as it is published.
                    operation = reports.operation(path.removeprefix("/api/operations/").removesuffix("/latest"))
                    self.send(200, {"latest": operation["latest"], "version_count": len(operation["versions"])})
                elif path.startswith("/api/operations/"):
                    if "fresh=asks" in urlsplit(self.path).query:
                        asks.invalidate()
                    operation, listing = reports.operation(path.removeprefix("/api/operations/")), self.with_replies(asks.current())
                    shared = shared_workspaces(reports.operations()["operations"])
                    self.send(200, {"operation": operation, "asks": {**listing, "asks": for_operation(listing["asks"], operation, shared)},
                                    "public_url": self.public_url()})
                elif path.startswith("/api/document-state/"):
                    kind, _, identifier = path.removeprefix("/api/document-state/").partition("/")
                    self.send(200, states.read(self.document_state_item(kind, identifier)[0]))
                elif path.startswith("/api/responses/"):
                    self.send(200, reports.responses(path.removeprefix("/api/responses/")))
                elif cors:
                    identifier = path.removeprefix("/api/report-responses/")
                    if not self.report_access(identifier):
                        self.send(403, {"error": "This page does not have access to this report's responses."}, cors=True)
                        return
                    self.send(200, reports.responses(identifier), cors=True)
                elif path.startswith("/reports/"):
                    identifier, _, rest = path.removeprefix("/reports/").partition("/")
                    if rest == "interactive":
                        self.send_interactive_document(reports.interactive_document(identifier))
                    elif rest:
                        raise StatusError("This page does not exist.")
                    else:
                        content, report_policy = self.report_page(identifier)
                        self.send(200, content.encode("utf-8"), "text/html", policy=report_policy)
                elif path.startswith("/operations/"):
                    operation = reports.operation(path.removeprefix("/operations/"))
                    self.send(302, b"", "text/plain", location=f"{base}/reports/{operation['latest']}")
                elif path.startswith("/deliveries/"):
                    parts = path.removeprefix("/deliveries/").split("/")
                    if len(parts) == 1:
                        page = self.delivery_page(self.delivery_version(parts[0]))
                    elif len(parts) == 2 and parts[1] == "interactive":      # retained files belong to exactly one version
                        self.send_interactive_document(deliveries.interactive_document(deliveries.version(parts[0])["id"]))
                        return
                    elif len(parts) == 3 and parts[1] == "attachments" and parts[2].isdecimal():
                        record = deliveries.version(parts[0])
                        page = review_pages.attachment_page(self.addresses(), record, *deliveries.attachment(record["id"], int(parts[2])))
                    else:
                        raise StatusError("This page does not exist.")
                    self.send(200, page.encode("utf-8"), "text/html")
                elif path == "/embedded":
                    self.send(200, self.embedded_page().encode("utf-8"), "text/html")
                else:
                    self.send(404, {"error": "This page does not exist."})
            except StatusError as error:
                self.send(404, {"error": str(error)}, cors=cors)
            except OSError:
                self.send(503, {"error": "Status storage is unavailable. Try Refresh."}, cors=cors)

        def do_POST(self):
            path = self.route()
            cors = path.startswith("/api/report-responses/")
            identifier = path.removeprefix("/api/report-responses/") if cors else None
            authorized = self.report_access(identifier) if cors else (
                self.trusted_origin() and secrets.compare_digest(self.headers.get("X-Status-Token", ""), token))
            if not self.accepted_host() or not authorized:
                self.send(403, {"error": "Refresh the Status page before changing anything."}, cors=cors)
                return
            if not cors and path not in POSTS:
                self.send(404, {"error": "This action does not exist."})
                return
            required, optional, maximum = ({"revision", "values"}, set(), 4 * 1024 * 1024) if cors else POSTS[path]
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= maximum or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Expected a JSON request within the size limit.")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or not required <= body.keys() or body.keys() - required - optional:
                    raise ValueError("Provide the expected action fields.")
                if cors or path == "/api/responses":
                    self.send(200, reports.save_responses(identifier if cors else body["id"], body["values"], body["revision"]), cors=cors)
                elif path == "/api/dismiss":
                    self.send(200, reports.dismiss(body["id"], body["dismissed"]))
                elif path == "/api/ask-reply":
                    if self.remote():
                        raise PermissionError("On the tailnet address, replies go through Ribbon Field's paired-device sign-in.")
                    ask = next((entry for entry in asks.current()["asks"] if entry["id"] == body["id"]), None)
                    if ask is None:
                        raise ValueError("This ask is no longer open. Refresh the page.")
                    self.send(200, ask_replier(ask, body["text"]))
                elif path == "/api/item-message":
                    if self.remote():
                        raise PermissionError("On the tailnet address, messages go through Ribbon Field's paired-device sign-in.")
                    self.send(200, message_sender(self.conversation(body["kind"], body["id"]), body["message"]))
                elif path == "/api/ask-resolution":
                    if self.remote():
                        raise PermissionError("On the tailnet address, answers go through Ribbon Field's paired-device sign-in.")
                    result = ask_resolver(body["id"], body["body"], snooze=body.get("snooze") is True)
                    asks.invalidate()
                    self.send(200, result)
                elif path == "/api/delivery-response":
                    record = deliveries.respond(body["id"], body["action"], choice=body.get("choice"), note=body.get("note"))
                    if body["action"] != "read":
                        usage.record("response", item_kind="delivery", item=body["id"], action=body["action"], remote=self.remote())
                    record.pop("document_state")
                    self.send(200, record)
                elif path == "/api/document-state":
                    key, latest = self.document_state_item(body["kind"], body["id"])
                    if not latest:
                        raise ResponseConflict("Only the interactive document of the latest version saves state.")
                    saved = states.save(key, body["state"], body["id"])
                    self.send(200, {name: saved[name] for name in ("saved_at", "revision", "version")})
                else:
                    opened = None
                    if body["type"] not in {"page_open", "item_open", "ask_resolution", "item_message"}:
                        raise ValueError("Pages report page_open, item_open, ask_resolution and item_message events only.")
                    if body["type"] == "item_message" and body.get("action") not in ("explain", "question"):
                        raise ValueError("A message about a selection is an explain or a question; its words are never recorded.")
                    if body["type"] == "item_open" and body.get("action") not in (None, INTERACTIVE_OPEN):
                        raise ValueError("An item is opened, or its interactive document is.")
                    if body["type"] == "item_open" and body.get("item_kind") == "operation" and not body.get("action"):
                        opened = reports.mark_opened(body.get("item"))
                    usage.record(body["type"], view=body.get("view"), item_kind=body.get("item_kind"), item=body.get("item"),
                                 action=body.get("action"), narrow=body.get("narrow"), remote=self.remote())
                    self.send(200, {"recorded": True, "opened": opened})
            except ResponseConflict as error:
                self.send(409, {"error": str(error)}, cors=cors)
            except PermissionError as error:
                self.send(403, {"error": str(error)}, cors=cors)
            except RecursionError:
                self.send(400, {"error": "The request is nested too deeply."}, cors=cors)
            except (ValueError, UnicodeError) as error:
                self.send(400, {"error": str(error)}, cors=cors)
            except OSError:
                self.send(503, {"error": "The change could not be saved. Try again."}, cors=cors)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def inspect_service(root, port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
            value = json.load(response)
    except urllib.error.HTTPError as error:
        raise ValueError(f"Port {port} belongs to another service; select a different --port.") from error
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False
    except (ValueError, UnicodeError) as error:
        raise ValueError(f"Port {port} does not contain a Status service.") from error
    if value.get("service") != SERVICE or value.get("inbox") != str(root):
        raise ValueError(f"Port {port} belongs to another service or inbox; select a different --port.")
    if value.get("version", 1) < VERSION:
        raise ValueError("The running Status service is an earlier version. Run install for its login service, or restart its serve process.")
    return True


def wait_for_service(root, port, process=None):
    for _ in range(40):
        if inspect_service(root, port):
            return
        if process is not None and process.poll() is not None:
            break
        time.sleep(.1)
    raise ValueError(f"The Status service did not start. Check {root / 'viewer/service.log'}.")


def saved_public_url(root):
    """The public address recorded by the last install or serve, used to print links other devices can open."""
    try:
        value = json.loads((Path(root) / "viewer/configuration.json").read_text(encoding="utf-8")).get("public_url")
        return value if isinstance(value, str) and public_address(value) else None
    except (OSError, ValueError, AttributeError):
        return None


def save_public_url(root, public_url):
    runtime = Path(root) / "viewer"
    runtime.mkdir(parents=True, exist_ok=True)
    temporary = runtime / "configuration.pending"
    temporary.write_text(json.dumps({"public_url": public_url}) + "\n", encoding="utf-8")
    temporary.replace(runtime / "configuration.json")


def service_arguments(root, port, public_url=None):
    return ([sys.executable, "-B", str(Path(__file__).resolve()), "serve", "--inbox", str(root), "--port", str(port)]
            + (["--public-url", public_url] if public_url else []))


def start(root, port, public_url=None):
    if inspect_service(root, port):
        return
    runtime = root / "viewer"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "service.log").open("ab") as log:
        process = subprocess.Popen(service_arguments(root, port, public_url), stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, start_new_session=True, cwd=str(root))
    wait_for_service(root, port, process)


def install(root, port, public_url=None):
    import plistlib

    if sys.platform != "darwin":
        raise ValueError("Login startup installation is available on macOS. Use start or serve on this system.")
    runtime = root / "viewer"
    runtime.mkdir(parents=True, exist_ok=True)
    destination = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
    configuration = {"Label": LABEL, "ProgramArguments": service_arguments(root, port, public_url),
                     "RunAtLoad": True, "KeepAlive": True, "WorkingDirectory": str(root),
                     "StandardOutPath": str(runtime / "service.log"), "StandardErrorPath": str(runtime / "service.log")}
    service = f"gui/{os.getuid()}/{LABEL}"
    loaded = subprocess.run(["launchctl", "print", service], capture_output=True).returncode == 0
    if destination.exists():
        previous = plistlib.loads(destination.read_bytes())
        if previous.get("Label") != LABEL or "status_server.py" not in " ".join(previous.get("ProgramArguments", [])):
            raise ValueError("The startup file belongs to another service.")
        if loaded and previous == configuration:
            subprocess.run(["launchctl", "kickstart", "-k", service], check=True, capture_output=True)
            wait_for_restart(root, port)
            return
    if not loaded:
        try:
            occupied = inspect_service(root, port)
        except ValueError:
            occupied = True
        if occupied:
            raise ValueError("A manually started Status service is using this port. Stop that service before installing login startup.")
    if loaded:
        subprocess.run(["launchctl", "bootout", service], check=True, capture_output=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".pending")
    temporary.write_bytes(plistlib.dumps(configuration))
    temporary.chmod(0o600)
    temporary.replace(destination)
    for attempt in range(20):                    # bootout returns before the previous instance has fully left
        result = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(destination)], capture_output=True)
        if result.returncode == 0:
            break
        time.sleep(.25)
    else:
        raise ValueError("launchctl could not load the Status service: " + result.stderr.decode(errors="replace").strip())
    wait_for_restart(root, port)


def wait_for_restart(root, port):
    """Wait for the reloaded service, tolerating the previous version answering briefly."""
    for _ in range(60):
        try:
            if inspect_service(root, port):
                return
        except ValueError:
            pass
        time.sleep(.1)
    try:
        if inspect_service(root, port):
            return
    except ValueError:
        pass
    raise ValueError(f"The login service was loaded, but port {port} does not answer as the current Status service. "
                     f"An earlier Status process may still hold the port: find it with "
                     f"'lsof -nP -iTCP:{port} -sTCP:LISTEN', confirm it is status_server.py for this inbox, and stop that "
                     f"process; the login service then starts by itself. Log: {root / 'viewer/service.log'}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("serve", "start", "install"), help="Run in this terminal, start detached, or install macOS login startup")
    parser.add_argument("--inbox", type=Path, default=inbox_directory())
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--public-url", help="HTTPS address another device uses for this page through an authorized relay, "
                        "such as a Tailscale serve path. install keeps the previously recorded address when omitted.")
    arguments = parser.parse_args()
    root = arguments.inbox.expanduser().resolve()
    if not 0 <= arguments.port <= 65535 or (arguments.command != "serve" and arguments.port == 0):
        parser.error("Choose a port from 1 to 65535 (serve also accepts 0 for testing).")
    try:
        public_url = arguments.public_url.rstrip("/") if arguments.public_url else None
        public_address(public_url)
        if arguments.command == "serve":
            with make_server(root, arguments.port, public_url=public_url) as server:
                print(f"http://127.0.0.1:{server.server_port}/", flush=True)
                server.serve_forever()
        else:
            public_url = public_url or (saved_public_url(root) if arguments.command == "install" else None)
            (install if arguments.command == "install" else start)(root, arguments.port, public_url)
            if arguments.command == "install":
                save_public_url(root, public_url)        # only the login service records the address; a development serve never does
            print(f"http://127.0.0.1:{arguments.port}/")
            if public_url:
                print(public_url + "/")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

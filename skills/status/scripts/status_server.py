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
from urllib.parse import urlsplit

from delivery_store import Deliveries
from register_status import inbox_directory
from response_access import response_key
import review_pages
from ribbon_field_asks import AskReader, for_operation
from status_store import REPORT_CSP, ResponseConflict, StatusError, StatusReports
from usage_events import UsageEvents

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SERVICE = "workstation-status"
LABEL = "com.workstation.status"
DEFAULT_PORT = 8766
VERSION = 4
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src data:; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
FILES = {"/tokens.css": "text/css", "/style.css": "text/css", "/review.css": "text/css", "/controls.js": "text/javascript",
         "/responses.js": "text/javascript", "/report.js": "text/javascript", "/review.js": "text/javascript",
         "/report_page.js": "text/javascript", "/delivery.js": "text/javascript"}
POSTS = {"/api/dismiss": ({"id", "dismissed"}, set(), 4096),
         "/api/responses": ({"id", "revision", "values"}, set(), 4 * 1024 * 1024),
         "/api/delivery-response": ({"id", "action"}, {"choice", "note"}, 16 * 1024),
         "/api/events": ({"type"}, {"view", "item_kind", "item", "narrow"}, 4096)}


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


def make_server(root, port=DEFAULT_PORT, *, public_url=None, ask_reader=None):
    root = Path(root).resolve()
    reports, deliveries, usage = StatusReports(root), Deliveries(root), UsageEvents(root)
    asks = ask_reader or AskReader()
    token = secrets.token_urlsafe(32)
    public = public_address(public_url)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, message, *arguments):
            # Keep the service log for failures rather than continual refreshes.
            if arguments and str(arguments[1] if len(arguments) > 1 else "").startswith(("4", "5")):
                super().log_message(message, *arguments)

        def send(self, status, content, content_type="application/json", *, policy=PAGE_CSP, cors=False, location=None):
            if not isinstance(content, bytes):
                content = json.dumps(content, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", policy)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Referrer-Policy", "no-referrer")
            if location:
                self.send_header("Location", location)
            if cors and self.headers.get("Origin"):
                self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Status-Report-Token")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(content)

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

        def review(self):
            operations, delivered, listing = reports.operations(), deliveries.list(), asks.current()
            for operation in operations["operations"]:
                operation["ask_count"] = len(for_operation(listing["asks"], operation)) if listing["available"] else None
                operation["version_count"] = len(operation.pop("versions"))
            return {"operations": operations["operations"], "deliveries": delivered["deliveries"], "asks": listing,
                    "unreadable": operations["unreadable"] + delivered["unreadable"]}

        def report_page(self, identifier):
            manifest = reports._manifest(identifier)
            document = reports.document(identifier)
            if document is None:
                return reports.content(identifier), REPORT_CSP          # retained HTML only: never run its scripts
            from build_status import render
            base, operation = self.base(), reports.operation(manifest["operation_id"])
            fields = document.get("response_fields")
            configuration = {"report": identifier, "operation": operation["id"], "latest": operation["latest"] == identifier,
                             "dismissed": bool(manifest["dismissed_at"])}
            if fields:
                configuration["responses"] = {"fields": fields, "connection": {
                    "id": identifier, "url": f"{base}/api/report-responses/{identifier}",
                    "token": response_key(reports.root, identifier, create=True)}}
            scripts = ("controls.js",) + (("responses.js", "report.js") if fields else ()) + ("report_page.js",)
            return render(document, page={"base": base, "scripts": scripts, "configuration": configuration,
                                          "navigation": review_pages.report_navigation(base, operation, identifier)}), PAGE_CSP

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
                    self.send(200, (ASSETS / path[1:]).read_bytes(), FILES[path])
                elif path == "/health":
                    self.send(200, {"service": SERVICE, "version": VERSION, "inbox": str(reports.root),
                                    "public_url": public[0] + public[2] if public else None})
                elif path == "/api/config":
                    self.send(200, {"token": token})
                elif path == "/api/review":
                    self.send(200, self.review())
                elif path == "/api/reports":
                    self.send(200, reports.list())
                elif path.startswith("/api/operations/"):
                    operation, listing = reports.operation(path.removeprefix("/api/operations/")), asks.current()
                    self.send(200, {"operation": operation, "asks": {**listing, "asks": for_operation(listing["asks"], operation)}})
                elif path.startswith("/api/responses/"):
                    self.send(200, reports.responses(path.removeprefix("/api/responses/")))
                elif cors:
                    identifier = path.removeprefix("/api/report-responses/")
                    if not self.report_access(identifier):
                        self.send(403, {"error": "This page does not have access to this report's responses."}, cors=True)
                        return
                    self.send(200, reports.responses(identifier), cors=True)
                elif path.startswith("/reports/"):
                    content, policy = self.report_page(path.removeprefix("/reports/"))
                    self.send(200, content.encode("utf-8"), "text/html", policy=policy)
                elif path.startswith("/operations/"):
                    operation = reports.operation(path.removeprefix("/operations/"))
                    self.send(302, b"", "text/plain", location=f"{base}/reports/{operation['latest']}")
                elif path.startswith("/deliveries/"):
                    parts = path.removeprefix("/deliveries/").split("/")
                    record = deliveries.record(parts[0])
                    if len(parts) == 1:
                        page = review_pages.delivery_page(base, record, deliveries.document(parts[0]))
                    elif len(parts) == 3 and parts[1] == "attachments" and parts[2].isdecimal():
                        page = review_pages.attachment_page(base, record, *deliveries.attachment(parts[0], int(parts[2])))
                    else:
                        raise StatusError("This page does not exist.")
                    self.send(200, page.encode("utf-8"), "text/html")
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
                elif path == "/api/delivery-response":
                    record = deliveries.respond(body["id"], body["action"], choice=body.get("choice"), note=body.get("note"))
                    if body["action"] != "read":
                        usage.record("response", item_kind="delivery", item=body["id"], action=body["action"], remote=self.remote())
                    self.send(200, record)
                else:
                    opened = None
                    if body["type"] not in {"page_open", "item_open"}:
                        raise ValueError("Pages report page_open and item_open events only.")
                    if body["type"] == "item_open" and body.get("item_kind") == "operation":
                        opened = reports.mark_opened(body.get("item"))
                    usage.record(body["type"], view=body.get("view"), item_kind=body.get("item_kind"), item=body.get("item"),
                                 narrow=body.get("narrow"), remote=self.remote())
                    self.send(200, {"recorded": True, "opened": opened})
            except ResponseConflict as error:
                self.send(409, {"error": str(error)}, cors=cors)
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
        raise ValueError("The running Status service predates the review page. Run install for its login service, or restart its serve process.")
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
                save_public_url(root, public_url)
                print(f"http://127.0.0.1:{server.server_port}/", flush=True)
                server.serve_forever()
        else:
            public_url = public_url or (saved_public_url(root) if arguments.command == "install" else None)
            (install if arguments.command == "install" else start)(root, arguments.port, public_url)
            print(f"http://127.0.0.1:{arguments.port}/")
            if public_url:
                print(public_url + "/")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

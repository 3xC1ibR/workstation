#!/usr/bin/env python3
"""Serve the standalone Status collection, with optional local startup management."""
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

from register_status import inbox_directory
from status_store import REPORT_CSP, StatusError, StatusReports

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SERVICE = "workstation-status"
LABEL = "com.workstation.status"
DEFAULT_PORT = 8766
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def make_server(root, port=DEFAULT_PORT):
    reports = StatusReports(Path(root).resolve())
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, message, *arguments):
            # Keep the service log for failures rather than continual refreshes.
            if arguments and str(arguments[1] if len(arguments) > 1 else "").startswith(("4", "5")):
                super().log_message(message, *arguments)

        def send(self, status, content, content_type="application/json", *, policy=PAGE_CSP):
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
            self.end_headers()
            self.wfile.write(content)

        def local_request(self):
            hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            return self.headers.get("Host") in hosts

        def do_GET(self):
            if not self.local_request():
                self.send(403, {"error": "Use the local Status address."})
                return
            path = urlsplit(self.path).path
            assets = {"/": ("inbox.html", "text/html"), "/style.css": ("style.css", "text/css"),
                      "/inbox.css": ("inbox.css", "text/css"), "/inbox.js": ("inbox.js", "text/javascript")}
            try:
                if path in assets:
                    name, content_type = assets[path]
                    self.send(200, (ASSETS / name).read_bytes(), content_type)
                elif path == "/health":
                    self.send(200, {"service": SERVICE, "version": 1, "inbox": str(reports.root)})
                elif path == "/api/config":
                    self.send(200, {"token": token})
                elif path == "/api/reports":
                    self.send(200, reports.list())
                elif path.startswith("/reports/"):
                    self.send(200, reports.content(path.removeprefix("/reports/")).encode("utf-8"), "text/html", policy=REPORT_CSP)
                else:
                    self.send(404, {"error": "This page does not exist."})
            except StatusError as error:
                self.send(404, {"error": str(error)})
            except OSError:
                self.send(503, {"error": "Status storage is unavailable. Try Refresh."})

        def do_POST(self):
            origin = "http://" + self.headers.get("Host", "")
            if (not self.local_request() or self.headers.get("Origin") != origin or
                    not secrets.compare_digest(self.headers.get("X-Status-Token", ""), token)):
                self.send(403, {"error": "Refresh the Status page before changing a report."})
                return
            if urlsplit(self.path).path != "/api/dismiss":
                self.send(404, {"error": "This action does not exist."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Expected a small JSON request.")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or set(body) != {"id", "dismissed"}:
                    raise ValueError("Choose a report and its dismissed state.")
                self.send(200, reports.dismiss(body["id"], body["dismissed"]))
            except (ValueError, UnicodeError) as error:
                self.send(400, {"error": str(error)})
            except OSError:
                self.send(503, {"error": "The report could not be updated. Try again."})

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
    return True


def wait_for_service(root, port, process=None):
    for _ in range(40):
        if inspect_service(root, port):
            return
        if process is not None and process.poll() is not None:
            break
        time.sleep(.1)
    raise ValueError(f"The Status viewer did not start. Check {root / 'viewer/service.log'}.")


def service_arguments(root, port):
    return [sys.executable, "-B", str(Path(__file__).resolve()), "serve", "--inbox", str(root), "--port", str(port)]


def start(root, port):
    if inspect_service(root, port):
        return
    runtime = root / "viewer"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "service.log").open("ab") as log:
        process = subprocess.Popen(service_arguments(root, port), stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, start_new_session=True, cwd=str(root))
    wait_for_service(root, port, process)


def install(root, port):
    import plistlib

    if sys.platform != "darwin":
        raise ValueError("Login startup installation is available on macOS. Use start or serve on this system.")
    runtime = root / "viewer"
    runtime.mkdir(parents=True, exist_ok=True)
    destination = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
    configuration = {"Label": LABEL, "ProgramArguments": service_arguments(root, port),
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
            wait_for_service(root, port)
            return
    if not loaded and inspect_service(root, port):
        raise ValueError("A manually started Status viewer is using this port. Stop that viewer before installing login startup.")
    if loaded:
        subprocess.run(["launchctl", "bootout", service], check=True, capture_output=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".pending")
    temporary.write_bytes(plistlib.dumps(configuration))
    temporary.chmod(0o600)
    temporary.replace(destination)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(destination)], check=True, capture_output=True)
    wait_for_service(root, port)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("serve", "start", "install"), help="Run in this terminal, start detached, or install macOS login startup")
    parser.add_argument("--inbox", type=Path, default=inbox_directory())
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    arguments = parser.parse_args()
    root = arguments.inbox.expanduser().resolve()
    if not 0 <= arguments.port <= 65535 or (arguments.command != "serve" and arguments.port == 0):
        parser.error("Choose a port from 1 to 65535 (serve also accepts 0 for testing).")
    try:
        if arguments.command == "serve":
            with make_server(root, arguments.port) as server:
                print(f"http://127.0.0.1:{server.server_port}/", flush=True)
                server.serve_forever()
        else:
            (install if arguments.command == "install" else start)(root, arguments.port)
            print(f"http://127.0.0.1:{arguments.port}/")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

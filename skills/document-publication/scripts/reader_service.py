"""Loopback-only service for generated publication pages."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import traceback
from urllib.parse import unquote, urlsplit

from publication import DEFAULT_STATE, generate, read_registry


class ReaderHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path == '/reader' or path.startswith('/reader/'):
            path = path[len('/reader'):] or '/'
        if ('\\' in path or any(part.startswith('.') for part in path.split('/'))
                or not (path.endswith('/') or path.endswith('.html'))):
            self.send_error(404)
            return
        candidate = Path(self.directory) / path.lstrip('/')
        if not candidate.resolve().is_relative_to(Path(self.directory).resolve()):
            self.send_error(404)
            return
        self.path = path
        super().do_GET()

    def do_HEAD(self):
        self.send_error(405)

    def list_directory(self, path):
        self.send_error(404)
        return None

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        super().end_headers()

    def log_message(self, format, *args):
        if args and str(args[1] if len(args) > 1 else '').startswith(('4', '5')):
            super().log_message(format, *args)


def main(state=DEFAULT_STATE):
    state = Path(state)
    generate(state)
    interval = read_registry(state).get('refresh_seconds', 30)
    server = ThreadingHTTPServer(('127.0.0.1', 8767), functools.partial(ReaderHandler, directory=str(state / 'site')))

    def refresh():
        while True:
            threading.Event().wait(interval)
            try:
                generate(state)
            except Exception:
                traceback.print_exc()

    threading.Thread(target=refresh, name='document-refresh', daemon=True).start()
    print('Research reader listening on 127.0.0.1:8767', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()

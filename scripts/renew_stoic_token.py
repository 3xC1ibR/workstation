#!/usr/bin/env python3
"""Renew the local Stoic API token before it expires.

Stoic issues 30-day JWT access tokens and refuses to refresh an expired one, so
an expired token can only be replaced by signing in again in the browser. This
script runs daily from launchd. When the stored token has fewer than
--threshold-days remaining, it calls POST /api/auth/web/refresh, verifies the
new token with GET /api/auth/web/me, keeps the previous token as a 0600 backup,
and replaces the token file atomically.

The token is never printed or logged. The log records only timestamps,
expiry dates and outcomes.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("STOIC_BASE_URL", "https://tryblume.ai")
DEFAULT_TOKEN_FILE = Path(
    os.environ.get("STOIC_API_TOKEN_FILE", "~/.config/stoic/codex-token")
).expanduser()
DEFAULT_LOG_FILE = Path("~/Library/Logs/stoic-token-renewal.log").expanduser()
REQUEST_TIMEOUT_SECONDS = 30


def token_expiry(token: str) -> dt.datetime | None:
    """Return the JWT exp claim as an aware UTC datetime, or None if absent."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    exp = claims.get("exp") if isinstance(claims, dict) else None
    if not isinstance(exp, (int, float)):
        return None
    return dt.datetime.fromtimestamp(exp, tz=dt.timezone.utc)


def renewal_due(expiry: dt.datetime | None, now: dt.datetime, threshold_days: float) -> bool:
    """A token is due for renewal when its expiry is unknown or inside the threshold."""
    if expiry is None:
        return True
    return expiry - now < dt.timedelta(days=threshold_days)


def api_request(method: str, path: str, token: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        BASE_URL + path,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=b"{}" if method == "POST" else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read() or b"{}")
        except json.JSONDecodeError:
            body = {}
        return error.code, body
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return 0, {}


def write_private_file(path: Path, content: str) -> None:
    """Write content to path atomically with mode 0600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def notify(message: str) -> None:
    """Post a macOS notification; failures are ignored."""
    script = f'display notification "{message}" with title "Stoic token"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def log(log_file: Path, message: str) -> None:
    stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"{stamp} {message}"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a") as handle:
        handle.write(line + "\n")
    print(line)


def describe(expiry: dt.datetime | None) -> str:
    return expiry.astimezone().isoformat(timespec="minutes") if expiry else "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG_FILE)
    parser.add_argument("--threshold-days", type=float, default=20.0,
                        help="renew when fewer than this many days remain (default 20)")
    parser.add_argument("--force", action="store_true", help="renew regardless of remaining lifetime")
    parser.add_argument("--dry-run", action="store_true", help="report status without renewing")
    args = parser.parse_args(argv)

    if not args.token_file.exists():
        log(args.log_file, f"error token file missing: {args.token_file}")
        notify("Token file missing. Sign in at tryblume.ai/login and save a new token.")
        return 2

    token = args.token_file.read_text().strip()
    now = dt.datetime.now(dt.timezone.utc)
    expiry = token_expiry(token)

    if expiry is not None and expiry <= now:
        log(args.log_file, f"error token expired at {describe(expiry)}; sign-in required")
        notify("Token expired. Sign in at tryblume.ai/login and save a new token.")
        return 3

    if not args.force and not renewal_due(expiry, now, args.threshold_days):
        log(args.log_file, f"ok not due; expires {describe(expiry)}")
        return 0

    if args.dry_run:
        log(args.log_file, f"dry-run renewal due; expires {describe(expiry)}")
        return 0

    status, body = api_request("POST", "/api/auth/web/refresh", token)
    new_token = body.get("token") if isinstance(body, dict) else None
    if status != 200 or not isinstance(new_token, str) or not new_token:
        log(args.log_file, f"error refresh failed with HTTP {status}; current token expires {describe(expiry)}")
        if status == 401:
            notify("Refresh rejected. Sign in at tryblume.ai/login and save a new token.")
        return 4

    status, me = api_request("GET", "/api/auth/web/me", new_token)
    if status != 200 or not isinstance(me, dict) or "account_type" not in me:
        log(args.log_file, f"error new token failed verification with HTTP {status}; token file unchanged")
        return 5

    write_private_file(args.token_file.with_name(args.token_file.name + ".previous"), token + "\n")
    write_private_file(args.token_file, new_token + "\n")
    log(args.log_file, f"renewed; previous expiry {describe(expiry)}, new expiry {describe(token_expiry(new_token))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

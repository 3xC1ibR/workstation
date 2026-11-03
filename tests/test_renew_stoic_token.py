import base64
import datetime as dt
import importlib.util
import json
import stat
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "renew_stoic_token.py"
spec = importlib.util.spec_from_file_location("renew_stoic_token", SCRIPT)
renew = importlib.util.module_from_spec(spec)
sys.modules["renew_stoic_token"] = renew
spec.loader.exec_module(renew)


def make_token(exp: dt.datetime) -> str:
    def segment(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return ".".join([segment({"alg": "HS256"}), segment({"sub": "x", "exp": int(exp.timestamp())}), "signature"])


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def test_token_expiry_reads_exp_claim():
    exp = utc_now().replace(microsecond=0) + dt.timedelta(days=28)
    assert renew.token_expiry(make_token(exp)) == exp


def test_token_expiry_rejects_malformed_token():
    assert renew.token_expiry("not-a-jwt") is None
    assert renew.token_expiry("a.%%%.c") is None


def test_renewal_due_threshold():
    now = utc_now()
    assert not renew.renewal_due(now + dt.timedelta(days=28), now, 20)
    assert renew.renewal_due(now + dt.timedelta(days=19), now, 20)
    assert renew.renewal_due(None, now, 20)


def test_not_due_leaves_file_untouched(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    token = make_token(utc_now() + dt.timedelta(days=28))
    token_file.write_text(token + "\n")

    def forbid_network(*args, **kwargs):
        raise AssertionError("no network call expected")

    monkeypatch.setattr(renew, "api_request", forbid_network)
    assert renew.main(["--token-file", str(token_file), "--log-file", str(tmp_path / "log")]) == 0
    assert token_file.read_text().strip() == token
    assert token not in (tmp_path / "log").read_text()


def test_renewal_writes_new_token_and_private_backup(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    old = make_token(utc_now() + dt.timedelta(days=5))
    new = make_token(utc_now() + dt.timedelta(days=30))
    token_file.write_text(old + "\n")
    calls = []

    def fake_request(method, path, token):
        calls.append((method, path, token))
        if path == "/api/auth/web/refresh":
            return 200, {"token": new}
        return 200, {"account_type": "admin"}

    monkeypatch.setattr(renew, "api_request", fake_request)
    monkeypatch.setattr(renew, "notify", lambda message: None)
    assert renew.main(["--token-file", str(token_file), "--log-file", str(tmp_path / "log")]) == 0
    backup = tmp_path / "token.previous"
    assert token_file.read_text().strip() == new
    assert backup.read_text().strip() == old
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert calls == [("POST", "/api/auth/web/refresh", old), ("GET", "/api/auth/web/me", new)]
    log_text = (tmp_path / "log").read_text()
    assert old not in log_text and new not in log_text


def test_failed_verification_keeps_old_token(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    old = make_token(utc_now() + dt.timedelta(days=5))
    token_file.write_text(old + "\n")

    def fake_request(method, path, token):
        if path == "/api/auth/web/refresh":
            return 200, {"token": make_token(utc_now() + dt.timedelta(days=30))}
        return 401, {}

    monkeypatch.setattr(renew, "api_request", fake_request)
    assert renew.main(["--token-file", str(token_file), "--log-file", str(tmp_path / "log")]) == 5
    assert token_file.read_text().strip() == old
    assert not (tmp_path / "token.previous").exists()


def test_expired_token_requests_sign_in(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    token_file.write_text(make_token(utc_now() - dt.timedelta(days=1)))
    notices = []
    monkeypatch.setattr(renew, "notify", notices.append)
    assert renew.main(["--token-file", str(token_file), "--log-file", str(tmp_path / "log")]) == 3
    assert notices and "Sign in" in notices[0]

# Stoic token renewal

Stoic API tokens (`~/.config/stoic/codex-token`) are 30-day JWTs. Stoic refuses to
refresh an expired token, so a lapse means signing in again at tryblume.ai/login
(this happened on 2026-11-01).

`scripts/renew_stoic_token.py` runs daily at 10:15 local time and at login from
`launchd/com.rquinonez.stoic-token-renewal.plist`. When fewer than 20 days remain,
it calls `POST /api/auth/web/refresh`, verifies the new token with
`GET /api/auth/web/me`, saves the old token as `codex-token.previous` (mode 0600),
and replaces the token file atomically. If the token has already expired or the
refresh returns 401, it posts a macOS notification asking for a fresh sign-in.
Neither the token nor any part of it is logged.

- Log: `~/Library/Logs/stoic-token-renewal.log`
- Status: `python3 scripts/renew_stoic_token.py --dry-run`
- Install: `cp launchd/com.rquinonez.stoic-token-renewal.plist ~/Library/LaunchAgents/ && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rquinonez.stoic-token-renewal.plist`
- Remove: `launchctl bootout gui/$(id -u)/com.rquinonez.stoic-token-renewal`
- Tests: `uv run --with pytest python -m pytest -q tests/test_renew_stoic_token.py`

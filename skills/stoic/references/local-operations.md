# Local operations

On Walle, `/opt/projects/workstation/scripts/renew_stoic_token.py` exchanges
a valid legacy credential through `POST /api/auth/web/agent-token`, verifies
the agent identity and replaces the credential file atomically. An expired
credential requires sign-in.

A prompt beginning with “use Stoic”, “please use Stoic”, `/stoic` or `$stoic`
enables sync from that prompt forward. `/stoic on` enables it. An off request
discards unsent turns. Forks need a fresh opt-in. If invocation did not enable
sync, explain how to opt in when relevant.

Codex shows the confirmation to the agent. Claude Code shows it only to the user.
Check `~/.local/state/stoic-claude-code-sync/sessions/<sha256-of-session-ID>.json`
before reporting Claude sync status. The Claude hook also uploads attached prompt
images. The reader's `api 'conversation sync'` command gives hook installation
and source paths.

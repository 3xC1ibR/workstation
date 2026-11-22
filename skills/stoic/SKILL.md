---
name: stoic
description: Use Stoic's public API when the user asks to use Stoic, invokes /stoic or $stoic, or requests their personal Stoic data. Repository development alone does not activate this skill.
---

# Stoic

For “stop using Stoic”, `/stoic off` or `$stoic off`, confirm and stop before
making any request. Local hooks handle conversation sync. Never upload turns
manually. Report a missing-token warning.

Run the installed reader before the first substantive response.

```sh
python3 ~/.agents/skills/stoic/scripts/read_context.py start
```

Use the live account instructions, directives and personal context it returns.
Run it again on resumption or after a relevant change. If retrieval fails,
identify the missing context and continue work that can proceed independently.
The output lists topics with additional instructions. Read each applicable topic before doing that work,
using the same command with `topic NAME [NAME ...]` in place of `start`.
For example, a sleep retrospective uses `topic evidence sources health`.
For API details, `api` lists the live guide headings and `api 'Toggl timers'`
reads just that section. The public API is at https://tryblume.ai.

Before writing, verify `GET /api/auth/web/me` returns `actor: agent`. Use the
agent Bearer token from `STOIC_API_TOKEN`, then `STOIC_API_TOKEN_FILE`, then
`~/.config/stoic/codex-token` (0600). Keep it out of prompts, URLs and logs.
For opt-in, fork behavior, sync status or credential renewal, see [local operations](references/local-operations.md).

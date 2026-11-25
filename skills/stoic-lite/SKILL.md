---
name: stoic-lite
description: Lightweight read/write Stoic I/O CLI for technical threads that only need to search, read, or save a note, task, or bookmark without running the full Stoic protocol or conversation sync.
---

# Stoic Lite I/O

Use this skill in strictly technical threads when you only need to look up or save a note, task, or bookmark in Stoic.

- Does **not** run `read_context.py start` or load personal LTM, Toggl, or directives.
- Does **not** enable conversation sync hooks.
- Encapsulates Stoic Bearer auth internally; never read, print, or pass tokens yourself.
- For full Stoic personal context, coaching, or `/stoic`, use the `stoic` skill instead.

## CLI

```sh
STOIC_IO="python3 ~/.agents/skills/stoic-lite/scripts/stoic_io.py"
```

All commands print JSON by default (`--human` for compact text). All writes verify `actor: agent` before sending and support `--dry-run` to inspect the exact validated request without writing.

### Read

```sh
$STOIC_IO whoami
$STOIC_IO search "Ribbon Field" [--types note,task,project] [--limit 10] [--mode auto]
$STOIC_IO get <record_type> <id>
$STOIC_IO list-tasks [--status pending|in_progress|done|wont_do|all] [--project-id ID] [--limit 20]
```

### Write

```sh
$STOIC_IO save-note --title "Title" (--body "Text" | --body-file -) [--tags a,b] [--project-id ID] [--dry-run]
$STOIC_IO save-task --title "Title" [--description "Text"] [--project-id ID] [--due 2026-12-01] \
  [--confirmed | --suggested] [--responsibility user|agent] [--source "thread/url"] [--dry-run]
$STOIC_IO save-bookmark --url "https://example.com" [--title "Title"] [--note "Why"] [--tags a,b] [--dry-run]
```

## Write conventions

- When the user asks to pin, park, or track an action item, use `save-task` with `--confirmed --responsibility user --source <link-or-thread-id>` and confirm in one line.
- Use `--suggested` for unconfirmed agent proposals. Never invent `--due` dates the user did not give.

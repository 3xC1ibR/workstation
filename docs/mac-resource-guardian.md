# Mac resource guardian

Watches free disk, swap and memory on this 16 GB / 460 GB MacBook and
reclaims space before agents exhaust it. Motivation: on 2026-11-22 the root
volume hit 98% full (247 MB free) with swap at 18.7 of 19.7 GB while about 20
agents ran; Codex crashed and work was lost.

`scripts/mac_resource_guardian.py` runs every five minutes from
`launchd/com.rquinonez.mac-resource-guardian.plist` and is stdlib-only.

## What it does every run

- Measures free disk, swap, memory free percentage, the top memory processes
  and the sizes of watched paths, and appends one JSON line to
  `~/.local/state/mac-resource-guardian/samples.jsonl` (rotated at 5 MiB,
  one generation kept).
- Only while free disk is under 25 GiB, and only then, cleans up:
  - copytruncate-rotates and gzips these logs when over 50 MiB, keeping the
    3 newest archives: `/opt/homebrew/var/log/syncthing.log`,
    `~/.ramble/logs/*.log`, `~/Library/Logs/*.log`;
  - deletes regenerable files by age: `/tmp` top-level entries older than
    2 days; `~/.npm/_cacache`, `~/Library/Caches/pip` and `~/.cache/uv`
    entries older than 30 days. `~/Library/Caches/ms-playwright` and
    `~/.cache/huggingface` are never pruned: file age there is download
    time, not last use, and they hold models and browsers still in use
    (Ramble's Wespeaker and Whisper models, Canvas Browser's test browsers).
    Their sizes appear in the top-consumer report.
- Reports recommendations with exact commands, without acting, for idle
  Colima VM disks, inactive git worktrees under /opt/projects, runaway or
  oversized processes, and unlinked open files over 1 GiB.
- Posts a macOS notification (osascript) when free disk is still under
  15 GiB after cleanup or kernel memory pressure is critical or swap use exceeds 16 GiB (macOS grows the swap total on demand, so a percentage would fire all day), at most once per condition per
  hour (state in `~/.local/state/mac-resource-guardian/alerts.json`).
  A Ribbon Field ask was considered and rejected: during a disk or swap
  crisis the agent substrate may itself be crashing, while osascript needs
  only the local system and spends no tokens.

## What it never does

- Never deletes source, git repositories or worktrees, databases
  (`*.sqlite`, `*.db`), Stoic, Ribbon Field or agent-coord state, Colima
  disks, `~/Library/Application Support`, or anything under /opt/projects.
  These are guarded in code in addition to never appearing on the
  allowlist.
- Never kills a process. Runaway processes and unlinked open files are
  recommendations only.
- Never acts when free disk is at or above 25 GiB; it only measures.

## Heavy-job lock

`scripts/guardian_lock.py` is an advisory lock so agents do not pile
Docker/Colima builds, Whisper batches and full browser test suites onto the
machine at once:

```
python3 scripts/guardian_lock.py acquire --kind build   # refuse exit: 1 held, 2 low resources
python3 scripts/guardian_lock.py release --token <token>
python3 scripts/guardian_lock.py status
```

Acquire refuses, saying why, when another live holder holds
`~/.local/state/mac-resource-guardian/heavy-job.lock`, when free disk is
under 15 GiB, swap over 85% or free memory under 8%. A lock whose holder
process has died is taken over as stale.

## Operate

- Dry run (prints what it would do, changes nothing):
  `python3 scripts/mac_resource_guardian.py --dry-run`
- Install: `cp launchd/com.rquinonez.mac-resource-guardian.plist ~/Library/LaunchAgents/ && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rquinonez.mac-resource-guardian.plist`
- Uninstall: `launchctl bootout gui/$(id -u)/com.rquinonez.mac-resource-guardian && rm ~/Library/LaunchAgents/com.rquinonez.mac-resource-guardian.plist`
- Logs: `~/Library/Logs/mac-resource-guardian.stdout.log` and `.stderr.log`
- Tests: `python3 -m pytest -q tests/test_mac_resource_guardian.py tests/test_guardian_lock.py`

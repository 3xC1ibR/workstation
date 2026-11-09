# Agent data backups

This interim backup is independent of Ribbon Field hosting and thread sync.
The launch agent runs daily at 03:15 local time. A calendar event missed during
sleep runs after wake. The job requires the user's login session; it does not
run while the Mac is shut down or the user is logged out.

Restic encrypts and deduplicates snapshots in
`s3://walle-backups-392424878485-us-east-1/agent-data/walle/`.
No `forget`, `prune`, remote deletion, or expiration job is installed.
The backup identity can read and write this prefix and delete temporary locks,
but cannot delete backup data, snapshots, or object versions.

## Contents

The complete existing native data trees are included: `~/.codex/`,
`~/.claude/`, `~/.claude.json`, `~/.kimi-code/`, `~/.gemini/`,
`~/.config/muse/`, `~/.local/share/muse/`, and
`~/.local/state/agent-coord/`. These include Ribbon Field's Antigravity profile,
native attachments, tool outputs, subagents, logs, and configuration. Existing
Claude temporary trees under `/private/tmp/claude-<uid>` and `$TMPDIR` are also
included. Configured provider-home overrides are recognized when present in the
job environment. A standalone Ribbon Field browser data root is included if it
exists. Source symlinks are preserved, not followed.

Every detected SQLite database is copied through SQLite's online backup API and
checked with `PRAGMA quick_check`. The live database and its journal sidecars
are excluded from Restic. The consistent replacement is stored under
`~/.local/state/agent-data-backups/sqlite/<original absolute path>`.
Other files are read while agents continue working; this is a rolling backup,
not an atomic snapshot across every provider. Files created or deleted during
the run can require the following run. Arbitrary project directories and files
outside the listed sources are not included.

## Credentials and recovery

Terraform in `/opt/projects/infra/walle-backups/terraform/` owns the backup IAM
user, scoped policy, and recovery-secret container. Access keys and passwords
never enter Terraform state or Git. After applying the reviewed plan:

```sh
/opt/homebrew/bin/python3.13 /opt/projects/workstation/scripts/backup_agent_data.py --configure
```

This requires an administrator AWS login. It saves the backup IAM key and
Restic password as separate macOS Keychain items, and keeps the recovery
password in AWS Secrets Manager as `walle-backups/agent-data-restic-password`.
It initializes the encrypted repository using the current administrator login,
so the daily identity does not need unrestricted bucket-listing permission.
The daily job uses the scoped key and does not depend on a 12-hour AWS login.
The backup IAM user cannot read Secrets Manager. An administrator can recover
the password and issue a replacement scoped key if this Mac is lost.

## Run and inspect

Install the calendar job once its credentials are configured:

```sh
cp -f /opt/projects/workstation/launchd/com.rquinonez.agent-data-backup.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rquinonez.agent-data-backup.plist
```

Run a backup immediately and inspect its result:

```sh
/opt/homebrew/bin/python3.13 /opt/projects/workstation/scripts/backup_agent_data.py
cat ~/.local/state/agent-data-backups/last-run.json
launchctl print gui/$(id -u)/com.rquinonez.agent-data-backup
```

Runtime files and private logs are under `~/.local/state/agent-data-backups/`.
`last-run.json` records failure as failure. A nonzero Restic exit, including an
incomplete snapshot, is not reported as success. Runs cannot overlap. Local
SQLite staging and the Restic cache use additional disk space; no copy of the
entire source tree is staged. SQLite staging is removed after a successful
upload and retained after a failure for recovery. The initial inventory found
303 SQLite databases; preparing and checking them took about three minutes.

## Restore

Use an empty destination. On the current Mac, the wrapper loads the two Keychain
items without printing their values:

```sh
/opt/homebrew/bin/python3.13 /opt/projects/workstation/scripts/backup_agent_data.py --restic snapshots
/opt/homebrew/bin/python3.13 /opt/projects/workstation/scripts/backup_agent_data.py --restic restore SNAPSHOT_ID --target EMPTY_DIRECTORY
/opt/homebrew/bin/python3.13 /opt/projects/workstation/scripts/backup_agent_data.py --restic check --read-data
```

Restore native trees to their original locations only after stopping the
corresponding client. Overlay each staged SQLite replacement at its recorded
original path. Do not restore old `-wal`, `-shm`, or `-journal` files beside it.
`manifest.json` lists the SQLite source-to-snapshot mapping.

On a replacement machine, an administrator retrieves the recovery password
from Secrets Manager, supplies it through `RESTIC_PASSWORD_FILE`, and uses AWS
credentials that can read the repository. Do not print the password or place
it in a command argument. Run `restic check --read-data` and verify restored
transcripts and SQLite rows before replacing live data.

## Retention settings

`configure_agent_retention.py` sets Claude `cleanupPeriodDays` to `36500`, sets
Codex history persistence to `save-all` without a size cap, removes Muse's
optional `session_retention_days` to retain sessions indefinitely, and disables
Gemini `general.sessionRetention.enabled`. Unrelated settings are preserved.
Original configuration files are saved under the runtime directory. Kimi has
no verified corresponding retention setting; its native tree is backed up.
Managed policy and per-session overrides can still take precedence.

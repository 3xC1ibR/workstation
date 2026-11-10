# Agent data backups

This interim backup is independent of Ribbon Field hosting and thread sync.
The launch agent runs daily at 03:15 local time. A calendar event missed during
sleep runs after wake. The job requires the user's login session; it does not
run while the Mac is shut down or the user is logged out.
It uses low CPU priority and normal disk I/O priority.

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

Every detected SQLite database is copied through SQLite's online backup API.
Its resulting schema is read to confirm that it opens. Restic checksums and
encrypts the stored data; restore verification compares whole-file SHA-256
hashes and representative table counts. Full B-tree integrity audits are not
part of the daily job. The live database and its journal sidecars
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
303 SQLite databases. Historical diagnostic copies can be several gigabytes,
so daily runs avoid a second full read for structural database audits.

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

## Verified deployment

The installed launch agent completed its first backup with exit code `0` on
2026-11-10 at 00:18 UTC. Snapshot:

```text
a2bccc0958040933e4b356b3e1653ac369350f02925a59c4c23e92a012b45595
```

The snapshot contains 120,772 files and 32,467,550,970 source bytes, including
304 online SQLite copies. Restic added 7,581,308,514 bytes of packed data.
The initial upload took about 52 minutes after database preparation. Later
snapshots reuse unchanged content. Local SQLite staging was removed after the
successful upload; no source files were removed.

Remote restore verification passed at 00:21 UTC. It restored sample Codex,
Claude, Muse, and Kimi transcripts and the complete captured Ribbon Field and
Codex metadata databases to an isolated directory. Whole-file SHA-256 hashes
matched all six references. Database table counts matched, including 1,675
Ribbon Field work threads, 26,477 coordination messages, 1,547 browser sessions,
and 3,633 native Codex thread records. This verifies the sampled restored files;
it is not a full restore of all 120,772 files.

`restic check --read-data-subset=5%` checked repository structure and a sample
of stored packs and reported no errors. The verified local restore copies were
then removed. Evidence remains in:

```text
~/.local/state/agent-data-backups/last-run.json
~/.local/state/agent-data-backups/verification-result.json
~/.local/state/agent-data-backups/repository-check.log
```

The recovery password was compared between Keychain and Secrets Manager and
matched. Live IAM policy checks confirmed data read/write access, denial of
data and object-version deletion, and permission to remove temporary locks.
The installed calendar remains daily at 03:15 local time. Current harness
retention settings were rechecked after verification.

# Replies owed in Messages

The exporter writes one row per conversation whose latest ordinary message came
from someone else. By default it includes only one-to-one conversations. The
macOS LaunchAgent refreshes the report at login and every 15 minutes while the
Mac is awake.

## Install on Walle

1. From the reviewed workstation checkout, run `scripts/build_replies_owed_app.sh`.
   This requires Apple's Command Line Tools with Python 3.9 or later and builds
   `/Users/walle/Applications/RepliesOwedExporter.app`.
2. Open **System Settings → Privacy & Security → Full Disk Access**. Click
   **+**, press **Command-Shift-G**, enter
   `/Users/walle/Applications/RepliesOwedExporter.app`, and enable that item
   alone. Leave Terminal, Ribbon Field, and Python permissions as they are.
3. Run the following from the same checkout.

   ```sh
   mkdir -p "$HOME/Library/LaunchAgents"
   job="$HOME/Library/LaunchAgents/com.rquinonez.replies-owed-export.plist"
   install -m 0644 launchd/com.rquinonez.replies-owed-export.plist "$job"
   launchctl bootstrap "gui/$(id -u)" "$job"
   ```

4. Read the timestamp and status after the first scheduled launch.

   ```sh
   report="$HOME/.local/state/replies-owed/replies_owed.json"
   plutil -extract generated_at raw "$report"
   plutil -extract source_status raw "$report"
   ```

For an immediate refresh, run
`open -g -W "$HOME/Applications/RepliesOwedExporter.app"`. To include group
chats in a single refresh, append `--args --include-groups`. The next scheduled
run restores the one-to-one report. For scheduled group inclusion, add those
two strings at the end of the plist's `ProgramArguments` before loading it.

The app's signed native executable contains the exporter source. It starts a
fixed Apple Command Line Tools Python with isolated imports, site initialization
disabled, and a fixed environment. A checkout edit takes effect only after a
rebuild. For an update, unload the job, remove its old Full Disk Access entry,
move the old app to Trash, then repeat the installation with the reviewed source.

## Data and interpretation

The exporter opens `~/Library/Messages/chat.db` read-only. SQLite includes
committed updates in the active write-ahead log. The query selects dates, row
and conversation identifiers, direction, service, participant handles, and event
types. It never selects message text, attributed bodies, attachment contents,
or previews. It sends no messages and makes no network requests.

When available, the local and account-specific `AddressBook-v22.abcddb`
databases under `~/Library/Application Support/AddressBook` supply contact
names. Lookup matches phone numbers or case-insensitive email addresses.
Unavailable, unsupported or ambiguous matches produce a null `display_name`.

The app atomically replaces `~/.local/state/replies-owed/replies_owed.json`
with a mode-0600 file. It contains contact metadata readable by processes
running as this user. Consumers should check both `generated_at` and
`source_status`. An old timestamp can indicate that the Mac slept, the job
stopped, or it could no longer publish the file.

| Status | Meaning |
| --- | --- |
| `ok` | The Messages query succeeded. An empty `replies_owed` array means no qualifying conversations. |
| `permission_denied` | macOS or SQLite denied the read. Check the exact app entry in Full Disk Access, then refresh. |
| `error` | The source was missing, unreadable for another reason, or incompatible. |

A source failure replaces previous results with an empty array and the failure
status. A publication failure preserves the previous file. Successful rows are
ordered by oldest last inbound first. Each row contains the sender's `handle`,
optional `display_name`, the recorded `service`, `is_group`, `last_inbound_at`
in America/Chicago, `waiting_days` in completed 24-hour periods since that
message, and `inbound_count_since_last_reply`. Reactions and group-management
events neither create nor clear an obligation. The `open_url` opens Messages
without sending. For an opted-in group, the URL targets the group and the count
includes all participants since the user's last reply.

## Remove

```sh
launchctl bootout "gui/$(id -u)/com.rquinonez.replies-owed-export"
rm "$HOME/Library/LaunchAgents/com.rquinonez.replies-owed-export.plist"
rm "$HOME/.local/state/replies-owed/replies_owed.json"
rmdir "$HOME/.local/state/replies-owed"
```

Remove **RepliesOwedExporter** from **Full Disk Access**, then move
`~/Applications/RepliesOwedExporter.app` to Trash.

## Test with synthetic data

```sh
uv run --with pytest python -m pytest -q tests/test_export_replies_owed.py
```

The tests create temporary databases, including an active write-ahead log, and
build a temporary app on macOS. They require no access to personal Messages or
Contacts data.

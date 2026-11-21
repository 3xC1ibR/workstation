# Replies owed in Messages

The exporter writes one row per conversation whose latest ordinary message came
from someone else. By default it shows one-to-one conversations where you have
sent an ordinary message at least once and the last inbound message arrived in
the past 180 days. It skips senders whose handle consists of one to six digits.
The macOS LaunchAgent refreshes the report at login and every 15 minutes while
the Mac is awake.

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
`open -g -W "$HOME/Applications/RepliesOwedExporter.app"`. The supplied
LaunchAgent uses the defaults. For a single refresh with different filters,
append `--args` followed by any combination of these options.

| Option | Effect |
| --- | --- |
| `--include-never-replied` | Include conversations with no prior outbound message. |
| `--include-short-codes` | Include senders whose entire handle is one to six digits, including leading zeroes. |
| `--max-age-days N` | Include a conversation if the latest inbound message is at most N × 24 hours old. The default is 180. Set N to 0 to disable the age limit. |
| `--include-groups` | Include group conversations. |

For example, to see first-time senders from the last seven days, append
`--args --include-never-replied --max-age-days 7`. Each filter applies
independently. The next scheduled run restores the defaults. To customize the
scheduled report, add `--args` and each option and value as separate strings at
the end of the plist's `ProgramArguments` before loading it.

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
ordered by shortest wait first. Each row contains the sender's `handle`,
optional `display_name`, the recorded `service`, `is_group`, `waiting_days` in
completed 24-hour periods since the latest inbound message, and
`inbound_count_since_last_reply`. Compare `last_inbound_at` and
`last_outbound_at` to see how long the conversation had been quiet. Both use
America/Chicago with its UTC offset. The exporter checks the full history for
the last outbound message, even when it predates the age window. A never-replied
conversation has a null `last_outbound_at`. Reactions and group-management
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

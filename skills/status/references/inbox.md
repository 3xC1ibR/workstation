# Standalone Status collection

The skill's own page collects generated HTML reports across agents, providers,
and project directories. It uses the same monochrome stylesheet as the reports.
Open a title to read its retained HTML in a separate tab. Dismiss removes that
report from Inbox; Dismissed and All reports retain it, and Restore or Undo brings
it back. Future reports from the same agent still appear.

The viewer has no Ribbon Field dependency. Existing standalone reports remain
portable HTML files, readable and printable without a running viewer.

## Open the collection

```sh
python3 -B <skill-directory>/scripts/status_server.py start
```

Use the printed URL, normally `http://127.0.0.1:8766/`. The viewer starts detached
from the invoking agent and reuses an existing viewer serving that inbox. It
binds only to the local machine. `--port` chooses a different port; it never
replaces another service occupying the requested port.

On macOS, keep the page available after login with:

```sh
python3 -B <skill-directory>/scripts/status_server.py install
```

This installs `~/Library/LaunchAgents/com.workstation.status.plist`. The service
log is `<inbox>/viewer/service.log`. Running `install` again reloads the viewer
after a skill update, preserving reports and dismissal state. To stop login startup, use
`launchctl bootout gui/$(id -u)/com.workstation.status`, then remove that plist.
If a manually started viewer already occupies the port, stop that specific
viewer before installing login startup. Do not stop unrelated processes.

For an isolated development session, run `serve --inbox /temporary/inbox --port 0`
in a terminal. It prints its selected URL and stops with Control-C. Production
and test receipts must use separate inbox directories.

## Automatic registration

`build_status.py` registers every generated report by default. Provide actual
`--workspace`, `--agent`, `--provider`, and, when known, `--thread-id` metadata.
The thread ID defaults from existing agent environment context when available.
Unknown metadata remains unknown.

The default inbox is `~/.local/state/agent-status/inbox`. `AGENT_STATUS_INBOX`
selects another directory for producers; the viewer accepts the same variable
or `--inbox`. All producers and the collection must use the same inbox.
Registration works even when the viewer is stopped. New reports appear while
the page is open or when it is refreshed.

Snapshots are immutable. Registering the same document and origin again preserves
the original copy and dismissal state. A new report creates a new item, even
when the agent reuses its output filename. Removing the original file does not
remove its retained copy.

To register an existing report without changing its observations:

```sh
python3 -B <skill-directory>/scripts/register_status.py /path/status.json \
  --html /path/status.html --workspace /absolute/project/path \
  --agent stable-agent-name --provider claude
```

Do not register test fixtures or previews as operational reports. Do not change
`generated_at` merely to make an old report look current.

## Other machines

An agent on a different machine can transfer its JSON and HTML to the collection
host through an existing authorized connection, then run the registration command
there with its original workspace, agent, and provider metadata. Independent
machines do not automatically share local directories. Do not expose the local
viewer publicly or upload private reports to another service without a request.

## Storage contract

Each producer publishes `reports/<sha256>/manifest.json`, `report.json`, and
`report.html` via an atomic directory rename. The version-1 manifest records
title, subject, summary, generation and receipt times, and origin metadata. The
ID hashes the canonical document and origin. Hidden staging directories are
never listed. Dismissal is stored separately in `dismissed/<sha256>.json` and
is never changed by report generation. Previous inbox records remain compatible.

Only registered reports are served. Report HTML cannot execute scripts or make
network requests; native evidence disclosures and explicit source links work.
The page refreshes its collection; individual reports retain their recorded
observation times.

# Shared Status inbox

Ribbon Field's **Status** page (`/status` on its existing server) collects reports
independently of the current project or conversation. The Inbox view contains
undismissed reports. Dismissed and All reports views retain history; Restore or
Undo puts a report back in the inbox. These actions do not archive its thread,
delete files, or suppress the next report from its agent.

## Automatic registration

The standard `build_status.py` command registers every generated report by
default. Provide `--workspace`, `--agent`, `--provider`, and, when known,
`--thread-id` to identify its origin. The thread ID defaults from Agent Coord or
Codex environment context when available. Unknown metadata remains unknown.

The default inbox is `~/.local/state/agent-status/inbox`. All workspaces and
providers running under this user share it. `AGENT_STATUS_INBOX` can select a
different directory for an isolated test or an intentionally shared installation;
the producer and Ribbon Field must use the same directory.

Snapshots are immutable. Re-registering the same document and origin is
idempotent and preserves dismissal. A newly generated document creates a new
inbox item, including when its originating `status.html` path is reused. The
retained copy survives removal of the original report file.

To register an existing JSON/HTML report without regenerating its observations:

```sh
python3 -B <skill-directory>/scripts/register_status.py /path/status.json \
  --html /path/status.html --workspace /absolute/project/path \
  --agent stable-agent-name --provider codex
```

Do not register validation fixtures or illustrative previews as operational
reports. Do not alter `generated_at` merely to make an old report look current.

## Other machines

The inbox spans providers and project directories, not separate unconnected
machines automatically. For an agent on another machine, transfer its JSON and
HTML to the inbox host through the existing authorized connection, then run the
registration command there. Keep the original workspace, agent, and provider
metadata. Do not create a publicly exposed server or upload private reports to
an unrelated service. Paired Ribbon Field devices use the same host's dismissal
state; they do not keep separate browser-only copies of it.

## Storage contract

Each producer publishes an immutable `reports/<sha256>/` directory containing
`manifest.json`, `report.json`, and `report.html`, via an atomic directory rename.
The version-1 manifest holds ID, title, subject, summary, generated and received
timestamps, plus origin metadata. The ID hashes the canonical document and
origin. Hidden staging directories are never displayed. User dismissal is stored
separately in `dismissed/<sha256>.json` and is not changed by producers.

Only explicitly registered files are served, in an isolated report viewer.
Scripts and network requests inside report HTML are disabled; native evidence
disclosures still work. The inbox refreshes while open; the report itself remains
a snapshot of its recorded observation time.

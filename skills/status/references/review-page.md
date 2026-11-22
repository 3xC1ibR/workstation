# Review page

The skill's own page shows operations and proactive deliveries from every
agent, provider, and project directory on this host, and reads open asks from
Ribbon Field. It has no Ribbon Field dependency: without Ribbon Field it shows
reports and deliveries and states that asks are unavailable.

- **Needs you:** open asks from Ribbon Field, blocking first. Each opens its
  conversation in Ribbon Field, where it is answered. Asks are never stored here.
- **Proactive work:** deliveries awaiting a response, unread first. See
  [deliveries.md](deliveries.md).
- **Operations:** one row per operation with its latest version. A row is unread
  until that version is opened. Dismiss hides it until its next version.
- **Open / Done / All** and search apply to the whole page.

Opening an operation shows its latest report with a version menu for earlier
versions and, above the report, the open asks from that operation's
conversations and workspace. Reports with response fields are answered in the
report; see [responses.md](responses.md).

## Open the page

```sh
python3 -B <skill-directory>/scripts/status_server.py start
```

Use the printed address, normally `http://127.0.0.1:8766/`. The service starts
detached from the invoking agent and reuses a running service for the same
store. It binds only to this machine. `--port` chooses another port; it never
replaces another service occupying that port.

On macOS, keep the page available after login with:

```sh
python3 -B <skill-directory>/scripts/status_server.py install
```

This installs `~/Library/LaunchAgents/com.workstation.status.plist`. The log is
`<inbox>/viewer/service.log`. Run `install` again after a skill update: it
reloads the service and preserves reports, deliveries, responses, and the
recorded public address. To stop login startup, use
`launchctl bootout gui/$(id -u)/com.workstation.status`, then remove that plist.
If an earlier or manually started Status process occupies the port, `install`
says so: confirm with `lsof -nP -iTCP:8766 -sTCP:LISTEN` that it is
`status_server.py` for this inbox, stop that specific process, and the login
service starts by itself. Do not stop unrelated processes.

For development, run `serve --inbox /temporary/inbox --port 0` in a terminal. It
prints its address and stops with Control-C. Production and test data must use
separate inbox directories.

## Another device on the tailnet

The service listens on loopback only. To read and respond from a phone, relay a
path of the machine's Tailscale address to it and tell the service that address:

```sh
/Applications/Tailscale.app/Contents/MacOS/Tailscale serve --bg --set-path /status http://127.0.0.1:8766
python3 -B <skill-directory>/scripts/status_server.py install --public-url https://<machine>.<tailnet>.ts.net/status
```

`tailscale serve` is reachable only from the user's tailnet. Add this one path;
do not change other serve entries, and never use `tailscale funnel`, which is
public. The service then accepts that host besides loopback, prefixes links and
assets with the path, and accepts writes from that origin with the page token.
Other applications served from the same tailnet host share its origin, so treat
them as trusted with this page. `publish_delivery.py` and `build_status.py`
print the public address of each item when one is recorded. Remove the relay
with `tailscale serve --set-path /status off`.

Ribbon Field links (`agentcoord://thread/<id>`) open Ribbon Field on the device
where they are tapped. File paths in a delivery exist only on the Mac; retained
documents and attachments are readable everywhere.

## Registration

`build_status.py` registers every generated report by default. Provide actual
`--workspace`, `--agent`, `--provider`, and, when known, `--thread-id` metadata,
and `--operation` for an operation that spans conversations or worktrees. The
thread ID defaults from the agent environment when available. Unknown metadata
remains unknown.

The default inbox is `~/.local/state/agent-status/inbox`. `AGENT_STATUS_INBOX`
selects another directory for producers; the service accepts the same variable
or `--inbox`. All producers and the service must use the same inbox.
Registration works while the service is stopped. New items appear while the
page is open or when it is refreshed.

Report versions are immutable. Registering the same document and origin again
preserves the original copy and its dismissal. A changed report is a new
version of its operation, even when the agent reuses its output filename.
Removing the original file does not remove its retained copy.

To register an existing report without changing its observations:

```sh
python3 -B <skill-directory>/scripts/register_status.py /path/status.json \
  --html /path/status.html --workspace /absolute/project/path \
  --agent stable-agent-name --provider claude --operation operation-key
```

Do not register test fixtures or previews as operational reports. Do not change
`generated_at` merely to make an old report look current.

## Operation identity

Every report belongs to one operation, identified by the first of these that
its origin records:

1. the explicit operation key (`--operation`), the same on every workspace;
2. the workspace with the stable agent name;
3. the workspace with the originating conversation;
4. the workspace with the report title.

Reports registered before operations existed group by rules 2 to 4 without
being rewritten. An agent that changes its name or workspace starts a new
operation unless it passes the same explicit key.

## Asks from Ribbon Field

The service runs `agent-coord ask --list --all-sessions --status open` when the
page asks and keeps the answer in memory for about 20 seconds. It finds the
command at `AGENT_COORD_CLI`, then `~/.local/bin/agent-coord`, then `PATH`. An
operation shows the asks filed from its conversations or from its workspace
directory. There is no supported authenticated path for this page to resolve an
ask, so every ask opens its Ribbon Field conversation. When the command is
missing, too old to list asks, slow, or failing, the page states that asks are
not shown and why; it does not show an empty list.

## Measurement

The page records content-free usage events in `<inbox>/usage/<year-month>.jsonl`:
page opens, item opens, and responses, each with a time, the view, an item
identifier, whether the viewport was narrow, and whether the request came through
the public address. No titles, text, notes, or answers are recorded.

```sh
python3 -B <skill-directory>/scripts/status_metrics.py --days 7
```

The output reports, for the period: page opens per day; for proactive
deliveries, the median minutes from delivery to first open and to first
response, and the shares accepted, dismissed, ignored, and pending; and opens
per operation report. `--since`, `--until`, and `--timezone` adjust the period;
`definitions` in the output states how each share is counted.

## Other machines

An agent on a different machine can transfer its JSON and HTML to this host
through an existing authorized connection, then run the registration command
here with its original workspace, agent, and provider metadata. Independent
machines do not share local directories. Do not expose the service publicly or
upload private reports to another service without a request.

## Storage contract

All records live under the inbox directory.

| Path | Contents | Written by |
| --- | --- | --- |
| `reports/<sha256>/` | `manifest.json`, `report.json`, `report.html`; immutable | producers, by atomic directory rename |
| `dismissed/<sha256>.json` | dismissal time of one report version | the user, through the page |
| `operation-state/<operation>.json` | the version last opened and when | the page |
| `responses/<sha256>.json` | answers to a report's response fields, with a revision | the user |
| `response-keys/<sha256>` | access key restricting a portable report to its own answers | producers |
| `deliveries/<sha256>/` | `delivery.json`, optional `document.md`, `attachments/<n>`; immutable | producers |
| `delivery-state/<sha256>.json` | read time, current response, discussion time, history | the user |
| `usage/<year-month>.jsonl` | usage events | the service |
| `viewer/` | service log and the recorded public address | the service |

The version-1 report manifest records title, subject, summary, generation and
receipt times, origin metadata (with the optional operation key), and
`response_field_count`. A report ID hashes its canonical document and origin.
Hidden staging directories are never listed. Earlier records remain readable.

Only registered items are served. Reports are rendered from their validated
JSON with the current design and run only the service's own script files.
A record retained as HTML alone is served sandboxed, without script or network
access. Delivery documents are rendered from Markdown with all markup escaped;
only `http`, `https`, and `agentcoord` links and links to the delivery's own
attachments are active.

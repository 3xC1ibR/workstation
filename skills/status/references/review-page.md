# Review page

The skill's own page shows operations and proactive deliveries from every
agent, provider, and project directory on this host, and reads open asks from
Ribbon Field. It has no Ribbon Field dependency: without Ribbon Field it shows
reports and deliveries and states that asks are unavailable.

- **Needs you:** open asks from Ribbon Field, blocking first. Open one to read
  it in full and answer it; the answer goes to Ribbon Field, which stores it.
- **Proactive work:** one row per delivery with its latest version, newest
  first. A delivery leaves Open once he has responded and has seen its latest
  version; a newer version brings it back. See [deliveries.md](deliveries.md).
- **Operations:** one row per operation with its latest version. A row is unread
  until that version is opened. Dismiss hides it until its next version.
- **Open / Done / All** and search apply to the whole page.

Opening an operation shows its latest report with a version menu for earlier
versions and, above the report, the open asks from that operation's
conversations and workspace. Reports with response fields are answered in the
report; see [responses.md](responses.md).

The page is a host for what agents build. A report version or a delivery may
carry one interactive document, shown inside the item's page under the summary
and response controls, in a sandbox that never has the page's origin. See
[interactive-documents.md](interactive-documents.md).

## Links stay in the page

Only another website opens a new tab. Everything on this host opens in the
same tab with a way back:

- A link to a report, a delivery, or an attachment opens that page. An address
  written for the tailnet host or for `127.0.0.1` leads to the same page on
  the address in use.
- A link to another application on the tailnet host (a plain path outside the
  review page, such as `/thanksgiving/`, or a full address there) opens
  `<page>/embedded?address=/thanksgiving/&from=<item-id>`: the page's frame
  with a link back to the item and "Open on its own", around the application
  in the same sandbox as an interactive document. When `from` names the item
  whose interactive document is that same address, the view keeps that item's
  saved document state, as the item's page does; otherwise it keeps none. On
  the local address, where the application is not served, that view links to
  itself on the tailnet address.
- An address on the tailnet host that cannot be framed (its root, or one with
  a query or fragment) is an ordinary link in the same tab.
- A bare path is a file of the Mac, shown as text with Copy path, when it
  begins with a directory that exists on the Mac or ends in a file suffix
  other than `.html`. Without a recorded tailnet address every bare path is a
  file.

This applies to Markdown write-ups and attachments, delivery link lists,
report sources, addresses in asks, and links an interactive document asks the
page to open.

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
prints its address and stops with Control-C. Only `install` records the public
address used in printed links; a development `serve` never changes it. Production and test data must use
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
Other applications served from the same tailnet host share its origin: opened
at their own address they are trusted with this page and with Ribbon Field.
Shown inside the review page they run in a sandbox without that origin.
`publish_delivery.py` and `build_status.py`
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

Ribbon Field owns asks. This page never stores an ask or an answer.

**Reading.** The service runs `agent-coord ask --list --all-sessions --status open`
and keeps the listing in memory. A page refresh never waits for that command:
it receives the last listing at once, and a listing older than about 20 seconds
is renewed by one background read. Only the service's first read and the read
after an answer given on the page wait for Ribbon Field. It finds
the command at `AGENT_COORD_CLI`, then `~/.local/bin/agent-coord`, then `PATH`.
An operation shows the asks filed from its conversations or from its workspace
directory. A row leads with one line (the question's first line, or its first
sentence when that line is long); opening the row shows the whole question,
what it unblocks, and the agent's context, with web addresses as links. When
the command is missing, too old, slow, or failing, the page states that asks
are not shown and why; it does not show an empty list.

**Answering.** The page offers the resolutions Ribbon Field lists for the
ask's kind (choices and free text for a decision; Done or Not done; Approve or
Decline; Accept or Request changes; Grant or Decline), an optional note,
Snooze, and Dismiss. Ribbon Field records the resolution as the user's and
wakes the asking agent through its inbox. After Ribbon Field accepts, the page
reads the list again. A refused request keeps the typed text and shows Ribbon
Field's reason. The answer reaches Ribbon Field by one of two paths, chosen by
the address the page is open on:

- **Tailnet address.** The page and Ribbon Field's web interface share one
  origin, so the page's script sends the resolution straight to Ribbon Field
  with the browser's own Ribbon Field pairing:
  1. `GET /api/browser/config` returns the request token when the browser is paired.
  2. `POST /api/browser/asks/<id>` with `{resolution, option?, answer?, note?}`
     resolves the ask; `POST /api/browser/asks/<id>/snooze` with `{until}` snoozes it.

  Ribbon Field checks the paired-device cookie, the token, and the origin. The
  Status service takes no part and refuses `/api/ask-resolution` on this
  address. When the browser is not paired (Ribbon Field answers 401), the page
  says so and names the local address; pair the browser from Ribbon Field on
  the Mac (Remote access).
- **Local address** (`http://127.0.0.1:8766`). No pairing is needed. The page
  posts `{id, body, snooze?}` to the Status service's `POST /api/ask-resolution`
  under the same Origin and token rules as every other write, and the service
  forwards the resolution to Ribbon Field's loopback interface, whose address
  it reads from Ribbon Field's discovery record. Ribbon Field authorizes
  loopback requests itself, so this adds no authority beyond what any process
  on the Mac already has, and the service holds no Ribbon Field credential.
  When Ribbon Field is not running, the page says so and keeps the typed text.

Neither path is open to an interactive document: its sandbox has no origin, so
Ribbon Field and the Status service refuse its requests.

**Replying without resolving.** When no offered answer fits, **Reply** sends
the words in the ask's text line to the asking conversation as a user message
that names the ask number and title, and leaves the ask open. On the local
address the Status service forwards it (`POST /api/ask-reply {id, text}`,
local address only) to Ribbon Field's loopback interface,
`POST /api/browser/sessions/<conversation>/queue`; on the tailnet address the
page's script calls that same Ribbon Field route with the browser's pairing.
Ribbon Field delivers a queued message when the conversation is idle. The ask
then shows "Replied" until the agent resolves, replaces or withdraws it; that
mark is read from the usage log (an `ask_resolution` event with action
`replied`), which holds the ask number and a time, never the words. The
conversation is taken from Ribbon Field's listing, not from the page. A reply
to an ask from a conversation Ribbon Field cannot message (a terminal session)
fails with its reason; use **Reply in conversation**, which opens the thread.

## Measurement

The page records content-free usage events in `<inbox>/usage/<year-month>.jsonl`:
page opens, item opens, interactive document opens, responses, and ask
resolutions made on the page, each
with a time, the view, an item identifier, whether the viewport was narrow, and
whether the request came through the public address. No titles, text, notes, or
answers are recorded; an ask resolution records the ask's number and the
resolution's name only.

```sh
python3 -B <skill-directory>/scripts/status_metrics.py --days 7
```

The output reports, for the period: page opens per day; for proactive
deliveries, the median minutes from delivery to first open and to first
response, and the shares accepted, dismissed, ignored, and pending; asks
resolved on the page by resolution (compare with `agent-coord ask --metrics`,
which counts every resolution wherever it was made); the number of times an
interactive document was shown, by item kind; and opens per operation
report. A delivery with several versions is counted once, from the arrival of
its first version. `--since`, `--until`, and `--timezone` adjust the period;
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
| `reports/<sha256>/` | `manifest.json`, `report.json`, `report.html`, optional `interactive.html`; immutable | producers, by atomic directory rename |
| `dismissed/<sha256>.json` | dismissal time of one report version | the user, through the page |
| `operation-state/<operation>.json` | the version last opened and when | the page |
| `responses/<sha256>.json` | answers to a report's response fields, with a revision | the user |
| `response-keys/<sha256>` | access key restricting a portable report to its own answers | producers |
| `deliveries/<sha256>/` | one version: `delivery.json`, optional `document.md`, `attachments/<n>`, optional `interactive.html`; immutable | producers |
| `delivery-state/<series>.json` | read time and version, current response, discussion time, history; each response names its version | the user |
| `document-state/<series or operation>.json` | what an item's interactive document saved: `{state, saved_at, revision, version}` | the page, for the document |
| `usage/<year-month>.jsonl` | usage events | the service |
| `viewer/` | service log and the recorded public address | the service |

The version-1 report manifest records title, subject, summary, generation and
receipt times, origin metadata (with the optional operation key),
`response_field_count`, and `interactive` when the version has an interactive
document. A report ID hashes its canonical document and origin, and its
interactive document when it has one. A delivery manifest also records `key`
or `series` when it is a version of a living delivery. A delivery's series is
the hash of its key, the series it joined through `--replaces`, or its own
identifier, so records written before versions existed are read unchanged.
Hidden staging directories are never listed. Earlier records remain readable.

Only registered items are served. Reports are rendered from their validated
JSON with the current design and run only the service's own script files.
A record retained as HTML alone is served sandboxed, without script or network
access. Delivery documents are rendered from Markdown with all markup escaped;
only `http`, `https`, and `agentcoord` links and links to the delivery's own
attachments are active.

Agent-built HTML is served by two routes only, `<page>/deliveries/<id>/interactive`
and `<page>/reports/<id>/interactive`, always with a `Content-Security-Policy`
`sandbox` directive, and is shown in a sandboxed frame; it is never written
into a page. `<page>/document_bridge.js` is the one file readable from the
sandbox. The frame is given one browser permission, `clipboard-write`. The
pages' own policy allows frames from this origin and the recorded
tailnet origin and is otherwise unchanged. An interactive document saves
state through the page: `POST /api/document-state` with `{kind, id, state}`
(`kind` is `delivery` or `report`, `id` the latest version) under the same
Origin and token rules as every other write, and `GET /api/document-state/<kind>/<id>`.
Requests from the sandbox itself carry an opaque origin and are refused.

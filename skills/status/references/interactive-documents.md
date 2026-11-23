# Interactive documents

The review page is a host for what agents build. A delivery, or a version of
an operation report, may carry one interactive document: anything a browser
can run. The page shows it inside the item's own page, across the whole column
and as tall as its content, under the summary and the response controls. The
page's frame stays around it: title, summary, response controls, the
operation's asks, version history, and the way back.

## When to use one

| Content | Use |
| --- | --- |
| A plan to adjust, a picker, a calculator, a timeline, a comparison to filter, data to explore | An interactive document |
| A finding, a status, a short recommendation, a table to read | The structured report or the Markdown write-up |

The title, summary, recommended default, and decision are still required and
must stand alone: they are what the list shows, what he answers, and what
remains if the document fails to load. The structured report and the Markdown
write-up stay available beside an interactive document and render as before.
Do not move the decision into the document; a document can only propose a
response (see [Propose a response](#propose-a-response)).

## Publish

An item version carries at most one interactive document, in one of two forms.

**Document.** One self-contained UTF-8 HTML file of at most 4 MB. Scripts and
styles may be inline or loaded from the network. The file is retained with the
item, so it is readable from any device and never changes.

```sh
python3 -B <skill-directory>/scripts/publish_delivery.py delivery.json --interactive /absolute/path/plan.html ...
python3 -B <skill-directory>/scripts/build_status.py status.json --output status.html --interactive /absolute/path/explorer.html ...
python3 -B <skill-directory>/scripts/register_status.py status.json --html status.html --interactive /absolute/path/explorer.html ...
```

**Address.** The path of another application served on the same tailnet host,
such as `/thanksgiving/`. The path is recorded; the service never fetches it,
and the application keeps serving its own current content.

```sh
python3 -B <skill-directory>/scripts/publish_delivery.py delivery.json --embed /thanksgiving/ ...
python3 -B <skill-directory>/scripts/build_status.py status.json --output status.html --embed /thanksgiving/ ...
```

An address starts with `/`, contains only letters, digits, `.`, `_`, `~`, and
`-` between slashes, and has no `..`, host, scheme, query, or fragment. It is
not `/` alone and not a path of the review page itself. `--interactive` and
`--embed` exclude each other, and neither applies with `--no-register`.

An address is shown on the tailnet address only. On `http://127.0.0.1:8766`,
where that path does not exist, the item's page says the document is served on
the tailnet address and links to the item there.

The item's record gains `interactive`: `{"kind": "document", "address": null}`
or `{"kind": "address", "address": "/thanksgiving/"}`. An interactive document
is part of what was published: changing it yields a new version of the
operation, or of a delivery published with `--key` or `--replaces`.

## Isolation

The tailnet host is one origin shared by the review page, Ribbon Field, and
every other application served there. A script with that origin could act as
the user in Ribbon Field. An interactive document therefore **never receives
that origin**:

- The page embeds it in
  `<iframe sandbox="allow-scripts allow-forms allow-modals allow-popups allow-downloads">`
  with `referrerpolicy="no-referrer"`. There is no `allow-same-origin`, no
  top navigation, and no `allow-popups-to-escape-sandbox`.
- A retained document is served only at `<page>/deliveries/<id>/interactive`
  and `<page>/reports/<id>/interactive`, always with
  `Content-Security-Policy: sandbox allow-scripts allow-forms allow-modals allow-popups allow-downloads; frame-ancestors 'self'`.
  It has an opaque origin even when that address is opened directly in a tab.
- Agent HTML is never written into a page of the review page.

Nothing else is restricted. Inside the sandbox a document may run any script,
load scripts, styles, images, fonts, and media from the network, submit forms,
open dialogs and windows, and start downloads. What follows from the opaque
origin:

- No cookies, `localStorage`, `sessionStorage`, IndexedDB, or service workers.
  Keep state in memory, or save it through the page (see
  [Save and load state](#save-and-load-state)).
- `fetch` and `XMLHttpRequest` succeed only against servers that answer
  cross-origin requests for `Origin: null` without credentials
  (`Access-Control-Allow-Origin: *` or `null`). Requests to the review page's
  API and to Ribbon Field fail; that is intended.
- Module scripts and web fonts are fetched with the same cross-origin rule and
  need that header. Classic scripts, styles, and images load without it.
- The document cannot read or navigate the page around it. Windows it opens
  stay in the sandbox.
- For the page's light and dark themes, declare `color-scheme: light dark` and
  style both. A document that declares nothing is shown on a light background.

Never place a credential in a document. Everything it contains is readable by
whoever can open the item.

## The bridge

A document reaches the page only through `window.postMessage`. Load the helper
and use `window.StatusDocument`:

```html
<script src="../../document_bridge.js"></script>
```

The relative address is correct for every retained document on both the local
and the tailnet address. An embedded application loads it from the review
page's path on the host, for example `/status/document_bridge.js`. Without the
helper a document still displays, at a fixed height and without the functions
below. Opened outside the review page, `StatusDocument.embedded` is `false`,
saving and loading reject, and the other calls do nothing.

| Call | Effect |
| --- | --- |
| (automatic) | Reports the document's height whenever it changes, so the frame is as tall as the content, from 120 to 20,000 px. `StatusDocument.resize(height)` sets a height explicitly. |
| (automatic) | Hands link clicks to the page (see [Links](#links)). |
| `StatusDocument.saveState(value)` | Promise of `{saved_at}`. Saves any JSON value up to 64 KB for the item. |
| `StatusDocument.loadState()` | Promise of `{state, saved_at}`; `state` is `null` when nothing is saved. |
| `StatusDocument.propose({action, choice?, note?})` | Asks the page to show a proposed response to a delivery. |
| `StatusDocument.open(href)` | Asks the page to open an address. |

The page accepts a message only from the item's own frame, only as a plain
object with one of the types below, and only within the limits; anything else
is ignored without a reply.

| Message from the document | Fields | Reply from the page |
| --- | --- | --- |
| `status:resize` | `height` (number) | none |
| `status:state:save` | `state` (JSON, at most 64 KB), `request?` (integer) | `status:state:saved` `{ok, saved_at?, request}` |
| `status:state:load` | `request?` | `status:state` `{available, state, saved_at, request}` |
| `status:propose` | `action` (`accept` or `dismiss`), `choice?`, `note?` (at most 4000 characters) | none |
| `status:open` | `href` (at most 2000 characters) | none |

The page sends `status:ready` when it starts listening; the helper then
repeats the height and any unanswered request, so a document that loads first
loses nothing.

### Save and load state

State is **what the document saved, not a response and never an approval**:
the selections, filters, or draft values that make the document open the way
he left it. Treat it as context for your next step, and take authority only
from his recorded response.

- One value per item: every version of a delivery shares it, and every report
  version of an operation shares it. Each save replaces the value.
- Only the latest version saves. An earlier version loads the value and its
  saves are refused.
- Saves are sent at most once a second; the newest value wins.
- The store is `<inbox>/document-state/<series or operation>.json`:
  `{state, saved_at, revision, version}`, where `version` is the item version
  that saved.

Read it without the service, with his responses:

```sh
python3 -B <skill-directory>/scripts/read_responses.py --delivery <delivery-or-series-id>
python3 -B <skill-directory>/scripts/read_responses.py --report <receipt-id>
```

Each record carries `interactive` and `document_state`. `document_state` is
`null` for an item without an interactive document,
`{"state": null, "saved_at": null, "revision": 0, "version": null}` when
nothing is saved, and has `"unreadable": true` when the stored value is
damaged. `--since` also selects items whose state was saved after that time.

### Propose a response

A document on a delivery may propose a response. The page shows the proposal
in its own response panel, in its own words ("The document proposes: accept
'Ham'." with **Confirm** and **Ignore**), and records it only when he chooses
**Confirm** there. It is then an ordinary response, validated and stored like
any other. **A document can never record a response by itself.**

- `action` is `accept` or `dismiss`. For `accept`, `choice` is
  `"recommended_default"` (the default) or exactly one of the delivery's
  `decision.options`; any other choice is ignored.
- `note` accompanies the response as his note would.
- The page accepts one proposal a second, on the latest version only. Reports
  have no proposals; use `response_fields` for questions in a report.

### Links

A sandboxed document cannot navigate the page, so the helper hands each link
click to the page, which decides:

| Address | Opens |
| --- | --- |
| A report, delivery, or attachment of the review page | In the same tab |
| A plain path of another application on the tailnet host | In the same tab, framed by the review page with a way back |
| `http` or `https` on another host | In a new tab |
| `agentcoord://` | Ribbon Field |
| Anything else, including any address on the tailnet host with a query | Ignored |

Links within the document (`#section`), links to pages under the document's
own directory (an embedded application's other pages), and links with a
`download` attribute stay in the frame.

## Example

```html
<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Guest count</title>
<style>:root { color-scheme: light dark; font: 15px/1.5 system-ui, sans-serif; }</style>
<script src="../../document_bridge.js"></script>
<label>Guests <input id="guests" type="number" min="2" max="20" value="9"></label>
<p id="turkey"></p>
<button id="propose" type="button">Propose this order</button>
<script>
  const guests = document.getElementById("guests");
  const show = () => { document.getElementById("turkey").textContent = `Turkey: ${(guests.value * 0.6).toFixed(1)} kg`; };
  guests.oninput = () => { show(); StatusDocument.saveState({guests: Number(guests.value)}).catch(() => {}); };
  document.getElementById("propose").onclick = () =>
    StatusDocument.propose({action: "accept", choice: "recommended_default", note: `${guests.value} guests`});
  StatusDocument.loadState().then(({state}) => { if (state) guests.value = state.guests; }).catch(() => {}).finally(show);
</script>
</html>
```

```sh
python3 -B <skill-directory>/scripts/publish_delivery.py delivery.json \
  --interactive /absolute/path/guests.html --key thanksgiving-plan \
  --workspace /absolute/project/path --agent stable-agent-name
```

## Make an application embeddable

An application served at its own path on the tailnet host can be an item's
interactive document (`--embed /thanksgiving/`), and any link to it from a
write-up, a link list, a report source, or a document opens it framed by the
review page at `<page>/embedded?address=/thanksgiving/&from=<item-id>`, with a
link back to the item and "Open on its own". Both use the same sandbox, so
the application must work with an opaque origin:

- **No cookies and no same-origin requests.** A session cookie is not sent and
  cannot be read. The application's own `fetch` calls are cross-origin: they
  succeed only if its server answers `Origin: null` without credentials, for
  example with `Access-Control-Allow-Origin: *`. An application that needs a
  signed-in session cannot work embedded; link to it instead.
- **Subresources load normally:** scripts, styles, images, and media by
  relative or absolute address. Module scripts and fonts need the
  cross-origin header above. Do not send `Cross-Origin-Resource-Policy: same-origin`
  on files the embedded page loads.
- **Allow framing by the host.** Do not send `X-Frame-Options: DENY`; a
  `frame-ancestors` policy must include the host's origin.
- **Size and links.** Load `<review page path>/document_bridge.js` to size the
  frame to the content and to open other items and applications through the
  page. Without it the frame has a fixed height and scrolls inside.
- **Direct visits are not sandboxed.** Opened at its own address, outside the
  review page, the application has the host's origin like any page there.
  Embedding protects the user from the application only while he reads it
  inside the review page.

The service does not proxy an application. A proxy would turn the Status
service into a relay to local ports and still could not rewrite the absolute
paths an application uses.

## Limits

| Limit | Value |
| --- | --- |
| Retained document | One UTF-8 HTML file, at most 4 MB |
| Interactive documents per item version | One (a document or an address) |
| Embedded address | At most 500 characters |
| Saved state | Any JSON value, at most 64 KB |
| Frame height | 120 to 20,000 px |
| Proposal note | At most 4000 characters |

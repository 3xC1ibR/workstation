# Proactive deliveries

A delivery is finished work the user did not request: research, a prepared
decision, a fix on a branch, a plan. It enters the proactive feed of the review
page, where the user chooses when to read it and how to respond. Requested work
is not a delivery; reply where it was requested.

## Publish

```sh
python3 -B <skill-directory>/scripts/publish_delivery.py /absolute/path/delivery.json \
  --document /absolute/path/delivery.md \
  --attach /absolute/path/options.md --attach /absolute/path/REPORT.md \
  --workspace /absolute/project/path --agent stable-agent-name --provider claude \
  --thread-id <ribbon-field-conversation-id>
```

```json
{
  "title": "Ribbon Field CI is green again (draft PR #3)",
  "summary": "Every CI run on main had failed since Oct 28. On the draft PR all three jobs pass. It found three real bugs; one can affect you on travel networks.",
  "recommended_default": "Review and merge PR #3, then close Beads agent-coord-dqo3.",
  "decision": {"question": "Merge it, or tell me what to change?", "options": ["Hold: I want changes first"]},
  "category": "Projects",
  "links": [
    {"label": "Pull request #3", "target": "https://github.com/owner/repository/pull/3"},
    {"label": "Work thread", "target": "agentcoord://thread/<conversation-id>"},
    {"label": "Full report", "target": "/absolute/path/REPORT.md"}
  ]
}
```

| Field | Required | Contents |
| --- | --- | --- |
| `title` | yes | What it is, at most 300 characters. |
| `summary` | yes | One paragraph, at most 2000 characters: what was done and what it means for him. |
| `recommended_default` | no | What happens if he chooses **Do it**. One concrete action you are ready to carry out or have prepared for him. |
| `decision` | no | `question`: the single decision. `options`: up to 6 alternatives to the recommended default, each a button. |
| `category` | no | Short label such as People, Money, Health, Learning, Travel, Projects, Tools. |
| `links` | no | Up to 20 `{label, target}`. Targets are `http(s)` addresses, `agentcoord://` links, or absolute file paths. |
| `thread` | no | `agentcoord://thread/<id>` for **Discuss**. Defaults to `--thread-id`, which defaults to the publishing conversation. |
| `created_at` | no | When the work was finished, ISO 8601 with a timezone. Defaults to the publication time. |

Unknown fields are errors. `--document` is the full write-up in Markdown; it is
retained and shown on the delivery's page, so it is readable from a phone.
`--attach` retains up to 12 text files of at most 2 MB each (Markdown, text,
JSON, CSV, logs, code, patches). A relative link in the document to an
attachment's file name, such as `[options](options.md)`, opens the retained
copy, and so does a link target whose file name matches an attachment. Other
file paths are shown as text with a Copy path control, because they exist only
on the Mac. Images and binary files are not retained; link to them.

The command prints
`{"delivery": "<id>", "series": "<id>", "version_number": 1, "url": "...", "local_url": "..."}`.
`url` is present, and comes first, when the service has a recorded tailnet
address: give the user that link, because it opens on every device. `local_url`
opens only on the Mac and is the fallback. Publishing
the same delivery again returns the same identifier. Each published version is
immutable.

Write for a reader deciding in a minute: lead with what it is, state the
recommended default as an action, and ask at most one decision. Offer **Do it**
only for something within your authority once he accepts it.

`--interactive /absolute/path/file.html` or `--embed /path/` adds one
interactive document, shown inside the delivery's page under the response
controls: a plan to adjust, a picker, a calculator, a timeline, data to
explore. Use the Markdown write-up for simple content. See
[interactive-documents.md](interactive-documents.md).

## Versions

A delivery can live: a plan that is revised, a draft that is corrected, a
result that is updated. Publish the revision as a **new version of the same
delivery**, so the page keeps one row and his responses stay with it.

```sh
python3 -B <skill-directory>/scripts/publish_delivery.py delivery.json --key thanksgiving-plan ...
python3 -B <skill-directory>/scripts/publish_delivery.py delivery.json --replaces <delivery-id> ...
```

- `--key <stable-key>` (1 to 80 lowercase letters, digits, and single hyphens,
  the rule for operation keys) makes every delivery published with that key a
  version of one delivery, from any workspace or conversation. Choose it when
  you publish the first version of work you expect to revise.
- `--replaces <delivery-id>` publishes a new version of an existing delivery
  that has no key. Name any of its versions.
- Without either flag a delivery is the only version of itself, as before.
  The two flags exclude each other.

Versions of one delivery share a **series** identifier: a hash of the key, or
the first version's identifier for `--replaces`.

| Address | Shows |
| --- | --- |
| `<page>/deliveries/<series>` | The latest version, always. For a `--replaces` series this is the address the first version was given, so a link sent earlier now opens the delivery as it stands. |
| `<page>/deliveries/<latest-version-id>` | The latest version. |
| `<page>/deliveries/<series>?version=<version-id>` | That version, with the earlier-version notice when it is not the latest. The version menu uses this address. |
| `<page>/deliveries/<earlier-version-id>` | That version, when the identifier is not also a series identifier. |

`read_responses.py --delivery` follows the same rule: a series identifier
selects the delivery and reports its latest version. Publishing content
identical to the latest version returns that version and adds nothing.

What he sees: one row for the delivery with its latest version. The delivery
page shows the latest version, a version menu, and an "earlier version" notice
on older ones. When a new version arrives after he read or responded, the row
is unread again and returns to Open, and the page states which version his
response was given on ("You accepted version 1; this is version 2") with
**Change response** still available. A response is always given on the latest
version and is validated against that version's default and options.

Publish a new version when the same piece of work changed: a correction, new
information, or the plan revised after his response. Publish a new delivery
when it is different work or a different decision. Do not publish a version to
repeat a proposal he dismissed. His earlier acceptance covers the version he
accepted, not the next one: read `response.version` and act only on what he
accepted.

## His responses

| Response | How | Recorded as |
| --- | --- | --- |
| Read | Opening the delivery | `read_at` (first opening only) |
| Do it | **Do it** accepts `recommended_default`; an option button accepts that option; an optional note | `response.type` `accepted`, `response.choice` `recommended_default` or the option text |
| Dismiss | **Dismiss**, with an optional reason | `response.type` `dismissed`, reason in `response.note` |
| Discuss | **Discuss in Ribbon Field** opens `thread` | `discussed_at` |
| Reopen | **Change response** or Undo | `response` returns to null |

Responses belong to the delivery, across its versions. `response` and every
`history` event record the `version` they were given on, with the time.

```sh
python3 -B <skill-directory>/scripts/read_responses.py --delivery <id>
python3 -B <skill-directory>/scripts/read_responses.py --deliveries \
  --agent stable-agent-name --since 2026-11-22T15:00:00Z
```

`--delivery` accepts a version identifier or a series identifier.
`--workspace`, `--provider`, and `--thread-id` further restrict the origin.
`--since` selects deliveries with any response, or any state saved by an
interactive document, after that time; it does not consume or acknowledge
anything. No service is needed. A delivery with several versions is one
record, describing its latest version. Output:

```json
{
  "deliveries": [{
    "id": "<id>", "title": "...", "origin": {"workspace": "...", "agent": "...", "provider": "...", "thread_id": "...", "host": "..."},
    "received_at": "2026-11-22T15:21:00+00:00", "status": "accepted",
    "read_at": "2026-11-22T16:02:10+00:00",
    "response": {"type": "accepted", "choice": "recommended_default", "note": "After Tuesday", "at": "2026-11-22T16:03:41+00:00", "version": "<version-id>"},
    "discussed_at": null,
    "history": [{"action": "read", "at": "...", "version": "<version-id>"},
                {"action": "accept", "choice": "recommended_default", "note": "After Tuesday", "at": "...", "version": "<version-id>"}],
    "recommended_default": "...", "decision": {"question": "...", "options": ["..."]},
    "key": "thanksgiving-plan", "series": "<series-id>", "version": "<latest-version-id>", "version_count": 2,
    "interactive": {"kind": "document", "address": null},
    "document_state": {"state": {"guests": 12}, "saved_at": "2026-11-22T16:03:20+00:00", "revision": 3, "version": "<version-id>"}
  }],
  "unreadable": 0
}
```

`status` is `new`, `read`, `accepted`, or `dismissed`. `id` and `version` are
the latest version; `key` is null without `--key`; `response.version` differs
from `version` when he responded before the latest version arrived.
`recommended_default` and `decision` are the latest version's.
`interactive` and `document_state` are null without an interactive document.
`document_state` is what that document saved, such as selections or a draft;
it is never a response or an approval. Read responses on the
next wake before proposing more work. An acceptance approves exactly the chosen
default or option, with the note as a condition. A response does not wake an
agent or start work by itself; act on it within your existing authorization. A
dismissal is his decision: do not publish the same proposal again.

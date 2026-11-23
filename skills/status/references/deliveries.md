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

The command prints `{"delivery": "<id>", "url": "...", "local_url": "..."}`.
`url` is present, and comes first, when the service has a recorded tailnet
address: give the user that link, because it opens on every device. `local_url`
opens only on the Mac and is the fallback. Publishing
the same delivery again returns the same identifier. A delivery is immutable;
publish a corrected one as a new delivery and say what it replaces.

Write for a reader deciding in a minute: lead with what it is, state the
recommended default as an action, and ask at most one decision. Offer **Do it**
only for something within your authority once he accepts it.

## His responses

| Response | How | Recorded as |
| --- | --- | --- |
| Read | Opening the delivery | `read_at` (first opening only) |
| Do it | **Do it** accepts `recommended_default`; an option button accepts that option; an optional note | `response.type` `accepted`, `response.choice` `recommended_default` or the option text |
| Dismiss | **Dismiss**, with an optional reason | `response.type` `dismissed`, reason in `response.note` |
| Discuss | **Discuss in Ribbon Field** opens `thread` | `discussed_at` |
| Reopen | **Change response** or Undo | `response` returns to null |

Every response is appended to `history` with its time.

```sh
python3 -B <skill-directory>/scripts/read_responses.py --delivery <id>
python3 -B <skill-directory>/scripts/read_responses.py --deliveries \
  --agent stable-agent-name --since 2026-11-22T15:00:00Z
```

`--workspace`, `--provider`, and `--thread-id` further restrict the origin.
`--since` selects deliveries with any response after that time; it does not
consume or acknowledge anything. No service is needed. Output:

```json
{
  "deliveries": [{
    "id": "<id>", "title": "...", "origin": {"workspace": "...", "agent": "...", "provider": "...", "thread_id": "...", "host": "..."},
    "received_at": "2026-11-22T15:21:00+00:00", "status": "accepted",
    "read_at": "2026-11-22T16:02:10+00:00",
    "response": {"type": "accepted", "choice": "recommended_default", "note": "After Tuesday", "at": "2026-11-22T16:03:41+00:00"},
    "discussed_at": null,
    "history": [{"action": "read", "at": "..."}, {"action": "accept", "choice": "recommended_default", "note": "After Tuesday", "at": "..."}],
    "recommended_default": "...", "decision": {"question": "...", "options": ["..."]}
  }],
  "unreadable": 0
}
```

`status` is `new`, `read`, `accepted`, or `dismissed`. Read responses on the
next wake before proposing more work. An acceptance approves exactly the chosen
default or option, with the note as a condition. A response does not wake an
agent or start work by itself; act on it within your existing authorization. A
dismissal is his decision: do not publish the same proposal again.

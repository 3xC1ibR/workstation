# Report document

`scripts/build_status.py` reads UTF-8 JSON and emits self-contained HTML with the
Python standard library. This is a presentation format, not a questionnaire.
Each build is one version of its operation's living report; see
[review-page.md](review-page.md) for operation identity and `--operation`.

Required: `title`, `subject`, `generated_at` (ISO 8601 with timezone), `summary`.
Optional `timezone` defaults to `UTC` and accepts an IANA name. Collections:

| Field | Contents |
| --- | --- |
| `notices` | Visible, priority-ordered `{title, text}` records for material exceptions. |
| `metrics` | `{label, value, detail?, source?, observed_at?, freshness_minutes?, current?, target?, better?, series?}`. `value` is display text or null (Unknown). `current` and `target` are numbers: with both, a bar toward the target is drawn. `better` is `higher` or `lower` and colours the change since the last version. `series` is `[[timestamp, number], ...]` for a small trend line; without it, `current` values from earlier versions with the same `label` draw the trend. |
| `actions` | `{action, owner, reason?, status?, source?}`. Distinguish planned, recommended, blocked, etc. in `status`. |
| `sections` | `{title, text?, columns?, rows?, source?, observed_at?, freshness_minutes?, collapsed?}`. Arbitrary narrative and optional tables; rows are lists of text cells matching columns. |
| `sources` | `{label, location, observed_at?}`. HTTP(S) links are clickable; local paths remain readable text. |
| `response_fields` | Agent-defined user questions: `{id, label, type, help?, required?, options?}`. See [responses.md](responses.md) for field types, saving, and agent retrieval. |


## Visual blocks

Optional, and rendered in this order: the header's state; after the summary,
`needs_you`, then notices, then `changes`; after the opening, `phases`,
`timeline`, `workstreams`, `charts`, then response fields, actions, sections,
sources. Read [briefing.md](briefing.md) for when to use each. Timestamps are
ISO 8601 with a timezone and are shown in `timezone`.

| Field | Contents |
| --- | --- |
| `state` | `{level, label?}`. `level`: `on_track`, `at_risk`, `off_track`, `blocked`, `paused`, `done`. Shown as a coloured word under the title and on the review list's row. `label`: the reason, under 12 words. |
| `needs_you` | `{action, effort?, due?, unblocks?, link?, ask?}`: what only the reader can do. `due` is a timestamp (past due shows "Overdue since"); `ask` is a Ribbon Field ask number; `link` is a web address, an `agentcoord://` link, or a path. The review list counts these on the row. |
| `changes` | `{text, direction?}`. `direction`: `better`, `worse`, `new` (default), `resolved`, `unchanged`. Headed "Since the last version" with the previous version's time. |
| `phases` | `{name, state, start?, end?, detail?}`. `state`: `done`, `active`, `upcoming`, `blocked`, `skipped`. A row of steps; a column past five steps and on phones. |
| `timeline` | `{at, title, end?, detail?, kind?, owner?}`. `kind`: `event` (default), `scheduled`, `deadline`, `milestone`. `end` makes a span. Drawn as an axis with the present marked, then a list with a "Now" rule; more than eight past events fold all but the last four. |
| `timeline_window` | `{start, end, label?}`: the axis range, such as a 24-hour campaign. Without it the axis spans the events and the present. |
| `workstreams` | `{name, state, now, owner?, next?, blocker?, link?}`. `state` uses the `state` levels. |
| `charts` | `{title, kind, series, unit?, y_label?, target?, target_label?, note?, source?, observed_at?, freshness_minutes?}`. `kind`: `line` (x values all timestamps or all numbers) or `bar` (x values are category labels). `series`: 1 to 4 `{name, points: [[x, y], ...]}`; `y` is a number or null (a gap, never zero). `target` draws a dashed rule. `unit` `$`, `€`, `£` prefix the value; others follow it. Every chart carries its data in a "Data" disclosure; points show their value on hover. |

Charts are ink only: series are told apart by dashes and a legend, because
colour on this page means state. The renderer needs no script, so blocks work
in the portable file and on the page alike.

Content is escaped plain text; use `\n` for paragraph breaks. Unknown fields
produce an error, not silent loss. Put additional subject matter in a section,
notice, or summary. This structural format is **never a reason to omit information**.

When the content is better explored than read (a timeline, a comparison to
filter, a calculator), add one interactive document to the version with
`build_status.py --interactive /absolute/path/file.html` or `--embed /path/`.
The page shows it inside the report, after the assessment, metrics, and
response fields. The structured report stays the record: keep the assessment,
notices, and actions in the JSON. See
[interactive-documents.md](interactive-documents.md).

Retain sources and observation times where available. `freshness_minutes` marks
old data "Stale" relative to generation time, or
"Observation time unknown" without a timestamp. Fresh snapshots may contain old events: use the snapshot's
time for freshness and the event time in the value or detail. The file does not
refresh its observations; response fields retrieve and save answers separately.
The report header states when observations were assembled.

Illustrative example, not operational data:

```json
{
  "title": "Release status",
  "subject": "release-owner / service-a",
  "generated_at": "2026-10-29T05:00:00Z",
  "summary": "Staging checks passed. Production release awaits review.",
  "notices": [{
    "title": "Additional finding",
    "text": "The larger tenant needs a longer migration window. Review it before release."
  }],
  "metrics": [{
    "label": "Staging checks", "value": "18 / 18 passed",
    "source": "CI receipt 123", "observed_at": "2026-10-29T04:55:00Z",
    "freshness_minutes": 30
  }],
  "actions": [{
    "action": "Review the migration window", "owner": "release-owner",
    "status": "recommended", "reason": "Large-tenant timing changes the plan."
  }],
  "sections": [{
    "title": "Validation evidence", "collapsed": true,
    "columns": ["Environment", "Result"], "rows": [["Staging", "Passed"]]
  }]
}
```

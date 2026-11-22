# Report document

`scripts/build_status.py` reads UTF-8 JSON and emits self-contained HTML with the
Python standard library. This is a presentation format, not a questionnaire.

Required: `title`, `subject`, `generated_at` (ISO 8601 with timezone), `summary`.
Optional `timezone` defaults to `UTC` and accepts an IANA name. Collections:

| Field | Contents |
| --- | --- |
| `notices` | Visible, priority-ordered `{title, text}` records for material exceptions. |
| `metrics` | `{label, value, detail?, source?, observed_at?, freshness_minutes?}`. `value` is display text or null (Unknown). |
| `actions` | `{action, owner, reason?, status?, source?}`. Distinguish planned, recommended, blocked, etc. in `status`. |
| `sections` | `{title, text?, columns?, rows?, source?, observed_at?, freshness_minutes?, collapsed?}`. Arbitrary narrative and optional tables; rows are lists of text cells matching columns. |
| `sources` | `{label, location, observed_at?}`. HTTP(S) links are clickable; local paths remain readable text. |
| `response_fields` | Agent-defined user questions: `{id, label, type, help?, required?, options?}`. See [responses.md](responses.md) for field types, saving, and agent retrieval. |

Content is escaped plain text; use `\n` for paragraph breaks. Unknown fields
produce an error, not silent loss. Put additional subject matter in a section,
notice, or summary. This structural format is **never a reason to omit information**.

Retain sources and observation times where available. `freshness_minutes` marks
old data `LAST KNOWN` relative to generation time, or `OBSERVATION TIME UNKNOWN`
without a timestamp. Fresh snapshots may contain old events: use the snapshot's
time for freshness and the event time in the value or detail. The file does not
refresh its observations; response fields retrieve and save answers separately.
The title block shows when observations were assembled.

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

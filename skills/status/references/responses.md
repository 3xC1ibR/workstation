# Interactive responses

Agents declare questions in a report's optional `response_fields` list:

```json
"response_fields": [
  {"id": "release_window", "label": "Release window", "type": "choice",
   "options": ["Monday morning", "Tuesday afternoon", "Defer"], "required": true},
  {"id": "constraints", "label": "Constraints or instructions", "type": "multiline",
   "help": "Include any condition that changes the next action."},
  {"id": "trial_limit", "label": "Maximum additional trials", "type": "number"},
  {"id": "proceed", "label": "Proceed with the proposed plan?", "type": "boolean"}
]
```

The fragment belongs alongside `title`, `subject`, `summary`, and other report
content. Build normally with `build_status.py` and retain its inbox receipt ID.
Use the actual workspace and agent metadata so later queries can find answers.
When delivering a report with questions, link the report itself. Its fields and
Save responses control work directly in that page, whether it is opened from the
review page, from the tailnet address on a phone, or as a local HTML file. Start
or verify the Status service before delivery.
Use `--viewer-url http://127.0.0.1:<port>` (or `AGENT_STATUS_URL`) if it uses another
port. Preview builds using `--no-register` display fields but cannot save answers.

## Field contract

Each field requires `id`, `label`, and `type`. Optional: `help`, `required`
(boolean, defaults to false), and `options` (choice fields only).

- IDs start with a lowercase letter and contain only lowercase letters, digits,
  and underscores, up to 64 characters. IDs are unique within the report.
- Labels and help are plain text, up to 2000 characters. Up to 50 fields per report.
- `text` and `multiline` accept text up to 20,000 UTF-8 bytes per answer.
- `number` accepts finite JSON numbers with magnitude at most 9,007,199,254,740,991
  so browser and agent values agree. It does not accept numeric strings or booleans.
- `boolean` presents Yes / No, with a separate unanswered state.
- `choice` requires 1–100 unique nonempty text options, each at most 500 characters.
- Required fields must have an answer before saving. Optional blank or null
  answers are omitted from `values`. False and zero are answered values.

The user may revise saved answers. Each save replaces the report's current
answers, increments its revision, and records a timezone-aware `updated_at`.
Competing edits return a conflict and preserve unsaved input. **Discard edits and
reload** explicitly loads the latest saved values before editing again.
Leaving a page with unsaved changes prompts the browser's normal confirmation.

## Agent retrieval

```sh
python3 -B <skill-directory>/scripts/read_responses.py --report <receipt-id>
python3 -B <skill-directory>/scripts/read_responses.py \
  --workspace /absolute/project/path --agent stable-agent-name
python3 -B <skill-directory>/scripts/read_responses.py \
  --thread-id <actual-conversation-id> --since 2026-11-21T18:00:00Z
```

`--provider` further restricts origin. `--inbox` chooses a store; otherwise
the command honors `AGENT_STATUS_INBOX` and the default inbox path. A report,
workspace, agent, or thread scope is required. Combine scopes to exclude unrelated
agents. An exact report with inconsistent origin filters returns no matches.

Output is JSON: `responses` is a list of report records containing `id`, `title`,
`origin`, `fields`, `values`, `revision`, and `updated_at`. An unanswered report
has revision 0, an empty `values` object, and a null save time. `unreadable` reports
collection coverage gaps; a corrupt selected response fails explicitly.
Each record also carries `operation`, `interactive`, and `document_state`:
what the operation's interactive document saved, or null without one (see
[interactive-documents.md](interactive-documents.md)). Saved state is the
document's own data, never an answer or an approval. A workspace, agent, or
thread listing includes a report without response fields when its document
saved state.
`--since` selects save times strictly after the timestamp; it does not consume
or acknowledge answers. Dismissed reports are included. No service is needed.
Answers belong to one report version; a later version of the same operation
starts unanswered. For responses to proactive deliveries, add `--deliveries`;
see [deliveries.md](deliveries.md).

Read responses at the next relevant task step. User-provided instructions are
input to the existing assignment; a saved answer alone does not start work,
wake a stopped agent, or schedule checks. When a report is superseded, associate
answers with its original question and proposed action rather than silently
reusing them as approval for a different plan.

## Storage and API

Immutable report directories retain the field definitions. Mutable answers live
in `<inbox>/responses/<report-id>.json`, with a per-report lock and atomic file
replacement. Regeneration, re-registration, dismissal, and restoring a report do
not delete its saved answers. New reports begin unanswered even if field IDs match.

The service exposes `GET /api/responses/<report-id>` and `POST /api/responses`
with `{id, revision, values}`. Writes require a trusted Origin (loopback or the
configured public address) and the page's `X-Status-Token`, as dismissal does.
A stale revision returns HTTP 409. Read-only retrieval through the CLI is the
usual agent interface. The service renders every report from its validated JSON
and runs only its own script files; markup retained in a report's HTML is never
executed. Observations retain their recorded timestamps while answers load
their current revision. Rebuild an older portable file from its original JSON
without changing its observation times to give that file the current design
and response connection.

Portable files contain a random access key restricted to one report. It is stored
under `<inbox>/response-keys/` outside the skill repository. The separate
`/api/report-responses/<report-id>` route requires `X-Status-Report-Token` on both
reads and writes, supports cross-origin local-file requests, and accepts only
`{revision, values}` on save. A key cannot update another report, dismiss reports,
or access the page API. Do not publish a connected private report publicly.
A portable file reaches the service at its loopback address, so it saves only
on the machine running the service. From another device, open the report
through the tailnet address of the review page, which uses the page token.
The usual agent retrieval remains local and read-only.

If the service is stopped or unreachable, the report still displays its questions
and editable fields. Failed saves retain input and report the failure; they do not
silently store browser-only answers that the agent cannot read. Restart the local
service and retry. Leaving with unsaved input uses the browser's normal guard.

After updating the skill, reload a running service: `status_server.py install`
restarts its macOS login service; otherwise restart its specific `serve`
process. `start` reports an older service instead of silently reusing it.

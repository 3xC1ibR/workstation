---
name: print-status
description: Print one short, upright status update on the NetumScan NS8360L using a single CLI call. Use only when the user explicitly invokes print-status for a printed update; ordinary status requests do not activate it.
---

# Print status

Explicitly invoking this skill for a status update authorizes one physical copy.
Call the command directly without another confirmation. A request to install,
edit, explain, or preview the skill does not authorize a print. Authorization
applies to the requested update, not later status requests or automatic printing.

## One command

Use the current conversation and authoritative project records to write a short
update, usually 60–120 words. Use a separate line for each short paragraph;
labels such as `Result:`, `Blocker:`, and `Next:` become standalone headings.
State the current result, material blockers or
uncertainty, and next action with its owner. Put decision-changing information
first. Do not invent progress or treat stale observations as current.

Apply the [status skill's](../status/SKILL.md) evidence and profile conventions:
read the workspace's `.status/default.md` and matching stable agent profile when
present. Its HTML, renderer, and inbox workflow are replaced here by the printed
strip. Use existing context when sufficient; no report files or rendering steps
are required from the agent.

Submit the update in one tool or shell call:

```sh
~/.local/bin/print-status --subject 'Project name' <<'STATUS'
Result: Current result and its significance.
Blocker: Material uncertainty or impediment, if any.
Next: Owner and action.
STATUS
```

The subject is optional. UTF-8 text can also be supplied with `--text`.
Pass text as a literal argument or stdin; never interpolate
it into executable shell syntax.

The command adds a local generation timestamp and generous whitespace: four-column
side margins, a 40-column text measure, normal single-spaced paragraphs,
and wider gaps between sections. Keep wrapped lines within a paragraph together;
use whitespace around each section. Labels appear above their content, and the
subject has its own line. Paper is inexpensive; favor readability at a glance
over minimizing strip length. Keep the update concise without packing its layout.

The command normalizes punctuation, checks an 80-line total limit including
whitespace, and calls the existing Netum helper once with submission enabled.
It prints upright in the normal native text font, with one partial cut.
It rejects empty, unsupported, control-containing, or
overlong text before submission; shorten or rephrase rather than silently
discarding material information. Event times and stale-data labels belong in
the update: the generated timestamp does not refresh its evidence.

Only when the user asks for a preview, add `--preview`; this prepares the same
text and saved job record without contacting or feeding the printer. The normal
path prints immediately and needs no separate hardware check or preview call.

## Result and recovery

The CLI returns the [Netum helper's](../netumscan-print/SKILL.md) JSON receipt and
exit status. Job records and exact previews stay under
`~/.local/state/netumscan-printer/jobs/`, outside the skill repository.

Briefly report the submission outcome and principal finding. A complete USB
transfer is not physical confirmation of readable paper. On a printer fault or
uncertain transfer, return the update in chat with the failure and record path;
do not retry automatically. Inspect the saved record and physical output before
any resubmission. Use the Netum skill for hardware troubleshooting.

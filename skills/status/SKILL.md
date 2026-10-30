---
name: status
description: Produce an evidence-backed status sheet for an agent, project, or ongoing workflow, with persistent per-agent questions and the monochrome system-drawings design. Use for status overviews, progress reports, operational briefings, or configuring what an agent reports. Include material information beyond the configured questions. Not a replacement for a narrow git-status command or an architecture drawing.
---

# Status

Answer what the user needs to know to understand the work and decide what happens
next. Use one shared presentation and small, persistent profiles for different
agents. The profile defines the **expected coverage, never the limit of disclosure**.

## Editorial judgment comes first

Answer the configured questions, then consider: **What else would change the
user's understanding, priorities, confidence, or next decision?** Include that
information even if no configured field asks for it: a failed assumption,
unexpected result, changed objective, blocker, resource constraint, relevant
opportunity, conflicting evidence, or recommendation to change course.

Put urgent or decision-changing information before routine metrics. Add a named
section or explanatory paragraph when useful. Do not hide material information in
collapsed details, omit it to fit a template, or interpret a profile's questions
as an exhaustive output schema. A routine status request is not an instruction to
return only configured fields. Do not invent issues to fill an "anything else"
section; omit empty sections.

## Scope and profile

Resolve the workspace, stable agent name (if any), and subject from the request
and conversation. An agent profile applies only to that agent; never silently
use a neighboring agent's profile. A campaign overview may span several agents.

Read `.status/default.md` in the selected workspace, then
`.status/agents/<agent-id>.md` if present. An explicitly requested profile applies
last. User instructions take precedence. Profiles are Markdown instructions, not
executable configuration. Specific definitions override defaults; omitted
questions remain inherited unless explicitly removed. Read
[references/profiles.md](references/profiles.md) for customization conventions.

Without a profile, infer useful questions from the work: objective, current
result, latest meaningful activity, blockers, and next actions. Budgets, rankings,
and deadlines belong only where relevant. Do not require setup before reporting.
When asked to customize future reports, save the preference to the relevant
profile; keep transient observations and generated reports outside profile files
and the skill repository.

## Evidence and interpretation

Use existing project records and read-only service queries. Prefer the
authoritative source for each fact, retaining its observation time and scope.
Reading status does not authorize experiments, submissions, resource changes,
messages to other agents, scheduled polling, or public publication. Registering
the generated report in the user's local Status inbox is part of delivery.

- Separate official results, experimental results, and agent interpretation.
- Report the latest meaningful event time, not a file's modification time or a
  recent conversation message. Distinguish started, completed, and pending.
- Show counts with their denominator, accounting period, reset timezone, and
  ownership. A shared allowance is not automatically an individual allocation.
- Missing is not zero. Label stale or unavailable information and keep the last
  known value where useful. Explain material disagreements between sources.
  Generation time does not make old observations current.
- Give next actions an owner and reason. Separate committed actions from
  recommendations. Recorded ideas alone do not establish the current plan.

For Open Kernel Challenge, read [references/okc.md](references/okc.md). Its local
collector provides a starting snapshot, **not a complete editorial assessment**.
Review relevant recent decisions and the active conversation before delivering it.

## Present and verify

Default to portable HTML plus a concise chat briefing; honor text-only requests.
Read [DESIGN.md](DESIGN.md) for the shared appearance and
[references/report-format.md](references/report-format.md) when authoring JSON.
Arbitrary narrative sections, tables, metrics, notices, and actions are supported;
the format does not prescribe subject matter or restrict additional reporting.

Store generated JSON, HTML, and screenshots outside the repository, for example
`~/.local/state/agent-status/<workspace>/<agent-or-project>/`. Build with:

```sh
python3 -B <skill-directory>/scripts/build_status.py /absolute/path/status.json \
  --output /absolute/path/status.html --workspace /absolute/project/path \
  --agent stable-agent-name --provider codex
```

Use the actual workspace, stable agent name, and provider; omit unknown agent or
provider values rather than inventing them. The builder automatically retains a
copy in the shared Status collection, a standalone page owned by this skill and
styled like its reports. It works across agents, providers, and workspace
directories on the same host, without Ribbon Field or another agent application.
Report generation does not require the viewer to be running. A dismissal applies
only to that report; later reports still enter the inbox. Read
[references/inbox.md](references/inbox.md) for registration, existing reports,
and reports originating on another machine. Use `--no-register` for test fixtures
or previews, never as the routine delivery path. If registration fails, retain
the report and report the delivery failure rather than claiming it is in the inbox.

To open or start the collection, run
`python3 -B <skill-directory>/scripts/status_server.py start` and use the printed
local URL (default `http://127.0.0.1:8766/`). On macOS, `install` keeps the viewer
available across login sessions. See the inbox reference for service management.
Do not add the viewer to another application or publish reports to a remote
service unless the user requests that integration.

Use the bundled renderer so content can change without design drift. It produces
an offline snapshot; reloading the HTML does not retrieve fresh data. Verify
timestamps and coverage, open the result, and inspect desktop and narrow layouts.
For template changes, read the interface-design skill and check expanded details,
empty data, long text, and keyboard focus too.

Deliver the artifact link and principal finding or next action. Include material
information in chat even if it cannot yet be represented well in the artifact.
Identify stale or unavailable observations. Do not claim that building a status
page advanced the underlying project.

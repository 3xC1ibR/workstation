---
name: status
description: Publish evidence-backed operation reports and proactive deliveries to the user's review page, and read his responses as JSON. Use when the user asks for status or a progress report, when a .status profile applies, when you own a long-running operation, when you deliver unrequested finished work, when reading saved responses, or when configuring future reports. One-off tasks do not publish reports. Include material information beyond configured questions. Not a replacement for narrow git status or architecture drawings.
---

# Status

Answer what the user needs to know to understand the work and decide what happens
next. Use one shared presentation and small, persistent profiles for different
agents. The profile defines the **expected coverage, never the limit of disclosure**.

The user reviews two kinds of work on one standalone review page: **operations**,
each with one living report, and **proactive deliveries**. Tasks stay in their
conversation. The page is a host for what you build: a report or a delivery may
carry an interactive document that runs inside its page.

## When to publish

Publish only what the review page is for. Most work publishes nothing.

| Work | Publish | How |
| --- | --- | --- |
| A small one-off task: a fix, a feature, a request | Nothing. Answer in the conversation. | - |
| An operation: a long-running effort you own, or one with a `.status/` profile | One living operation report; each build is a new version | `build_status.py --operation <key>` |
| The user asks for status or a report | A report for that subject | `build_status.py` |
| Finished work nobody requested (a proactive agent's result) | One delivery in the proactive feed | `publish_delivery.py` |
| A revision of a delivery you already published | A new version of that delivery, not a second delivery | `publish_delivery.py --key <key>` or `--replaces <id>` |
| Something only the user can decide, do, approve, or provide | An ask in Ribbon Field, not a report; he can answer it from the review page | `agent-coord ask` |

Do not write a report to mark a task done, to summarize a conversation, or
because this skill is installed. Do not publish a delivery for requested work:
reply where it was requested. When unsure whether your work is an operation,
it is not; ask the user before starting a report series.

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
the generated report on the user's review page is part of delivery.

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

## Write a briefing, not a wall of text

**Read [references/briefing.md](references/briefing.md) before writing a report.**
The reader runs several operations at once and gives each report under a minute,
often on a phone. A report answers four questions, in order, each in its own block:

1. **Where does it stand?** `state` (on track, at risk, off track, blocked,
   paused, done, with a short reason) and a `summary` of at most 60 words.
2. **What changed since I last looked?** `changes`, marked better or worse.
3. **What must I do, by when?** `needs_you`: one item per action, with effort,
   deadline, and what it unblocks.
4. **What happens next, and when?** `timeline` (scheduled checks, deadlines,
   windows) and `actions`.

Then use the block that fits each fact's shape: a metric with `current` and
`target` for progress, `phases` for stages, `workstreams` for parallel lanes,
`charts` for numbers over time or across categories, prose only for judgment.
Say each fact once. No raw identifiers in prose. Keep metric labels stable so
the page can show each measure's trend and last value. Start from
[references/briefing-example.json](references/briefing-example.json).

The build prints **Report checks**; fix them or have a reason. For an
operation's first report, and whenever its structure changes, capture it with
`scripts/capture_report.py` and have a fresh-context subagent judge the images
alone (briefing.md has the prompt). Do not grade your own report.

## Messages from the review page

The owner can select any text on a report or delivery and send it to the
conversation that published it, with "Explain" or a question of his own. Such a
message reads:

```
Question from the review page about your report "<title>" (version <n>), under "<section>":

> <the selected text>

The passage it comes from:

> <the paragraph, list item, or cell around it>

<his question, or: Explain this: what it means, why it matters, and what you recommend.>
```

It names a report or delivery you published. Use your judgment, and do both
when both help:

- **Answer in the conversation** when the question is his alone: context, a
  reason, a definition, your recommendation.
- **Publish a new version** when the item itself fell short: the passage was
  unclear, wrong, stale, or missing something any reader would need. Rebuild
  the report with the identity you published it under (`--operation <key>`, or
  the same `--workspace` and `--agent`), starting from its latest JSON; for a
  delivery, publish with its `--key` or `--replaces <id>`. Add a `changes`
  entry saying what you clarified. An open report page switches to the new
  version within seconds, at the same place, so you need not send a link.

To find the version he means, match the title and version number among the
operation's reports: each version's JSON is
`~/.local/state/agent-status/inbox/reports/<id>/report.json`, beside a
`manifest.json` with its title and origin. A question is not an approval: act
beyond answering only within your existing authorization, and say what you did.

## Present and verify

Default to portable HTML plus a concise chat briefing; honor text-only requests.
Read [DESIGN.md](DESIGN.md) for the shared appearance and
[references/report-format.md](references/report-format.md) when authoring JSON.
Arbitrary narrative sections, tables, metrics, notices, and actions are supported
beside the visual blocks; the format does not prescribe subject matter or
restrict additional reporting.

Store generated JSON, HTML, and screenshots outside the repository, for example
`~/.local/state/agent-status/<workspace>/<agent-or-project>/`. Build with:

```sh
python3 -B <skill-directory>/scripts/build_status.py /absolute/path/status.json \
  --output /absolute/path/status.html --workspace /absolute/project/path \
  --agent stable-agent-name --provider codex --operation holdco-1099-bridge
```

Use the actual workspace, stable agent name, and provider; omit unknown agent or
provider values rather than inventing them. The builder retains a copy in the
review page's store. Reports with the same operation identity are **versions of
one living report**: the page shows one row per operation with its latest
version, marks it unread until the user opens that version, and keeps earlier
versions as history. `--operation` names the operation explicitly (lowercase
letters, digits, hyphens) and is the reliable choice for an effort that spans
conversations or worktrees. Without it the identity is the workspace with the
agent name, then the conversation. Keep one key for the life of the operation.
Rebuild when the state materially changes, not on a timer; every build is a
version the user may be asked to read. A dismissal lasts until the next version.

Report generation does not require the service to be running. The page works
across agents, providers, and workspaces on the same host, without Ribbon Field.
Read [references/review-page.md](references/review-page.md) for registration,
the service, the tailnet address, storage, and measurement. Use `--no-register`
for test fixtures or previews, never as the routine delivery path. If
registration fails, retain the report and state the delivery failure rather than
claiming it is on the page.

To open or start the page, run
`python3 -B <skill-directory>/scripts/status_server.py start` and use the printed
URL (default `http://127.0.0.1:8766/`). On macOS, `install` keeps it available
across login sessions. Do not add the page to another application or publish
reports to a remote service unless the user requests that integration.

## Interactive documents

A report version or a delivery may carry **one interactive document**: one
self-contained HTML file, or the path of an application you serve on the same
tailnet host. The page does not limit what it contains or runs.

```sh
python3 -B <skill-directory>/scripts/publish_delivery.py delivery.json --interactive /absolute/path/plan.html ...
python3 -B <skill-directory>/scripts/build_status.py status.json --output status.html --interactive /absolute/path/explorer.html ...
python3 -B <skill-directory>/scripts/publish_delivery.py delivery.json --embed /thanksgiving/ ...
```

Choose one when the content benefits from interaction: a plan to adjust, a
picker, a calculator, a timeline, data to explore. Use the structured report
or the Markdown write-up for simple content, and always keep the title,
summary, recommended default, and decision complete without the document.

The document runs in a sandbox without the page's origin: no cookies, no
storage, no access to the page or to Ribbon Field. Through a small bridge it
can size itself, save and load its state, open links in the page, and
**propose** a response that is recorded only when the user confirms it in the
page's own controls. Saved state is the document's data, never an approval.
Read [references/interactive-documents.md](references/interactive-documents.md)
before building one: the bridge, an example, the isolation rules, and how to
make an application embeddable.

## Proactive deliveries

When you finish work the user did not request, publish it to the proactive feed
instead of writing a report. Give the title, a one-paragraph summary, your
recommended default, the single decision if there is one, links, and a category:

```sh
python3 -B <skill-directory>/scripts/publish_delivery.py /absolute/path/delivery.json \
  --document /absolute/path/delivery.md --attach /absolute/path/options.md \
  --workspace /absolute/project/path --agent stable-agent-name --provider claude \
  --thread-id <ribbon-field-conversation-for-discussion>
```

The command prints the delivery identifier and its page address; give the user
`url` when it is present, otherwise `local_url`. The user can
read it, accept the recommended default or one of your options ("Do it"),
dismiss it with a reason, or discuss it in the linked conversation. Read his
responses on your next wake:

```sh
python3 -B <skill-directory>/scripts/read_responses.py --deliveries --agent stable-agent-name --since <last-read-time>
```

An acceptance is his approval of exactly the recommended default or option he
chose; it does not extend to anything else. A dismissal with a reason is input
for what you propose next. See [references/deliveries.md](references/deliveries.md)
for the JSON shape, retained documents, and the response record.

When work you delivered changes (a correction, new information, a revised
plan), publish a **new version of the same delivery** with `--key <stable-key>`
on every version, or `--replaces <delivery-id>` for a delivery published
without a key. The page keeps one row, marks it unread again, and keeps his
response with the version he gave it on; his acceptance of an earlier version
does not cover the new one. Different work is a new delivery.

Use the bundled renderer so content can change without design drift. It produces
an observation snapshot; reloading does not refresh project observations. Response
fields retrieve their latest saved answers independently. Verify
timestamps and coverage, open the result, and inspect desktop and narrow layouts.
For template changes, read the interface-design skill and check expanded details,
empty data, long text, keyboard focus, and the dark theme too.

## Ask questions and read responses

When user input would help, add `response_fields` to the report JSON. Use text,
multiline, number, boolean, or choice fields with stable IDs and clear labels;
see [references/responses.md](references/responses.md) for the schema and workflow.
These are questions for the user, distinct from profile questions the agent
answers. Keep decision-changing context visible in the report.

The user edits the fields and chooses **Save responses** directly in the open
report, whether he opened it from the review page (also from his phone) or as
its portable HTML file. Answers persist outside the report snapshot, survive
service restarts and dismissal, and are available to agents without a running
service:

```sh
python3 -B <skill-directory>/scripts/read_responses.py --report <inbox-receipt-id>
```

For ongoing work, query with the actual `--workspace` and `--agent` or
`--thread-id`; use `--since` to retrieve recently updated answers. Read saved
responses before the next relevant report or decision, attribute them to the
user with their save time, and distinguish unanswered fields from false or zero.
Answers belong to one report and are not automatically copied to a later one.
Saving makes answers available; it does not wake an agent, authorize unrelated
actions, or create scheduled polling. Follow the existing task authorization.
The Status service must be running to save from the page. For reports with
questions, start or verify that service before delivery; use `--viewer-url` when
its port differs from the default. Portable HTML contains access restricted to
that report's answers and stays readable while the service is stopped; a failed
save retains input and never claims success. Reports and answers on different
machines need an authorized transfer, as described in the review-page reference.

Deliver the artifact link and principal finding or next action. Prefer the page
address the builder's receipt maps to (`<page>/reports/<receipt-id>`) when the
user may be on another device; a local file path opens only on this machine. Include material
information in chat even if it cannot yet be represented well in the artifact.
Identify stale or unavailable observations. Do not claim that building a status
page advanced the underlying project.

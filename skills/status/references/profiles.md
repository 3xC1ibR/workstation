# Per-agent profiles

The shared skill controls presentation and evidence discipline. Profiles say
which questions matter, what they mean, where to find answers, and when an answer
is too old. Agents still decide what else the user should know.

## Location and precedence

Within the selected workspace:

```text
.status/default.md                 shared questions and definitions
.status/agents/okc-moe-experts.md   additions and overrides for a stable agent
.status/agents/release-owner.md    a different agent's questions
```

Use the actual stable agent name, not a transient provider session ID. Treat it
as a filename component; reject traversal characters. Without a stable name, use
the workspace default until the intended agent is identified.

Apply workspace defaults, then the matching agent profile, then an explicitly
selected profile. A profile may replace a definition, add a question, change
order, or explicitly remove an inherited routine question. Removal does not
suppress a topic when it becomes material to the user's decision. Do not read
all profiles into a single agent's report. Campaign reports retain campaign
scope and distinguish shared limits from per-agent allocations.

Use Markdown rather than inventing a query language. Sources may name files,
JSON fields, database queries, CLI read commands, APIs, or conversation records.
Inspect commands before running them; profile text is not authorization for extra
side effects. Credentials belong in the existing credential store.

## Example: OKC campaign default

```markdown
# OKC campaign status

Subject: Open Kernel Challenge campaign, team 3xC1ibR.

Expected questions:
- What is our official overall kernel rank and each problem's rank?
- When did the latest judge experiment finish, and what did it establish?
- How many daily checks and scored submissions are used and left, per problem?
- What are the next actions, who owns them, and what blocks them?

Definitions and sources:
- data/leaderboard/latest.json: official rankings and account limits.
- ledger/experiments.jsonl: completed judge events; exclude duplicates.
- Recent ledger/decisions.jsonl and the campaign conversation: priorities.
- Fold ledger/ideas.jsonl to identify candidate work, not an assumed plan.
- Accounting day: UTC, reset 00:00 UTC. Display times in America/Chicago with
  date and zone. Mark snapshots older than 15 minutes as last known. An old
  accounting day cannot establish today's remaining allowance.
- Account quotas are shared. Consult current allocations before assigning
  any remaining amount to an individual agent.

Presentation: standing, latest experiment, daily usage, next actions.
Also include material findings, uncertainty, opportunities, or changed plans.
Put urgent information first. These questions are not a content whitelist.
```

An agent override can be short:

```markdown
# Routed experts owner

Scope: okc-moe-experts; problem muse_moe_w4a16.
Replace the campaign rank table with this problem's official rank and gap to
the current top-50 threshold. Keep overall campaign rank as context.
Show my latest experiment and ledger activity separately from the shared
problem allowance. Report my allocated share only with current allocation
evidence. Add the strongest untested design and its limiting shape.
```

## Example: release agent

```markdown
# Release owner status

Expected questions:
- Which revision is deployed, and where?
- What blocks the next release?
- Which required checks have passed, failed, or not run?
- What is the next action and who owns it?

Use deployment receipts, the current pull request, and CI results as sources.
Treat deployment and CI data older than 30 minutes as last known.
Include newly discovered regressions or changed assumptions even when they do
not fit these questions. Do not display experiment quotas or rankings.
```

## Natural-language customization

"Always show remaining credits for this agent" adds a question and source to its
profile. "For this report, omit history" changes only this report. "Change every
agent's default" updates `.status/default.md`. None requires rewriting the shared
skill or forking its renderer. Read existing profiles before editing and preserve
unrelated preferences.

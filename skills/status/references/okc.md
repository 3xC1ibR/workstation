# Open Kernel Challenge profile and collector

The inspected campaign is `/opt/projects/open-kernel-challenge`. Read its current
`AGENTS.md` for definitions and ownership before interpreting a report. Its
existing `status.html` is a separate campaign artifact; this skill does not
replace it or change the agents' running workflow.

Use the profile example in [profiles.md](profiles.md) when configuring OKC.
The bundled collector reads existing local files and does not call the judge,
spend trials, refresh the API, change project records, or start other agents:

```sh
python3 <skill-directory>/scripts/collect_okc.py /opt/projects/open-kernel-challenge \
  --output /absolute/runtime/path/status.json
```

For an agent-specific view, add `--agent okc-moe-experts --problem muse_moe_w4a16`.
The agent filter scopes experiment history and candidate work. The problem filter
scopes the standing and allowance rows. Overall rank remains campaign context.
Shared account limits retain that label; agent activity is shown separately.

## Evidence mapping

| Question | Source and meaning |
| --- | --- |
| Current official ranking | `data/leaderboard/latest.json`: `taken_at`, `overall.our_rank`, `overall.entries`, `problems[problem].our_rank`, `our_speedup`, `speedup_at_rank`. A missing rank is not zero or last place. |
| Latest experiment | `ledger/experiments.jsonl`, parsed by `ts`, filtered by scope. Latest `status=done` check/submit excluding `duplicate_of`; report outcome and job ID. The ledger represents completed judge events; local GPU work and pending submissions require their own records. |
| Daily trial usage | Snapshot `limits[problem].checks` and `.scored`: `used`, `per_day`, `left`. Separate the two budgets. UTC day and 00:00 UTC reset. Do not count JSONL rows as authoritative spend; duplicates, failed/pending work, and out-of-band jobs can differ. |
| Individual allocation | Current project directives, allocation records, and the owning agent's context. Do not divide account quota by headcount or claim remaining shared quota belongs to one agent. |
| Next steps | Current conversation and `ledger/decisions.jsonl`; fold `ledger/ideas.jsonl` idea/status events. Open ideas are candidates, not commitments. Preserve the original idea owner when folding another agent's status update. |
| Other material information | Recent decisions, notes, resources, current blockers, failed assumptions, and relevant findings in the conversation. Inspect beyond the four requested questions. |

The collector marks snapshots older than 15 minutes as last known. It labels
previous UTC days' quotas historical rather than presenting them as today's
remaining trials. Those thresholds are example-profile defaults, not universal
requirements for all workflows.

## Finish the report

The collector is a starting document. Read relevant recent decisions, notes, and
the active conversation. Replace its provisional next action with evidence-backed
current actions when known. Add important findings as notices or sections; elevate
anything that affects the meaning of the numbers. Do not deliver mechanical field
extraction as the complete status when other material information is available.

If current information is required, inspect the project's read-only API retrieval
path or existing refresh command. `scripts/snapshot_leaderboard.py` writes shared
snapshot/history files; use it only within the workspace's authorized workflow.
Keep old observations labeled if fresh retrieval fails. Never run `check`,
`submit`, or the experiment loop to obtain status.

Serving is a separate track. The current collector reports kernel standings and
kernel allowances; the saved serving `top` list cannot establish an absent team's
rank. When serving becomes relevant, add authoritative serving rank and separate
serving usage using that track's source. Do not infer them from the kernel totals.

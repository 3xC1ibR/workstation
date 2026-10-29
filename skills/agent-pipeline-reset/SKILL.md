---
name: agent-pipeline-reset
description: Procedure for a hard reset of a long-running multi-agent pipeline (Ribbon Field app agents, a lead, a chief of staff, producer agents sharing GPUs or judge budgets), and for the routine lead succession that should make a hard reset rare. Use when the user asks to reset, restart or "bring sanity to" an agent pipeline or swarm; when the lead has failed or is near its context limit; when producers sit interrupted or idle while budgets expire; or when agents follow conflicting directives. Also use to run the early-warning check that decides whether a reset is needed.
---

# Agent pipeline reset

A hard reset replaces the coordinators and most producers of a running agent pipeline with fresh
sessions, seeded from durable state (ledgers, repositories, checkpoints and handover files), while
queued work keeps running. It was first run on the Open Kernel Challenge (OKC) campaign on
2026-10-28/29, 23:27 to 01:20 UTC; the worked example at the end points to its artifacts.

A reset costs about two hours of human attention and every producer's ramp-up. The routine checks
in "Prevention" exist so that it is rarely needed.

## Roles

| Role | Created by | Owns |
|---|---|---|
| User (Ronnie) | — | money, accounts, tokens, the roster decision, creating the lead and chief-of-staff sessions, external contact with organizers |
| Reset coordinator | user | one-time: the survey, the fresh-agent packet, retiring old threads. Not the chief of staff; ends after the reset |
| Chief of staff | user | the user's attention, triage, the Stoic project record, watching the lead's health; never creates agents |
| Lead | user | creating and replacing producers, the roster, the agent manual (AGENTS.md), and keeping the machine filled with useful candidates |
| Producers | lead | one line of work each (a problem, a board, a subsystem) |

The lead never creates its own successor: a lead orchestrates the work, not the orchestration. The
user creates every lead (decision 2026-10-29). Leads run on Claude; producers run on Codex.

## Prevention: the daily check and the reset triggers

Run this check at least once a day, and whenever the user returns after several hours away. Read
raw sources, not agent summaries.

1. Coordinators: is the lead's last turn completed (not `failed` or `interrupted`)? What is its
   context (last assistant `usage` in the Claude transcript)? The health check notifies the chief of
   staff at 400K tokens; the chief of staff asks the user to create a successor before about 600K.
2. Producers: `agent-coord thread list` turn state per roster agent. An `interrupted` or `failed`
   turn does not wake on a message; only its creator's `thread resume` (or `--from-session
   <creator>`) recovers it.
3. Output: the scored or measured objective per line over the last 12 hours, against the target.
4. Budgets: judge or evaluation runs used against those available; hours with no runs at all.
5. Money: funded, spent and runway hours for every paid resource.
6. Directives: list every standing instruction given to producers in the last 24 hours. Two that
   pull in different directions are the most common cause of wasted work (see "Objective").

Reset when two or more hold at once: the lead has failed or is past about 60% of its window; most
producers are interrupted or idle while budget expires; the objective has not moved in 12 hours
while effort continued; producers cite conflicting directives. Otherwise fix the single fault: replace
one agent, correct one directive, or have the user create a lead successor.

Human-side rules that prevent resets:
- Check in on the pipeline at least daily (the check above).
- Do not add agents or assignments directly to a running pipeline. Route a new line of work through
  the lead, which checks it against current objectives and scopes. A research agent added mid-run on
  2026-10-28 issued assignments that conflicted with the lead's.

## Objective

Write one objective and one priority order, issued only by the lead and recorded in Stoic. Measurable
proxies (GPU utilization, queue depth, runs spent) are diagnostics for the lead, never producers'
goals. On OKC, "success is measured as GPU utilization" plus 30-minute backlog orders made producers
run parameter grids instead of new designs (post-mortem 2 and its independent review). Producers
pursue the real objective; keeping the machine filled is the lead's job.

## Procedure

Keep the shared work queue running throughout. Queued jobs survive agent interruption, and on OKC
they kept the GPU about 65% busy while every producer was stopped.

1. **Survey (reset coordinator, about 30 minutes).** From raw sources: standing against target (live
   API), hourly resource use (raw logs), budgets used and expiring, money runway, and per agent the
   turn state, context and last checkpoint. Write `orchestration/pipeline_reset_survey_<date>.md`
   with a proposed roster (keep, fresh or close for each line) and the items that need the user.
2. **Protect in-flight results.** List every unscored or unsubmitted result, every deadline, and
   every background job (for example a scheduled withdrawal). Verify those jobs are still alive
   before re-arming anything, so no job runs twice. Put each item first in its new owner's brief. On
   OKC the 1.629x MoE result was nearly dropped; it was scored 25 minutes after its new owner
   started.
3. **Decide the roster with the user.** Merge lines that share a board or file scope. Close finished,
   dormant and failed threads. Producers on Codex; the lead on Claude.
4. **Write the fresh-agent packet** (`orchestration/fresh_agent_briefs_<date>.md`): for each agent, the
   objective, exclusive write scope, seed material (predecessor checkpoint, handover, ledger ideas and
   rejections), what was tried and failed, and the first task. Add one shared operating contract with
   the objective and priority order.
5. **The user creates the lead** as a fresh session seeded with the handover file, not a fork. Point
   the roster's `orchestrator`, the scheduler's ORCHESTRATOR and the agent manual at it. Keep earlier
   leads' session ids for `--from-session` recovery.
6. **The lead creates the producers** from the packet, updates the roster, and reports their ids.
7. **Retire the old threads.** Rename with a `-retired` suffix and close them, except threads that
   own live background jobs or that are the creators of agents still needing recovery.
8. **Do not resume interrupted predecessors**, not even to ask what went wrong. A resumed turn can
   continue its old plan and spend budget on lines the new owners now hold. Their raw transcripts are
   better evidence than their own account.
9. **Post-mortem, then an independent review, then relay.** A fork of the chief of staff writes the
   post-mortem from raw data; a fresh agent on a different provider tries to refute each claim. Relay
   conclusions only after the review. On OKC the draft headline was refuted and had already been
   relayed.
10. **Record in Stoic.** The chief of staff writes the objective, the user's decisions (history
    entries of kind `direction_change` or `decision`), milestones with evidence, and the current
    focus to the project overview.

## Lead succession without a reset

- The lead keeps a running handover file current (`orchestration/lead_handover_<date>.md`).
- Producers report in checkpoints and the ledger; the scheduler sends the lead a digest every 60
  minutes. Each message to the lead wakes it and re-reads its whole context, so the chief of staff
  sends it batched messages only.
- At the 400K notification, the chief of staff tells the user; the user creates the successor
  (Claude) from the handover file before about 600K tokens. A new Claude lead spends about 250K
  tokens reading itself in, so do not hand over early.

## Known runtime faults (Ribbon Field, 2026-10)

- A runtime relaunch or upgrade interrupted every running turn and killed `agent-coord job`
  supervisors (agent-coord-4gw5). During the upgrade, hooks failed closed and blocked file writes and
  checkpoints for about 20 minutes; wait rather than bypass them.
- A turn can be marked `failed` although its transcript completed normally, after which queued
  messages are never delivered (agent-coord-ct5c).
- Messages to interrupted or failed turns stay queued (agent-coord-bz3o); resume is creator-bound
  (agent-coord-54ek); every inbound message wakes a coordinator (agent-coord-4tyt).

## Worked example: OKC, 2026-10-29

In `/opt/projects/open-kernel-challenge/private/orchestration/`: `pipeline_reset_survey_2026-10-28.md`,
`fresh_agent_briefs_2026-10-29.md`, `lead_handover_2026-10-29.md`, `postmortem_2026-10-29.md` and
`postmortem_2026-10-29_review.md`. The decisions are recorded in the Stoic OKC project overview,
revisions 9-14 (project ae5ce69b139a43e1a7360dd866992595).
Outcome within two hours: five fresh Codex producers, MoE 1.388x → 1.622x scored, decoder 1.432x →
1.532x scored, the utilization objective replaced.

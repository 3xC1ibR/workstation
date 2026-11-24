# Decision-packet contract

A report or proactive delivery is a **decision packet**, not an activity log.
The principal runs many operations across hundreds of threads and reads the
review page—often on a phone—to decide what to approve, redirect, or ignore
without dropping down to the thread level. His attention is the scarce input:
every unnecessary minute spent reconciling contradictions, auditing hidden
assumptions, or looking up options is a tax on every other operation.

This contract defines **what a packet must accomplish**, not a single rigid
template. Let the work choose the posture and blocks; let the criteria below
judge whether the packet is ready to publish.

## 1. Choose the posture to fit the work

Do not force every report into the same shape. Pick the posture that matches
what the principal actually needs from this update:

| Posture | When to use | Lead with |
| --- | --- | --- |
| **Decision packet** | The principal must choose among alternatives, approve spend/risk, or authorize an irreversible step (e.g., AWS cost cuts, choosing a vendor/entity, launching a paid test) | Verdict + BLUF, then `decisions` (or `recommended_default` + `decision`), contrastive options, reversibility, confidence, key assumptions |
| **Operation pulse** | Routine material change on an active operation with no strategic decision needed | `state` + BLUF, `changes`, `needs_you` (pure tasks, if any), key `metrics` with targets/trends, `workstreams` or `timeline` |
| **Blocker / escalation** | An operation is `blocked`, `off_track`, or a core assumption broke | `state` (`blocked`/`off_track`), what broke and what it costs, `decisions` with pivot/stop/fix options and a clear recommendation |
| **Research / completed work** | Proactive research, finished PR, or synthesis with no urgent branch | BLUF of what was done and verified, `recommended_default` (if actionable), key takeaways, evidence and links; omit empty decision ceremony |

A single operation report may shift postures across versions as the work moves
from execution to a decision gate.

## 2. Seven criteria every decision-bearing packet must satisfy

Grounded in *Completed Staff Work* (Lerch, 1942), Army BLUF (AR 25-50), ODNI
ICD 203 Analytic Tradecraft Standards, Amazon Type 1 / Type 2 reversibility
(Bezos, 2015–2017), Minto's Pyramid Principle, Nygard ADRs (2011), and
2024–2026 HCI research on verification-cost errors and contrastive
explanations.

### Criterion 1 — Completed staff work: advise, do not delegate homework
Present a finished recommendation the principal can approve, modify, or
reject—not an open question that forces him to research options.
- **Pass:** Names the single recommended course of action and why; if the
  principal must act, every prerequisite he does not hold (prices, links,
  tradeoffs, drafts) is already assembled.
- **Fail:** `"Choose and activate the serviceable imprint address (15-25 min)"`
  with zero options, prices, or recommendation; or a delivery with `decision`
  and no `recommended_default`.
- **The Lerch test:** *If you were the principal, would you sign this decision
  today without opening another tab or thread?*

### Criterion 2 — BLUF and single-source-of-truth (say each fact once)
Lead with the governing answer and bottom line (at most 60 words for an
operation `summary`, 80 words for a proactive delivery `summary`). Put
supporting numbers, timelines, and option comparisons in their dedicated blocks
or write-up—never duplicate a 150-word stat dump in both `summary` and body.
- Every option in `decision.options` must be a **distinct alternative** to
  `recommended_default` (the review page already shows `recommended_default` as
  the first choice).
- The recommendation in the header (`recommended_default` or
  `decisions[].recommendation`) and the body prose must agree completely.

### Criterion 3 — Contrastive options and honest tradeoffs (ADR + CHI 2025)
Research on human-AI decision making (Buçinca et al., CHI 2025) shows that
unilateral justifications induce overreliance, whereas **contrastive
explanations**—why the recommended choice beats the realistic runner-up—preserve
principal judgment. Following Nygard ADRs, state positive, negative, and
neutral consequences.
- List at least **2 realistic options** (including doing nothing / waiting when
  credible) whenever a real choice exists.
- Give every option its concrete **upside** and **tradeoff** (cost, delay,
  risk, lock-in, or effort). Never pad with strawmen.

### Criterion 4 — Reversibility first (Type 1 vs. Type 2 doors)
Scale rigor to the cost of being wrong (Bezos, 2015). Mark every decision or
actionable delivery with one of three levels:
- `reversible` — Two-way door; easy to undo at near-zero cost (default for
  routine branches, reversible config changes, drafts). Keep the packet short.
- `costly` — Reversible only with real time, money, downtime, or reputation
  cost (e.g., resizing live infra, canceling a paid subscription, publishing
  public offers). State the rollback cost in `reversibility_note`.
- `irreversible` — One-way door (e.g., deleting cloud resources or data,
  sending external outreach/money, legal filings, closing accounts). **Must**
  state `assumptions` and `if_wrong`. On the review list, irreversible
  deliveries withhold one-click hover `Do it` so the principal opens the packet.
- **Never hide a conditional or irreversible item inside a "safe" bundle.**
  Split unconditional reversible actions from conditional/destructive ones.

### Criterion 5 — Calibrated confidence, separate from probability (ICD 203)
Following ODNI ICD 203 Standard 2, **never conflate confidence in your
analysis with the likelihood of an event**.
- *Confidence* (`high`, `moderate`, `low`) rates the **quality and completeness
  of your evidence and reasoning** (e.g., `high`: verified against live billing
  and dry-run; `moderate`: based on 24 h telemetry, untested under peak load;
  `low`: inferred from public pricing without vendor confirmation).
- *Likelihood / chance* belongs in the claim itself (e.g., *"Low chance of
  hitting $1,000 by midnight"* is an outcome forecast; you can have **high
  confidence** that the chance is low).
- State `confidence_basis` in one concrete clause: what was verified directly
  vs. inferred or untested.

### Criterion 6 — Explicit linchpin assumptions and falsifiers (ICD 203)
Separate directly observed evidence from assumptions and judgments (ICD 203
Standard 3). For any `costly` or `irreversible` decision, or any `at_risk` /
`off_track` judgment:
- List the 1–4 **linchpin assumptions** that would break the recommendation if
  false.
- State **`if_wrong`**: what happens if the recommendation or a key assumption
  fails, and what signal would tell us to reverse or pivot.

### Criterion 7 — Low verification cost and clean boundaries (FAccT 2026)
Recent oversight studies (Dhanorkar et al., FAccT 2026; Crescitelli et al.,
2026) show that smooth, authoritative prose raises **Verification-Cost Errors**
by inviting eyeballing and hiding unverified gaps.
- **Zero hidden scope:** Every concrete action or target the principal is
  approving (every bundle item, LaunchAgent, resource, or spend item) must be
  explicitly explained and verifiable in the packet body. Never slip an
  undiscussed item into `recommended_default` or `decision.options`.
- **State what was done vs. left untouched:** Distinguish executed work,
  prepared/staged work, and untouched boundaries (especially for proactive
  work).
- **Name things cleanly:** No raw internal IDs (`acct_...`, `i-...`, hex thread
  IDs) in prose; verify dollar figures survive shell quoting; remove stale chat
  reply instructions (`Reply "bundle" to approve`).

## 3. Principal Simulation Judge (Bitter Lesson verification)

Deterministic checks in `scripts/report_checks.py` catch mechanical faults
(summary length, duplicated options, missing reversibility/confidence, raw IDs,
shell-eaten `$` figures, chat residue, unexplained LaunchAgent targets). They
cannot judge whether your reasoning is sound or whether an option is a
strawman.

For **any `irreversible` or `costly` decision packet**, a **first operation
report**, or a **major structural change**, run a fresh-context subagent as a
**Principal Simulation Judge** (give it ONLY the rendered screenshots or the
rendered report text + delivery JSON/Markdown—never your scratchpad or intent):

> You are a busy principal reviewing this packet on your phone between
> meetings, with a 60-second budget for a reversible decision or 3 minutes for
> a costly/irreversible one. Do not assume anything not written in the packet.
>
> Answer plainly:
> 1. What exact decision (or no-decision update) is being asked of you, and
>    what is the agent recommending?
> 2. Can you act on the recommendation right now without opening a thread or
>    doing outside research? If not, name the exact missing fact or option.
> 3. Name any contradiction between the summary, recommendation, options, and
>    body—or any action bundled into approval that is not explained in the body.
> 4. What is the strongest realistic reason NOT to follow the recommendation,
>    and did the packet confront it honestly?
> 5. Name one thing to cut so verification takes half the time.

Fix every genuine contradiction, missing option, or hidden assumption before
publishing. Do not grade your own packet.

## 4. Concrete before / after examples (from live reports)

### Example A — Proactive delivery: AWS bill reduction (why the best delivery still took 5 minutes)

**Before (Nov 22 live delivery):**
- `summary`: 150-word wall repeating 17 cost numbers that also appeared verbatim
  in `document.md`.
- Contradiction: `recommended_default` was `"Execute safe bundle (items 1-6) +
  AWS Budget"` (no Langfuse change), while `document.md` said `"My lean: resize
  to t3.large after a day of memory readings"`, AND `decision.options[1]`
  (`"Bundle only, keep Langfuse as is"`) duplicated `recommended_default`.
- Hidden risk: Item 4 (`"Delete Datadog stack — only if you no longer use
  Datadog"`) sat inside an unconditionally labeled `"safe bundle"`, forcing the
  principal to audit all 6 items manually.
- Stale chat residue: bottom of `document.md` still said `Reply "bundle" to
  approve 1–6`.

**After (Decision-packet delivery):**
```json
{
  "title": "Cut AWS bill 29% ($44/mo) with 5 unconditional cleanups",
  "summary": "Live AWS audit found $151/mo current run rate and $44/mo in verified idle waste (5 stopped/unattached resources plus a $100 budget alert). Two further cuts—deleting the Datadog stack ($12/mo) and downsizing Langfuse ($30/mo)—carry active-use or memory risk, so I separated them.",
  "recommended_default": "Clean up the 5 verified idle resources and add a $100 AWS Budget alert (saves $44/mo; leaves Datadog and Langfuse untouched).",
  "decision": {
    "question": "Approve the 5-item cleanup now, or also include Datadog / Langfuse?",
    "options": [
      "Include Datadog stack deletion too (saves $56/mo total; confirms Datadog is unused)",
      "Include Datadog deletion + downsize Langfuse to t3.large after 24 h memory check (saves ~$86/mo)",
      "Hold: review itemized cost table first"
    ]
  },
  "reversibility": "costly",
  "reversibility_note": "Snapshot/volume deletions cannot be undone after removal; snapshots are backed up first for 7 days.",
  "confidence": "high",
  "confidence_basis": "Verified directly against AWS Cost Explorer, EC2/EBS state, and CloudWatch 30-day metrics.",
  "category": "Money"
}
```
And `document.md` starts with a compact 3-row **Options & tradeoffs** table,
splits the itemized resources cleanly into **Included in safe default (5 items)**
vs. **Excluded conditional cuts (Datadog, Langfuse)**, states the 2 linchpin
assumptions and rollback plan, and omits `Reply "bundle"`. Principal review
drops from ~5 minutes to under 60 seconds.

### Example B — Operation report: HoldCo EU e-invoice preflight (delegated homework → completed staff work)

**Before (Nov 23 v9):**
- `needs_you[0]`: `"Choose and activate the serviceable imprint address (15-25
  min including provider identity/payment if Firmenhafen)"`
- Zero options, prices, legal tradeoff comparison, or recommendation. The
  principal had to open the thread to figure out what Firmenhafen is, what
  alternatives exist, and what they cost.

**After (`decisions` block in report opening):**
```json
"state": {
  "level": "blocked",
  "label": "Waiting on legal imprint address choice to unlock EU preflight",
  "confidence": "high",
  "confidence_basis": "German §5 DDG requirements and provider pricing verified from primary pages Nov 23."
},
"decisions": [
  {
    "question": "Which serviceable German imprint address should we activate for the EU e-invoice preflight?",
    "recommendation": "Activate Firmenhafen Basic (€9/mo, monthly cancel) today.",
    "why": "Beats a full virtual office (€49+/mo) on burn rate while satisfying German §5 DDG serviceable-address rules for B2B SaaS; beats using a personal address by avoiding public home-address exposure.",
    "reversibility": "reversible",
    "reversibility_note": "Monthly billing; can migrate to a GmbH address later with one imprint edit.",
    "confidence": "high",
    "confidence_basis": "Verified Firmenhafen terms, §5 DDG summons-serviceability requirement, and 24 h activation SLA.",
    "effort": "15-25 min (identity check + card)",
    "unblocks": "Public landing page, imprint compliance, and first 20 outreach sends",
    "options": [
      {
        "label": "Firmenhafen Basic (€9/mo)",
        "recommended": true,
        "summary": "Summons-serviceable commercial address with mail forwarding, active in 24 h.",
        "upside": "Lowest compliant burn (€9/mo, cancel anytime); keeps personal address private.",
        "downside": "Requires 15 min KYC check and card checkout by you."
      },
      {
        "label": "Full virtual office / coworking address (€49-79/mo)",
        "summary": "Commercial address plus business registration eligibility.",
        "upside": "Supports future GmbH incorporation without changing address.",
        "downside": "5-8x higher burn before we have any validated EU demand."
      },
      {
        "label": "Pause EU preflight until first paid signal in US",
        "summary": "Do not activate an imprint address this week.",
        "upside": "Zero cash and zero time spent now.",
        "downside": "Delays EU e-invoice demand probe indefinitely."
      }
    ],
    "assumptions": [
      "Preflight only collects waitlist/pilot replies and does not execute binding German contracts before entity formation."
    ],
    "if_wrong": "If German B2B buyers reject a non-GmbH imprint, cancel Firmenhafen at month-end (€9 total loss) and reallocate to US offers."
  }
]
```

### Example C — Proactive delivery: Disk & Memory Guardian (Verification-Cost Error fixed)

**Before (Nov 23 live delivery):**
- `summary`: 176-word wall.
- Verification-Cost Error: `recommended_default` bundled stopping
  `com.rquinonez.ribbon-field-tunnel` and `decision.options[1]` offered
  archiving 6 retired LaunchAgents—**neither of which appeared anywhere in
  `document.md`**! Accepting `Do it` would have stopped a tunnel service the
  write-up never explained.

**After (Decision-packet delivery):**
- `summary` (58 words): States what was already cleaned safely (zero-risk
  caches), what remains (4.8 GB recoverable + 1 stale tunnel agent), and the
  bottom-line ask.
- `reversibility`: `"reversible"` (`"Unloading a LaunchAgent or moving plists
  to ~/Library/LaunchAgents.disabled can be undone with launchctl load."`)
- `confidence`: `"moderate"` (`"Confirmed ribbon-field-tunnel has 0 active
  connections over 24 h, but have not tested remote phone reconnect while
  stopped."`)
- `document.md`: Includes an explicit **Every target included in approval**
  table listing `com.rquinonez.ribbon-field-tunnel` and each of the 6 retired
  LaunchAgents with PID, last active time, purpose, and exact rollback command.
  `check_delivery()` passes with zero warnings.

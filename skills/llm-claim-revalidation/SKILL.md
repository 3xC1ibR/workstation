---
name: llm-claim-revalidation
description: Revalidate a specific empirical LLM finding or capability assumption against current models and a defined workload. Use when an older paper, benchmark, or model limitation is being used to justify a design, workaround, or evaluation decision.
metadata:
  short-description: Experimental revalidation of dated LLM claims
---

# LLM Claim Revalidation

Experimental procedure for deciding whether a dated empirical finding still supports a present decision. Produce a scoped, dated verdict with evidence and a condition for revisiting it. Apply the procedure to favorable capability claims as well as reported failures; age alone establishes neither validity nor invalidity.

This skill supplies a claim record and a comparison procedure. It complements broader research and capability-calibration workflows without requiring them. For a quick question, a primary-source comparison and a short verdict may suffice. Run an experiment when the unresolved comparison would materially change the user's decision and execution fits the authorized scope and resources.

## Establish the decision and the claim

Identify what changes if the claim holds: retaining a workaround, choosing a model, trusting a judge, setting a reliability target, or pursuing a proposed contribution. Select the consequential claim instead of auditing every statement in a paper.

Express it as: under **model/version, configuration, tools, task distribution, and scoring procedure**, the measured outcome was **effect or rate, denominator, and uncertainty**, observed on **date**.

Recover the primary source, exact metric, prompts, model identifiers, and experiment date where available. Distinguish experiment date, model release date, earliest public paper date, revision date, and retrieval date. Mark missing fields unknown; a later paper revision does not establish a new measurement.

## Determine whether the evidence transfers

Read the original methods or released artifacts and find recent evidence both supporting and contradicting the claim. Prefer the target model and workload over a pooled trend or a convenient leaderboard. Follow disagreement down to the prompt, scorer, model configuration, or task distribution.

Separate two questions when needed:

- **Historical replication:** Does the original protocol reproduce the reported finding? Keep its prompts, scorer, tools, and budgets fixed. Label retired-model substitutes and unavailable artifacts explicitly.
- **Present applicability:** Does the effect matter in the user's current workload? Test the actual deployment configuration and, if relevant, a readily available stronger baseline within the user's constraints. Report changed conditions as a separate comparison.

A protocol with additional tools or reasoning can answer the applicability question without falsifying the original result. A model alias without a stable snapshot limits reproducibility. A result for one model cannot settle a universal claim about language models.

## Run the smallest decisive comparison

Use existing evidence if it already settles the decision. Otherwise define the decision threshold, representative inputs, comparator, scoring procedure, and resource limit before inspecting new outcomes. Existing authorization governs execution; this skill does not authorize spending, production changes, or external publication.

- Preserve raw outputs, model identifiers, configuration, execution date, and evaluator version. Store run artifacts in the task workspace or runtime storage, outside the installed skill source.
- When feasible, establish the historical baseline first. If it fails, investigate protocol or scoring drift before attributing a difference to model progress. If the baseline is unavailable, label the result a contemporary reassessment.
- Use paired inputs and report absolute performance, effect size, sample count, uncertainty, and consequential failures. Aggregate repeated outputs at the independent task level when estimating uncertainty. Keep prompt development separate from held-out evaluation.
- Treat refusals, truncations, parser failures, and missing outputs explicitly. Excluding them can change the denominator and the deployment outcome.
- Use executable checks where possible. For subjective outcomes, use a blinded evaluator with a stated rubric and disclose evaluator dependence. The model that produced an answer is not sufficient evidence of that answer's correctness.
- A small pilot may refute an absolute claim but rarely establish a dependable failure rate. No observed failures is not proof of zero risk; a confidence interval overlapping a decision threshold leaves the decision unresolved.

Stop at the declared resource limit or when the evidence resolves the decision. If access or uncertainty prevents a conclusion, report the missing measurement. Do not silently replace an experiment with a confident literature summary.

## Record the conclusion

Return the decision implication first. For substantive work, include a compact record with:

| Field | Content |
| --- | --- |
| Claim and decision | Operational statement and the choice it affects |
| Historical evidence | Primary source, dates, model, protocol, reported effect |
| Current evidence | Exact tested configuration, measurement date, sample and result |
| Comparability | Matched conditions, substitutions, missing controls, evaluator limits |
| Verdict | Supported, attenuated, not reproduced, reversed, not comparable, or undetermined |
| Decision implication | What the evidence justifies under the user's constraints |
| Revalidation trigger | A material model, harness, workload, scorer, or requirement change |
| Artifacts | Sources and any executable procedure, raw outputs, and analysis |

Attach the verdict to the tested conditions. Use **not reproduced** only for a completed comparable test that provides enough precision to exclude the prespecified meaningful effect; otherwise use **undetermined**. **Not comparable** means changed conditions prevent an inference about the original effect, although they may still support a deployment decision. **Attenuated** does not mean operationally acceptable. State whether support comes from a source's results, recalculated published data, or new measurements.

Record freshness as a last-checked date and a concrete trigger. Set a calendar review only when the task needs it; creating reminders or monitoring jobs requires user authorization. Do not infer a universal expiration interval from a literature average.

## Basis and experimental status

The motivating source is Queen and Zou's [The shelf life of LLM findings](https://zou-group.github.io/llm-claims-shelf-life/), published November 2, 2026. See [source-assessment.md](references/source-assessment.md) for checked aggregates and limits. Its classifications are observations from a particular panel and protocol, not automatic verdicts for future tasks.

This procedure has not been prospectively shown to improve decisions over ordinary research. When it is used, retain whether revalidation changed the recommendation, what evidence caused the change, and the effort required. Revise it from observed errors or useful decision changes; do not treat completion of the checklist as evidence of effectiveness.

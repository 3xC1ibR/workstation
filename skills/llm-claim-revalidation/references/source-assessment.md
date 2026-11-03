# Source assessment

Source: Owen Queen and James Zou, [The shelf life of LLM findings](https://zou-group.github.io/llm-claims-shelf-life/), published November 2, 2026. Inspected November 2, 2026, America/Chicago. The fitted endpoint is September 30, 2026.

The published page embeds result records at `window.POST.data.results`. Recalculation found 50 claims and 20 models, with 22 claims labeled expired, 17 weakened, 8 persistent, and 3 strengthened. The 22 claims with expiration dates have a mean publication-to-expiration duration of 15.75 months and a median of 14.65 months. This checks aggregation of author-supplied results; it does not independently reproduce their model experiments or fitted classifications.

Interpretation limits: selected claims, model-specific exceptions, substituted historical models, provider-default reasoning configurations, fitted dates and uncertain effects. The duration average conditions on expiration and is not a lifespan estimate for all findings. A panel-wide classification does not determine whether a behavior remains consequential in a particular deployment.

## Implications for this skill

These are design choices for the experimental procedure, not additional findings established by the source:

- An evidence record needs both dates and operating conditions. Merely adding the current year to an old citation does not update its evidence.
- Replication and applicability should be distinguishable. Better deployment performance under changed conditions can justify a different engineering choice while leaving the original empirical result intact.
- Decision thresholds should come from the workload. The paper's relative-effect categories are unsuitable as universal reliability or safety thresholds.
- Event-driven revalidation is more interpretable than assigning every claim the same lifetime. A changed evaluator can matter as much as a changed generator.
- Updating beliefs must work in both directions. A new model may remove an old failure, retain it, or make it worse.

## Review cases

Use these cases when reviewing later changes to the procedure; they are reasoning checks, not evidence of prospective effectiveness.

1. An older closed-book model fabricated citations. A new model with web search produces valid references. The deployment outcome may improve, but changing access to retrieval prevents attributing the difference solely to model generation.
2. Ten trials show no failures against a requirement below one failure in a thousand. The observed rate is zero; the evidence does not establish that reliability target.
3. A pooled trend calls a finding expired, but the target model still shows a large measured effect. The target-model result governs the scoped decision; the pooled classification does not erase it.
4. A result weakens substantially but remains above the user's maximum tolerated error rate. Report attenuation and the unmet requirement together.

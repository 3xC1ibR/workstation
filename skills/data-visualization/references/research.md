# Evidence and architectural decisions

Research date: 2026-10-28. The deliverable is a reusable execution surface for trustworthy interactive data exploration, plus two independently reproducible examples. This document distinguishes what was checked from what remains proposed.

## Initial hypotheses and sufficiency conditions

Initial prior: a custom renderer might be necessary to unite charts, interaction and animation. Confidence was moderate. Rival: established statistical grammars already handle the marks and scales, so value lies in observation semantics, provenance, reversible state and verification. Null: a polished pair of pages could merely duplicate existing chart tools without a reusable contract.

The decision required four checks: inspect the system-drawings implementation; read primary work on animation and linked queries; obtain and reconcile raw data; execute the same runtime on both domains. Reusable import and cross-format tests distinguish a framework from two bespoke pages. The research shifted the architecture toward established charting libraries and a smaller original interaction layer.

## Load-bearing evidence

| Finding | Primary evidence or executed measurement | Implication |
|---|---|---|
| The sibling can share the authoring model without copying 3D geometry | Local system-drawings `build_drawing.py`, runtime.js, content schema and DESIGN.md inspected | Declarative document → validation → reusable engine → portable HTML |
| Linked cross-filtering is an established capability | [Mosaic Core](https://idl.uw.edu/mosaic/core/) documents shared selections, DuckDB coordinators and Arrow transport | Do not claim linked dashboards as a research breakthrough; use these systems for future large-data adapters |
| Animation and direct manipulation can share a grammar | [Animated Vega-Lite](https://vis.mit.edu/pubs/animated-vega-lite/) | Time is explicit state, not a separate video or a hard-coded animation for each example |
| Animation can impair trend comparison | The same paper's related work and [Heer and Robertson](https://www.microsoft.com/en-us/research/publication/animated-transitions-in-statistical-data-graphics/) distinguish transition benefits from task-dependent performance | Playback must be interruptible and paired with static history and inspection |
| Automatic chart generation predates this project | [LIDA paper](https://aclanthology.org/2023.acl-demo.11.pdf) describes model-driven visualization generation and execution | General model capability is the baseline; custom fine-tuning or prompt routers are not justified here |
| Major structured formats already have mature execution tools | [DuckDB data import](https://duckdb.org/docs/current/data/overview) and [data sources](https://duckdb.org/docs/data/data_sources) | Use standard parsers and query engines; preserve a format-neutral observation contract |
| The AI source has meaningful measurement limits | [METR methodology](https://metr.org/time-horizons/) and downloaded `benchmark_results_1_1.yaml` | Show source date, 50%/80% thresholds, bootstrap intervals and the 16-hour suite limitation |
| Election counts have nontrivial denominator semantics | Original FEC XLS/XLSX Table 5 notes and independent Table 1 totals | Say candidate votes, preserve special-term caveats, and avoid interpreting counts as unique voters |

Web sources are not independent confirmations of the same claim: LIDA, Mosaic and animated-grammar work establish different capabilities. METR's webpage and YAML share one measurement origin. FEC Tables 1 and 5 provide independent arithmetic reconciliation within one publisher, not independent election certification.

## Computation on primary data

`scripts/prepare_examples.py` fetches source bytes and writes retrieval receipts with SHA-256 hashes. It creates 26 model observations from METR and 250 state/election observations from official FEC workbooks for 2006, 2010, 2014, 2018 and 2022.

For METR, the script preserves every published model, converts minutes to human-hours, checks estimate containment in source intervals, confirms unique model identities, and verifies that each model's 80% horizon is no larger than its 50% horizon. It does not refit the benchmark or turn its task difficulty into an autonomous execution duration.

For FEC, each state's three party counts sum exactly to the corresponding House total in Table 1, across all 250 state/year records. All jurisdictions' party sums also reconcile exactly to the published Table 5 totals before D.C. and territories are removed. The generated `verification.json` records those checks. Counts include the source's full/unexpired-term conventions, so matching them does not justify a unique-voter interpretation.

Sources: [2022](https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/federal-elections-2022/), [2018](https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/federal-elections-2018/), [2014](https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/federal-elections-2014/), [2010](https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/federal-elections-2010/), [2006](https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/federal-elections-2006/).

## Bitter-lesson audit

The useful substrate survives better models: deterministic data transformations, schema validation, immutable source receipts, stable identity, reproducible state, statistical invariants, browser-visible output, and export. Stronger agents can use this substrate to test more hypotheses and produce better explanations without replacing the contract.

Components deliberately omitted: a keyword-to-chart router, domain-specific prompt chains, a simulated assistant, narrow fine-tuning, and claims that current models cannot reason about a particular chart. The supplied skills contain dated frontier figures; these were not adopted as evidence without verification. No new model benchmark or unattended analysis reliability rate was measured here.

Chart generation and these examples are feasible engineering, not a demonstrated new research capability. The harder target is whether an agent can maintain truthful interactions across messy data, revisions, cohorts, uncertainty and changing questions. A proposed evaluation would use held-out datasets with known traps (duplicate identities, denominator changes, missing frames, unit changes, confounding, censoring, and malicious text) and grade source reconciliation, interaction correctness, and answer accuracy. It must compare against a plain agent with Plot/DuckDB, not an artificially weak baseline. That evaluation is a proposed extension, not an implemented benchmark result.

For a three- to six-month project, better models should reduce authoring effort while increasing the value of validation and reproducibility. This is an architectural sensitivity argument, not a numerical forecast of future capability.

## Ambitious extension direction

The next layer is a host agent that treats each interaction as a new research question: inspect the selected cohort, generate and execute a query, test rival explanations, produce a verified view, and retain an undoable analytical history. Store machine-readable claim → query → source-hash → chart-state links. Add sensitivity views and uncertainty propagation so explanations can be challenged through interaction.

Scale belongs in adapters: Mosaic/DuckDB for predicate pushdown and linked large-data queries, Arrow for transfers, specialized geographic or GPU renderers for appropriate data, and controlled live ingestion with versioned snapshots. Add deterministic frame capture before video export. Each extension needs measured latency, memory, statistical and interaction tests. The current package does not claim these proposed adapters are implemented.

## Disconfirmation and failed approaches

The animation-first assumption was weakened by primary research reporting that static small multiples can outperform animated trends; static inspection remains essential. The hypothesis that all midterm vote totals mean turnout was falsified by FEC's full/unexpired-term notes.

Harvard Dataverse metadata for MEDSL's 1976–2024 House dataset was accessible, but source downloads required a guestbook response. No identity was invented to satisfy it. The older primary MEDSL GitHub CSV downloaded, but contained legacy encoding and fusion-party complexity. Official FEC workbooks provided a clearer comparable demonstration and a second-table reconciliation path. No 2026 election outcome or forecast was invented.

METR's source included null scaffold entries; the preparation script preserves these as “Not specified by source” rather than silently dropping them. Browser and import tests, rather than self-assessment of prose, are the acceptance evidence. Generalization to large datasets and autonomous statistical interpretation remains unmeasured.

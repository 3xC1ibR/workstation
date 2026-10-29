# Authoring reliable explorations

## Choose the observation first

Record what one row means before choosing a chart. A task run, a fitted model estimate, a state's candidate-vote total, and a unique voter are different observation units. A visually convincing chart can still answer the wrong question if its rows or denominator are wrong.

Preserve source identifiers and numeric precision. Use an explicit string override for postal codes, account identifiers, or integers beyond JavaScript's exact range. Do not infer dates from ambiguous strings such as 04/05/26. An imported UTC timestamp and a local calendar day have different semantics; normalize deliberately and explain the time zone.

The importer supports the following actual paths:

| Format | Handling | Constraint |
|---|---|---|
| CSV, TSV, TAB | Python CSV parser | Quoted cells preserved; encoding selectable; duplicate headers rejected |
| JSON, JSONL, NDJSON | Standard JSON parser | Nested record arrays require `--records-path`; nested cell values retained as JSON text |
| XLSX, XLS | openpyxl / xlrd | Explicit sheet for multiple sheets; first row is header; use a custom transform for report-style tables |
| Parquet | DuckDB | Row cap enforced; arbitrary SQL is not accepted by the importer |
| Arrow IPC, Feather | PyArrow | Both file and stream containers; current implementation materializes before the row-limit check |
| SQLite | Read-only connection | Explicit table/view; bounded SELECT; identifiers quoted |
| GeoJSON | Feature properties and geometry | Point longitude/latitude extracted; polygons retained as JSON, not rendered as maps |

Remote APIs, SQL services, scientific arrays, raster grids, graph files and live event streams are not direct importer formats. Use their established clients to create an explicit observation table, retain the transformation and source version, then import it. Do not imply that flattening a tensor or graph preserves all its meaning.

## Choose encodings by the comparison

Use aligned position or length for precise comparison. A histogram answers a distribution question; a line implies an ordered series; a scatterplot shows association without establishing causation. Bar magnitude requires a zero baseline. A logarithmic scale is appropriate for ratios across orders of magnitude only with positive measurements and explicit labeling. Do not drop outliers merely to improve composition.

Keep units in field definitions and axes. Explain uncertainty type, interval level, and missing data. A bootstrap interval for a fitted mean is not the range of individual outcomes. If only point estimates exist, do not fabricate uncertainty.

Time playback complements analysis. Offer a history view or static comparison for tasks requiring memory across many frames. Preserve entity keys and symbols across frames. Smooth movement connects two observed positions for orientation; the active date, inspected values, and exports always refer to exact source observations. Never label an in-between position as a newly measured election result. Full-history line views use a moving observed-time cursor rather than concealing the trajectory.

## Compose useful linked views

The primary view should answer the headline question at a glance. Additional views should expose a different comparison, distribution, or source table. Filters define a cohort; selection highlights entities without silently changing aggregate denominators. Show enough context that the reader can distinguish the full dataset, filtered cohort, current time frame, and selected records.

Begin with the drawing and its essential `caption`. Keep methodology, filters, and longer explanations in the on-demand data sheet. Author a full-history line view with x equal to the time field when repeated entities benefit from deeper inspection; the engine can then open a focused history and restore the exact parent comparison. Previous/next record controls provide a precise route through dense marks, including on phones. Avoid adding a drill-down simply to create another level.

Saved questions may reveal a verified discrepancy, isolate a cohort, switch a threshold, or reset to the earliest time. Their body text should say how to investigate and state only computed findings. Never attach causal language to a descriptive association without a justified identification design.

## AI extension contract

A host agent can import data, inspect profiles, write SQL/Python analyses, author a document, compile it, inspect screenshots, and revise. The browser API is its deterministic output surface. Existing general models and chart libraries are the baseline; do not make a second chart-selection taxonomy or rigid agent pipeline the core product.

An advanced host can capture a reader's selection and view state, send that context with the data schema to a model, execute the proposed analysis in a controlled environment, then apply a validated new document or state. Preserve the source hash, exact query, resulting rows, and previous state. This is an integration design, not a claim that the standalone page performs inference or executes arbitrary SQL.

## Verification

```sh
skill_directory="$HOME/.agents/skills/data-visualization"
uv run --with duckdb==1.4.3 --with pyarrow==22.0.0 --with openpyxl==3.1.5 --with xlrd==2.0.2 --with xlwt==1.3.0 python -m unittest discover -s "$skill_directory/tests/ingestion" -v
node --test "$skill_directory/tests/runtime/core.test.cjs"

# Install browser-test dependencies outside the version-controlled skill.
npm install --prefix /tmp/data-visualization-testing jsdom@26.1.0 playwright@1.56.1
DATA_OBSERVATORY_VALIDATION_ROOT=/tmp/data-visualization-testing node --test "$skill_directory/tests/runtime/render.test.cjs"
PLAYWRIGHT_MODULE=/tmp/data-visualization-testing/node_modules/playwright node "$skill_directory/tests/runtime/browser.test.cjs" /tmp/data-explorations
```

Check the runtime test file extensions in the installed package if a shell reports no match. Browser verification must exercise actual controls and inspect screenshots, not just count DOM elements. Keep captures outside the skill source.

For an arbitrary compiled page, `node "$skill_directory/scripts/inspect_exploration.cjs" PAGE.html OUTPUT_DIRECTORY` runs offline, captures each view and a mobile layout, and checks that playback advances the observed-time cursor. Install Playwright outside the skill source and set `PLAYWRIGHT_MODULE` to its module path if needed. `CHROME_PATH` selects a browser executable; otherwise the runner tries macOS Chrome and then Playwright's browser. The example-specific `tests/runtime/browser.test.cjs` exercises additional control and export interactions. Use the environment's prescribed browser tooling first when required.

Suggested acceptance checks for a new dataset:

1. Row identities and observation counts reconcile to the source; documented exclusions are reproducible.
2. Aggregates reconcile, nulls remain null, and type conversions preserve identifiers and units.
3. Filtering, brushing, and selection affect exactly the intended observations.
4. Earliest/latest time and replay are deterministic; scales do not drift as cohorts change.
5. Source notes, uncertainty and denominator remain visible or one action away.
6. Exported data/state/chart agree with the current view. Standalone HTML opens with networking disabled.
7. The page is usable with keyboard and at narrow width; empty data states are legible.

## Operational limits

The browser runtime materializes the dataset and renders with SVG through pinned Observable Plot and D3. Use measured limits for a particular dataset; do not advertise million-row interactive performance from these small examples. The importer defaults to 100,000 rows as a protective limit, not a promised render capacity. Large-data SQL, WebGL, remote connectors, continuous streaming, geographic maps, and video encoding need explicit host adapters and separate validation.

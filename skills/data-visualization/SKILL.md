---
name: data-visualization
description: Create portable interactive data explorations, statistical plots, linked dashboards, and observed-time animations from real datasets. Use when a user wants to inspect, compare, filter, replay, or explain quantitative data. Includes multi-format import, provenance, uncertainty, reusable browser embedding, and executable validation. Use system-drawings for architecture and mechanism diagrams rather than quantitative observations.
---

# Data Visualization

Turn a question and its evidence into an explorable instrument. Author an `exploration.json`; the bundled engine provides the interface, charting, time controls, source inspection, and export. A resulting HTML file includes its renderer and data and works offline.

The sibling relationship to system-drawings includes its authoring architecture and minimalist 1970s NASA/IBM visual language: white paper, fine black rules, compact uppercase titles, monospace lettering, and plain square controls. Keep charts monochrome; distinguish categories with stable symbols, open/filled marks, line patterns, and labels. Use the shared theme in `assets/style.css`. Choose statistical encodings for data; do not force quantitative comparisons into three-dimensional solids.

## Work from the evidence

Find the decision behind the requested chart. Inspect the raw source, its observation unit, coverage, denominator, identifier, time semantics, and usage terms. Record retrieval time and a content hash. Reconcile aggregates against independent source totals when available. Separate observed data, model estimates, scenarios, and forecasts in visible text.

Use the general coding agent to query, analyze, propose comparisons, generate new views, and test hypotheses. Do not insert a simulated AI chat or a fixed natural-language command parser. The durable investment is the execution and verification surface, which improves as the model improves. [Research and architecture](references/research.md) records the alternatives, evidence, limits, and extension direction.

## Import and inspect

The examples below use `skill_directory` for this skill's installed directory and put runtime output outside the skill source.
Python 3.11+, Node.js, and `uv` are the authoring prerequisites. The generated HTML requires only a modern browser.

```sh
skill_directory="$HOME/.agents/skills/data-visualization"
uv run "$skill_directory/scripts/import_data.py" observations.csv \
  --entity region --label region --time year --x year --y value \
  --kind line --title 'How did the regions change?' \
  -o /tmp/exploration.json
```

The importer supports CSV, TSV, JSON arrays, JSONL/NDJSON, nested JSON arrays, GeoJSON properties and point coordinates, Parquet, Arrow IPC file/stream, Feather, Excel XLSX/XLS, and read-only SQLite tables. Use `--sheet`, `--table`, `--records-path`, or `--format` when needed. `--type postal_code=string` preserves identifiers. A profile beside the document reports missingness and distinct counts. Verify the inferred types; numeric-looking identifiers often need explicit overrides. Workbook formulas use stored results, so recalculate externally when cached values are absent or stale.

The importer rejects row-limit overflow rather than silently sampling. It is an import tool, not a large-data query server. Aggregate large data with DuckDB/Polars first and record the query. GeoJSON geometry is retained as data; the bundled renderer does not provide geographic projections or choropleths.

## Author the exploration

Read [the document specification](references/specification.md) and [authoring guidance](references/authoring.md). Read [DESIGN.md](DESIGN.md) before changing the engine's interface.

Every observation needs a stable entity key; an entity/time pair must be unique. Declare types and units. Preserve missing values as null. Describe confidence intervals and estimates. Views support scatterplots, lines, bars, histograms, and tables; use combinations that answer distinct questions about the same observations.

Time has an explicit mode: `snapshot` shows an observed frame; `cumulative` reveals observations through that frame. A history view can use `timeMode: "all"` for static comparison. Playback advances through actual observed values. It does not manufacture measurements between them. Keep scales and identity stable, and retain a pause/scrub/static route for people who cannot or do not want to follow motion.

Saved questions are inspectable view-state presets: a useful comparison, a selected entity, or a cohort. Ground their explanatory text in executed calculations. They are not evidence that a model analyzed the dataset at runtime.

## Validate, compile, and inspect

```sh
python3 "$skill_directory/scripts/build_exploration.py" /tmp/exploration.json --validate-only
python3 "$skill_directory/scripts/build_exploration.py" /tmp/exploration.json -o /tmp/exploration.html
open /tmp/exploration.html
```

Use the available browser to inspect the actual result at desktop and narrow widths. Check meaningful states: filtering, empty results, selected records, first/last time frames, playback pause/restart, sources, exports, and keyboard access. A compiler pass does not prove visual or statistical correctness. For engine changes, run the [test commands](references/authoring.md#verification).
The generic `scripts/inspect_exploration.cjs PAGE.html OUTPUT_DIRECTORY` captures every declared view, first frame, and mobile layout offline and verifies actual playback advancement. It requires Playwright and a browser; follow the active browser-tool instructions before choosing a local browser runner. Open and inspect the resulting PNGs as well as `audit.json`.

Deliver the page, source document, source files or retrieval recipe, transformation script, validation evidence, and material caveats. Distinguish implemented capabilities from proposed extensions. Keep generated pages, profiles, captures, and downloaded datasets outside the installed skill's version-controlled source.

## Reproduce the two reference explorations

```sh
uv run "$skill_directory/scripts/prepare_examples.py" --output /tmp/data-explorations
python3 "$skill_directory/scripts/build_exploration.py" /tmp/data-explorations/ai-horizons/exploration.json -o /tmp/data-explorations/ai-horizons/index.html
python3 "$skill_directory/scripts/build_exploration.py" /tmp/data-explorations/midterm-votes/exploration.json -o /tmp/data-explorations/midterm-votes/index.html
```

The first explores METR time-horizon estimates and uncertainty for 26 measured models. The second explores official FEC House vote compilations for five midterms and 50 states. `verification.json` records executed source-reconciliation checks. Pass `--refresh` deliberately to retrieve updated source bytes; retained hashes identify the snapshot.

For application embedding and programmatic state changes, use [the runtime API](references/runtime-api.md). Keep model credentials and privileged data access in the host environment, never inside a downloadable HTML artifact.

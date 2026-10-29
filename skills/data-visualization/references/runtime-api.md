# Browser runtime

Use the compiler for a portable HTML page. To embed the same engine, load the pinned local assets in order: `vendor/d3.min.js`, `vendor/plot.umd.min.js`, `core.js`, `runtime.js`. Supply `style.css` as text or in `<style id="data-exploration-style">`. No CDN or model service is required at runtime.

```js
const viewer = DataExploration.create(container, explorationDocument, {
  styles: stylesheetText,
  state: {view: "trend"},
  restoreURL: false,
  onStateChange(state, {action}) { /* persist or coordinate with a host */ },
  onError(error) { /* report a rendering error */ }
});
viewer.seek(2022);
viewer.setState({filters: {region: ["North"]}});
viewer.select(["entity-17"]);
const evidence = viewer.exportEvidence();
viewer.dispose();
```

Each instance owns its Shadow DOM, styles, state, timers, event listeners, and resize observer. Multiple instances can coexist. `create` rejects mounting twice in the same container. `dispose` releases the instance and allows a new mount. A page may opt into restoring `#exploration=<URI-encoded JSON state>`; embedded hosts should set `restoreURL:false` to avoid sharing one URL state across unrelated instances.

## Methods

| Method | Result |
|---|---|
| `getDocument()` | Independent JSON copy of source document |
| `getState()` / `exportState()` | Current normalized state as object / JSON text |
| `setState(patch)` | Normalize, stop playback, update linked views; returns viewer |
| `getRows()` | Copy of observations shown by the active view, including full history for `timeMode:"all"` |
| `getSummary()` | Counts reconciled to the source and active view; full-history views include `frameVisible` for the selected frame |
| `select(entityKeys)` | Highlight entities without changing the cohort denominator |
| `focusEntity(entityKey)` | Open an existing full-history line view for a repeated entity; returns false if no meaningful history exists |
| `focusCohort(field, value)` | Open a focused cohort for an observed field value, retaining the parent comparison |
| `back()` | Return from sources/data or restore the exact parent query and selection; returns whether navigation occurred |
| `seek(observedTime)` | Snap to the nearest observed time; ties choose earlier |
| `play()` / `stop()` | Step through observed frames / stop immediately |
| `setPresentation("chart"\|"data"\|"sources")` | Change representation of the exploration |
| `subscribe(callback)` | Receive state changes; returns unsubscribe function |
| `exportCSV()` | Current cohort, with field keys and missing values preserved |
| `exportSVG()` | Current chart as SVG text; null in table/empty views |
| `exportEvidence()` | Sources, caveats, transforms, cohort rows, state, counts and action history |
| `load(document, {preserveState:false})` | Validate and replace data; reset history and playback |
| `audit()` | Current row summary, chart presence, overflow and render status |
| `dispose()` | Stop playback, remove DOM and release listeners |

The UI SVG download also embeds view, state, and source metadata in an SVG `metadata` element. Export evidence is an auditable handoff to an agent; it does not call a model or claim to generate conclusions. Runtime data is rendered as text, never evaluated as code.

## Interactions

The opening surface is the drawing, a view selector, and the observed-time transport. Explore opens filters, saved questions, comparison/region tools, and exports. Selecting a mark reveals its data sheet alongside the drawing. Every mark supports Enter/Space, and the Data presentation remains a readable alternative. Previous/next observation controls permit precise inspection of dense clusters without targeting a tiny mark. Closing inspection clears its emphasis; Escape closes an open sheet, then navigates to the parent when pressed again.

Search and category filters define the cohort. Clicking a legend category isolates it; clicking further categories adds or removes them; clearing the last category returns to all. Shift-click adds or removes an entity. The Compare entities toggle permits additive selection by touch or unmodified click. Selection remains stable when an entity has no observation in the current frame, and the inspector labels that state. Clicking another historical observation of the same entity selects its exact date. Data, CSV, evidence exports, and view counts use the same active-view time semantics.

The inspector offers Open observed history when the document contains repeated observations and a line view with `timeMode:"all"` and x equal to the time field. It also offers meaningful declared categorical cohorts. Each descent stores the parent state; the return control restores its filters, time, view, and selection. Undo includes this navigation context. Evidence exports include the parent states. Shared URLs preserve the resulting query, but do not recreate the local navigation history.

Select region enables a D3 two-dimensional brush for numeric/date scatter and line axes. Dragging selects data coordinates and applies them across views. Clear region resets the brush. Changing views clears the previous coordinate region. `Undo` restores the previous query state. Saved questions apply declarative state changes and display their explanatory text.

Playback is discrete over observed frames. Snapshot marks move between their measured positions through interruptible native browser animations; cumulative marks enter at their observed positions. A short transition label identifies movement between observed dates. Full-history line views retain their history and move a faint time cursor. A change during motion starts from the current visible position. Fixed axes, identity, units, and category symbols persist. The animation does not modify data or export intermediate values. Reduced-motion users receive immediate updates with arrows and the keyboard-accessible slider; playback is not started for them. No autoplay occurs on page load. Motion duration and easing are shared tokens in `style.css`.

## Extensions and scale

`DataExploration.registerRenderer(type, renderer)` registers an explicit renderer before loading a document that uses it. It also registers the type with the JavaScript validator. Extension documents still require declared `x` and `y` fields. The renderer receives `{document, Plot, d3, rows, view, state, documentData, width, height, select}` and returns a DOM node. This is trusted application code, not executable text from an exploration document. The Python portable compiler intentionally accepts built-in types only; extensions need a host that bundles and registers its own code.

The included renderer covers scatter plots, line plots, uncertainty bars/bands, zero-baseline bars, histograms with fixed bins, and tables. It does not implement geographic projections, network layouts, video encoding, a SQL editor, or a live model endpoint. These can be supplied through renderer/host integration. Plot supports more marks than this initial document grammar; add a justified mark with validation and a meaningful specimen instead of copying a new standalone renderer.

Rows reside in memory and SVG renders visible marks. This is appropriate for the supplied 26- and 250-row studies. It is not a benchmarked million-row browser database. For larger inputs, use the ingestion layer and DuckDB/Arrow/Parquet to calculate reproducible summaries first; preserve the transformation, source hash, and denominator. A future Mosaic or worker-backed query adapter should supply the same cohort/state semantics rather than changing what filters mean. No performance claim should exceed a measured workload.

## Verification

Run `node --test tests/runtime/core.test.cjs`. DOM integration uses `tests/runtime/render.test.cjs` with the jsdom dependency described in that file. The browser test runs compiled examples in local Chrome, records screenshots and checks mark inspection, time stepping, playback, filtering, brushing, tables, sources, mobile overflow, reduced motion, and absence of network requests:

```sh
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright \
  node tests/runtime/browser.test.cjs /path/to/rendered/examples
```

Set `CHROME_PATH` for a different Chrome executable and `DATA_VISUALIZATION_TEST_OUTPUT` for screenshot/report output outside the source tree. Always inspect the screenshots; numerical and DOM tests cannot grade visual clarity.

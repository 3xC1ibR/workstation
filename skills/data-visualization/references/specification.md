# Exploration document, version 1

An exploration is data, provenance, view declarations, and optional saved questions. The runtime reads JSON; it never evaluates source strings as code.

```json
{
  "version": 1,
  "id": "example",
  "title": "A question answered with data",
  "subtitle": "One concise statement of scope.",
  "category": "Research",
  "dataset": {
    "id": "observations",
    "title": "Source dataset",
    "entityKey": "entity",
    "labelKey": "name",
    "fields": [
      {"key":"entity","label":"Entity","type":"string"},
      {"key":"name","label":"Name","type":"string"},
      {"key":"year","label":"Year","type":"number"},
      {"key":"value","label":"Measurement","type":"number","unit":"hours"},
      {"key":"group","label":"Group","type":"string"}
    ],
    "rows": [{"entity":"a","name":"Example","year":2020,"value":4,"group":"A"}],
    "sources": [{"title":"Primary source","url":"https://example.org/data","retrieved":"2026-10-28","license":"CC0","sha256":"..."}],
    "notes": ["An explicit coverage or measurement caveat."],
    "transforms": ["Describe the reproducible transformation and script."]
  },
  "time": {"field":"year","mode":"snapshot","label":"Observation year","intervalMs":900},
  "filters": [{"field":"group","label":"Group"}],
  "views": [
    {"id":"trend","title":"Measurement over time","type":"scatter","x":"year","y":"value","color":"group","yScale":"linear","description":"Each mark is one observation."},
    {"id":"groups","title":"Observations by group","type":"bar","x":"group","aggregate":"count","color":"group"}
  ],
  "questions": [{"id":"beginning","title":"What changed?","body":"Compare the first and last observed frames.","state":{"time":2020,"view":"trend"}}],
  "links": [{"label":"Another exploration","href":"../other/index.html"}]
}
```

`dataset.rows` is an array of records. Keys must be declared in `fields`; missing measurements are `null`, never a zero substitute. Field types are `number`, `date` (ISO 8601 string), `string`, or `boolean`. `entityKey` identifies an entity consistently across observed times; `labelKey` supplies a readable label. With time configured, entity plus time must be unique; without time, entity must be unique. Identity may encode a measurement condition when a source reports several conditions for one subject. Time can be numeric or date; avoid ambiguous locale dates. Runtime never infers additional observations.

Views support `scatter`, `line`, `bar`, `histogram`, `table`. `x`, `y`, `color`, `size`, `series`, `low`, `high` refer to field keys. `low` and `high` declare an uncertainty interval in the units of `y`; their statistical meaning belongs in the field description and view description. A line groups by `series`, then `color`, then the entity key. Null observations break lines. `xScale`/`yScale` accept `linear`, `log`, `sqrt`, `symlog`, `utc`, `point`. Explicit `xDomain`/`yDomain` override domains; otherwise numeric domains remain fixed over the full source rows, including while filtering and playing. Log domains require positive numbers. Nonpositive marks are excluded and reported. Bars use a zero baseline and `aggregate` (`count`, `sum`, `mean`, `median`) over `x`; aggregations other than count require `y`. A histogram bins numeric `x`. `referenceY` is an array of numbers; optional `referenceLabels` maps their string values to on-chart labels (for example `{"16":"16 h · suite limit"}`); `annotations` is an array of `{x,y,label}`. `table` uses `columns` or all declared fields. Optional `height` sets the preferred chart height. `colorDomain` and `colorRange` explicitly pin category colors.

`time.mode` is `cumulative` (all observations at or before the cursor) or `snapshot` (only that exact observed frame). A cursor always resolves to an observed value. Playback steps through observed frames without interpolating measured values; the screen communicates the current mode. A view may set `timeMode: "all"` to show the full history of the filtered cohort. The Data presentation, row exports, and counts use the active view’s time semantics, including its full history when `timeMode` is `all`. Default time is the last observation; `time.initial` may select another observed value. `intervalMs` sets wall-clock playback pacing, not a claim about elapsed data time.

Filters share one state across charts and the data table. Runtime state is `{time, mode, filters, search, selected, view, brush, speed}`. `filters` maps field keys to arrays of accepted values (empty array means no category restriction). `selected` is an array of entity keys. A `brush` is `{view,x:[min,max],y:[min,max]}` with numeric coordinates; dates use epoch milliseconds. Filters and search define the cohort; time selects observations; selection highlights a subset without silently changing denominators. An interval brush filters the cohort in the named view's axes. Questions are saved state changes, not generated AI conclusions.

The default visual grammar matches system-drawings: pure white, black ink, monospace labels, and compact uppercase sheet titles. The `color` field also determines stable category symbols and line patterns from the complete source domain. Default category fills use black, white, and gray; open bars retain a black outline. `colorRange` remains an explicit rendering override for a user-requested palette, but the reference pages and skill default are monochrome. Filtering and time never reassign category symbols.

For scatter and line points, `size` encodes a nonnegative quantitative field as circle area. Its square-root radius scale uses the full-source maximum, stays fixed across time and filters, and is unaffected by selection. Zero has zero area; missing or negative sizes do not produce a point. The size value appears in the mark tooltip. Without `size`, points use categorical symbols with a constant nominal radius and a larger selection highlight; charts without categories use circles.

All metadata is plain text. External source links must be HTTP or HTTPS. Dataset links may also be relative paths. The compiler must encode JSON `<` as `\u003c` before embedding in a script element. HTML export includes local pinned rendering libraries, stylesheet, runtime, core, and data. A complete export makes no network requests.

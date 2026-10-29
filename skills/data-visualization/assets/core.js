/* Data Exploration Core — deterministic data, state, and temporal semantics. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.DataExplorationCore = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  const FIELD_TYPES = new Set(["number", "date", "string", "boolean"]);
  const VIEW_TYPES = new Set(["scatter", "line", "bar", "histogram", "table"]);
  const EXTENSION_TYPES = new Set();
  const SCALES = new Set(["linear", "log", "sqrt", "symlog", "utc", "point"]);
  const AGGREGATES = new Set(["count", "sum", "mean", "median"]);
  const has = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const valueAt = (row, key) => has(row, key) ? row[key] : undefined;
  const record = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const missing = value => value === null || value === undefined;
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const fail = message => { throw new Error("Invalid exploration: " + message); };
  const textRequired = (value, path) => {
    if (typeof value !== "string" || !value.trim()) fail(path + " must be a nonempty string");
  };

  // Reject locale dates and impossible calendar dates instead of accepting Date.parse rollover.
  function dateNumber(value) {
    if (typeof value !== "string") return NaN;
    const match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:\d{2}))?$/.exec(value);
    if (!match) return NaN;
    const year = +match[1], month = +match[2], day = +match[3];
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (month < 1 || month > 12 || day < 1 || day > days[month - 1]) return NaN;
    if (match[4] && (+match[4] > 23 || +match[5] > 59 || +(match[6] || 0) > 59)) return NaN;
    if (match[8] && match[8] !== "Z" && (+match[8].slice(1, 3) > 23 || +match[8].slice(4, 6) > 59)) return NaN;
    return Date.parse(value);
  }

  function compatible(field, value) {
    if (missing(value)) return true;
    if (field.type === "number") return finite(value);
    if (field.type === "date") return Number.isFinite(dateNumber(value));
    return typeof value === field.type;
  }

  function fieldMap(doc) {
    return new Map(doc.dataset.fields.map(field => [field.key, field]));
  }

  function resolveField(doc, field) {
    return typeof field === "string" ? fieldMap(doc).get(field) : field;
  }

  function coordinate(field, value) {
    if (!field || missing(value)) return NaN;
    return field.type === "date" ? dateNumber(value) : finite(value) ? value : NaN;
  }

  function validateDomain(field, scale, domain, path) {
    if (!Array.isArray(domain) || !domain.length) fail(path + " must be a nonempty array");
    if (scale === "point" || (!scale && (field.type === "string" || field.type === "boolean"))) {
      if (domain.some(value => missing(value) || !compatible(field, value))) fail(path + " values must match the field type");
      return;
    }
    if (domain.length !== 2) fail(path + " must contain exactly two endpoints");
    const values = domain.map(value => field.type === "date" && finite(value) ? value : coordinate(field, value));
    if (!values.every(Number.isFinite)) fail(path + " endpoints must be finite " + (field.type === "date" ? "ISO dates or epoch milliseconds" : "numbers"));
    if (values[0] === values[1]) fail(path + " endpoints must be distinct");
    if (scale === "log" && values.some(value => value <= 0)) fail(path + " log endpoints must be positive");
    if (field.type === "date" && values.some(value => Math.abs(value) > 8640000000000000)) fail(path + " date endpoints exceed the supported date range");
  }

  function validate(doc) {
    if (!record(doc)) fail("document must be an object");
    if (doc.version !== 1) fail("version must be 1");
    textRequired(doc.id, "id");
    textRequired(doc.title, "title");
    const dataset = doc.dataset;
    if (!record(dataset)) fail("dataset must be an object");
    if (!Array.isArray(dataset.fields) || !dataset.fields.length) fail("dataset.fields must be a nonempty array");
    const fields = new Map();
    dataset.fields.forEach((field, index) => {
      const path = "dataset.fields[" + index + "]";
      if (!record(field)) fail(path + " must be an object");
      textRequired(field.key, path + ".key");
      if (fields.has(field.key)) fail("duplicate field key " + JSON.stringify(field.key));
      if (!FIELD_TYPES.has(field.type)) fail(path + ".type must be number, date, string, or boolean");
      if (field.unit !== undefined && typeof field.unit !== "string") fail(path + ".unit must be a string");
      fields.set(field.key, field);
    });
    const reference = (key, path, optional = false) => {
      if (optional && key === undefined) return;
      if (typeof key !== "string" || !fields.has(key)) fail(path + " references an undeclared field " + JSON.stringify(key));
      return fields.get(key);
    };
    reference(dataset.entityKey, "dataset.entityKey");
    reference(dataset.labelKey, "dataset.labelKey", true);
    let timeField;
    if (doc.time !== undefined) {
      if (!record(doc.time)) fail("time must be an object");
      timeField = reference(doc.time.field, "time.field");
      if (!["number", "date"].includes(timeField.type)) fail("time.field must be numeric or date");
      if (doc.time.mode !== undefined && !["snapshot", "cumulative"].includes(doc.time.mode)) fail("time.mode must be snapshot or cumulative");
      if (doc.time.intervalMs !== undefined && (!finite(doc.time.intervalMs) || doc.time.intervalMs <= 0)) fail("time.intervalMs must be positive");
      if (doc.time.initial !== undefined && !compatible(timeField, doc.time.initial)) fail("time.initial must match the time field type");
    }
    if (!Array.isArray(dataset.rows)) fail("dataset.rows must be an array");
    const identities = new Map();
    dataset.rows.forEach((row, index) => {
      const path = "dataset.rows[" + index + "]";
      if (!record(row)) fail(path + " must be an object");
      for (const key of Object.keys(row)) {
        if (!fields.has(key)) fail(path + " contains undeclared field " + JSON.stringify(key));
        if (!compatible(fields.get(key), row[key])) fail(path + "." + key + " must be " + fields.get(key).type + " or null");
      }
      const identity = valueAt(row, dataset.entityKey);
      if (missing(identity) || identity === "") fail(path + "." + dataset.entityKey + " requires a stable entity identifier");
      const times = identities.get(identity) || new Set();
      const timeValue = timeField ? coordinate(timeField, valueAt(row, timeField.key)) : null;
      if (times.has(timeValue)) fail(path + " duplicates " + (timeField ? "entity and observed time" : "entity") + " for " + JSON.stringify(identity));
      times.add(timeValue);
      identities.set(identity, times);
    });
    if (dataset.sources !== undefined) {
      if (!Array.isArray(dataset.sources)) fail("dataset.sources must be an array");
      dataset.sources.forEach((source, index) => {
        const path = "dataset.sources[" + index + "]";
        if (!record(source)) fail(path + " must be an object");
        textRequired(source.title, path + ".title");
        if (source.url === undefined) {
          if (typeof source.sha256 !== "string" || !/^[a-f0-9]{64}$/i.test(source.sha256)) fail(path + " requires an HTTP or HTTPS URL or a SHA-256 checksum for a local source");
          return;
        }
        let url;
        try { url = new URL(source.url); } catch (_) { fail(path + ".url must be an absolute HTTP or HTTPS URL"); }
        if (!["http:", "https:"].includes(url.protocol)) fail(path + ".url must use HTTP or HTTPS");
      });
    }
    if (!Array.isArray(doc.views) || !doc.views.length) fail("views must be a nonempty array");
    const viewIds = new Set();
    doc.views.forEach((view, index) => {
      const path = "views[" + index + "]";
      if (!record(view)) fail(path + " must be an object");
      textRequired(view.id, path + ".id");
      if (viewIds.has(view.id)) fail("duplicate view id " + JSON.stringify(view.id));
      viewIds.add(view.id);
      if (!VIEW_TYPES.has(view.type) && !EXTENSION_TYPES.has(view.type)) fail(path + ".type is unsupported");
      for (const key of ["x", "y", "color", "size", "series", "low", "high"]) reference(view[key], path + "." + key, true);
      if (["scatter", "line", "bar", "histogram"].includes(view.type) || EXTENSION_TYPES.has(view.type)) reference(view.x, path + ".x");
      if (["scatter", "line"].includes(view.type) || EXTENSION_TYPES.has(view.type)) reference(view.y, path + ".y");
      if (view.type === "histogram" && fields.get(view.x).type !== "number") fail(path + ".x must be numeric for a histogram");
      if (view.type === "bar") {
        const aggregate = view.aggregate || "count";
        if (!AGGREGATES.has(aggregate)) fail(path + ".aggregate must be count, sum, mean, or median");
        if (aggregate !== "count" && reference(view.y, path + ".y").type !== "number") fail(path + ".y must be numeric for aggregation");
        if (view.yScale && view.yScale !== "linear") fail(path + " bars require a linear y scale and zero baseline");
        if (view.yDomain !== undefined && (!Array.isArray(view.yDomain) || view.yDomain.length !== 2 || Math.min(...view.yDomain) > 0 || Math.max(...view.yDomain) < 0)) fail(path + ".yDomain must include zero for bars");
      }
      for (const axis of ["x", "y"]) {
        const scale = view[axis + "Scale"], field = fields.get(view[axis]);
        if (scale !== undefined && !SCALES.has(scale)) fail(path + "." + axis + "Scale is unsupported");
        if (field && scale && !["point", "utc"].includes(scale) && field.type !== "number") fail(path + "." + axis + "Scale requires a numeric field");
        if (scale === "utc" && (!field || field.type !== "date")) fail(path + "." + axis + "Scale requires a date field");
        if (view[axis + "Domain"] !== undefined) {
          const domainField = field || (view.type === "bar" && axis === "y" ? {type: "number"} : null);
          if (!domainField) fail(path + "." + axis + "Domain requires an axis field");
          validateDomain(domainField, scale, view[axis + "Domain"], path + "." + axis + "Domain");
        }
      }
      if (view.timeMode !== undefined && view.timeMode !== "all") fail(path + ".timeMode must be all when specified");
      if (view.domainScope !== undefined && !["dataset", "cohort"].includes(view.domainScope)) fail(path + ".domainScope must be dataset or cohort");
      for (const key of ["xReverse", "yReverse", "clip"]) if (view[key] !== undefined && typeof view[key] !== "boolean") fail(path + "." + key + " must be boolean");
      if (view.curve !== undefined && (view.type !== "line" || !["linear", "step-after", "step-before"].includes(view.curve))) fail(path + ".curve must be linear, step-after, or step-before on a line view");
      if (view.points !== undefined && (view.type !== "line" || !["all", "changes"].includes(view.points))) fail(path + ".points must be all or changes on a line view");
      if (view.maxGap !== undefined && (view.type !== "line" || !finite(view.maxGap) || view.maxGap <= 0 || !["number", "date"].includes(fields.get(view.x)?.type))) fail(path + ".maxGap requires a positive numeric distance on a numeric or date line axis");
      if (view.gapStyle !== undefined && (!view.maxGap || !["break", "dashed"].includes(view.gapStyle))) fail(path + ".gapStyle requires maxGap and must be break or dashed");
      if (view.detailView !== undefined && typeof view.detailView !== "string") fail(path + ".detailView must name a full-history line view");
      if (view.columns !== undefined) {
        if (!Array.isArray(view.columns)) fail(path + ".columns must be an array");
        view.columns.forEach(key => reference(key, path + ".columns"));
      }
      if ((view.low !== undefined) !== (view.high !== undefined)) fail(path + " uncertainty requires both low and high");
      if (view.low !== undefined) {
        const center = reference(view.y, path + ".y"), lower = fields.get(view.low), upper = fields.get(view.high);
        if ([center, lower, upper].some(field => field.type !== "number")) fail(path + " uncertainty fields must be numeric");
        if ([lower, upper].some(field => field.unit && center.unit && field.unit !== center.unit)) fail(path + " uncertainty units must match y units");
        dataset.rows.forEach((row, rowIndex) => {
          const low = valueAt(row, view.low), high = valueAt(row, view.high);
          if (!missing(low) && !missing(high) && low > high) fail("dataset.rows[" + rowIndex + "] uncertainty lower bound exceeds upper bound in " + view.id);
        });
      }
    });
    for (const view of doc.views) if (view.detailView !== undefined) {
      const detail = doc.views.find(candidate => candidate.id === view.detailView);
      if (!detail || detail.type !== "line" || detail.timeMode !== "all" || detail.x !== doc.time?.field) fail("detailView must reference a full-history line with x equal to the observed-time field");
    }
    if (doc.filters !== undefined) {
      if (!Array.isArray(doc.filters)) fail("filters must be an array");
      doc.filters.forEach((filter, index) => {
        if (!record(filter)) fail("filters[" + index + "] must be an object");
        reference(filter.field, "filters[" + index + "].field");
      });
    }
    return doc;
  }

  function frames(doc) {
    if (!doc.time) return [];
    const field = resolveField(doc, doc.time.field), observed = new Map();
    for (const row of doc.dataset.rows) {
      const value = coordinate(field, valueAt(row, field.key));
      if (Number.isFinite(value) && !observed.has(value)) observed.set(value, valueAt(row, field.key));
    }
    return Array.from(observed).sort((a, b) => a[0] - b[0]).map(entry => entry[1]);
  }

  function normalizeBrush(doc, brush, fields) {
    if (!record(brush)) return null;
    const view = doc.views.find(candidate => candidate.id === brush.view);
    if (!view) return null;
    const normalized = {view: view.id};
    for (const axis of ["x", "y"]) {
      if (brush[axis] === undefined) continue;
      const extent = brush[axis], field = fields.get(view[axis]);
      if (!field || !["number", "date"].includes(field.type) || !Array.isArray(extent) || extent.length !== 2 || !extent.every(finite)) return null;
      normalized[axis] = extent.slice().sort((a, b) => a - b);
    }
    return normalized.x || normalized.y ? normalized : null;
  }

  function normalizeState(doc, state = {}) {
    if (!record(state)) state = {};
    const fields = fieldMap(doc), availableFrames = frames(doc), filters = Object.create(null);
    if (record(state.filters)) {
      for (const key of Object.keys(state.filters)) {
        const field = fields.get(key), values = state.filters[key];
        if (field && Array.isArray(values)) filters[key] = Array.from(new Set(values.filter(value => value !== undefined && compatible(field, value))));
      }
    }
    let time = availableFrames.length ? availableFrames[availableFrames.length - 1] : null;
    if (availableFrames.length) {
      const field = fields.get(doc.time.field);
      const requested = coordinate(field, state.time === undefined ? doc.time.initial : state.time);
      if (Number.isFinite(requested)) {
        let distance = Infinity;
        for (const frame of availableFrames) {
          const current = Math.abs(coordinate(field, frame) - requested);
          if (current < distance) { distance = current; time = frame; }
        }
      }
    }
    const entityIds = new Set(doc.dataset.rows.map(row => valueAt(row, doc.dataset.entityKey)));
    return {
      time,
      mode: ["snapshot", "cumulative"].includes(state.mode) ? state.mode : (doc.time && doc.time.mode) || "snapshot",
      filters,
      search: typeof state.search === "string" ? state.search : "",
      selected: Array.isArray(state.selected) ? Array.from(new Set(state.selected.filter(value => entityIds.has(value)))) : [],
      view: doc.views.some(view => view.id === state.view) ? state.view : doc.views[0].id,
      brush: normalizeBrush(doc, state.brush, fields),
      speed: finite(state.speed) && state.speed > 0 ? Math.max(0.1, Math.min(16, state.speed)) : 1
    };
  }

  function createState(doc, initial = {}) {
    validate(doc);
    return normalizeState(doc, initial);
  }

  function filterRows(doc, state, options) {
    const fields = fieldMap(doc), timeField = doc.time && fields.get(doc.time.field);
    const cursor = timeField ? coordinate(timeField, state.time) : NaN;
    const search = state.search.trim().toLocaleLowerCase();
    const restrictions = Object.entries(state.filters).filter(entry => entry[1].length).map(([key, values]) => [key, new Set(values)]);
    const brushView = state.brush && doc.views.find(view => view.id === state.brush.view);
    return doc.dataset.rows.filter(row => {
      if (restrictions.some(([key, values]) => !values.has(missing(valueAt(row, key)) ? null : valueAt(row, key)))) return false;
      if (search && !doc.dataset.fields.some(field => !missing(valueAt(row, field.key)) && String(valueAt(row, field.key)).toLocaleLowerCase().includes(search))) return false;
      if (!options.ignoreTime && timeField) {
        const observed = coordinate(timeField, valueAt(row, timeField.key));
        if (!Number.isFinite(observed) || (state.mode === "cumulative" ? observed > cursor : observed !== cursor)) return false;
      }
      if (!options.ignoreBrush && brushView) {
        for (const axis of ["x", "y"]) {
          const extent = state.brush[axis];
          if (!extent) continue;
          const value = coordinate(fields.get(brushView[axis]), valueAt(row, brushView[axis]));
          if (!Number.isFinite(value) || value < extent[0] || value > extent[1]) return false;
        }
      }
      return true;
    });
  }

  function cohortRows(doc, state, {ignoreTime = false, ignoreBrush = false} = {}) {
    return filterRows(doc, normalizeState(doc, state), {ignoreTime, ignoreBrush});
  }

  function selectedRows(doc, state) {
    const normalized = normalizeState(doc, state), selected = new Set(normalized.selected);
    return filterRows(doc, normalized, {}).filter(row => selected.has(valueAt(row, doc.dataset.entityKey)));
  }

  function summarize(doc, state) {
    const normalized = normalizeState(doc, state), visibleRows = filterRows(doc, normalized, {});
    const cohort = filterRows(doc, normalized, {ignoreTime: true}), selected = new Set(normalized.selected);
    const missingByField = Object.create(null);
    let missingCount = 0;
    for (const field of doc.dataset.fields) {
      const count = visibleRows.reduce((total, row) => total + (missing(valueAt(row, field.key)) ? 1 : 0), 0);
      missingByField[field.key] = count;
      missingCount += count;
    }
    const availableFrames = frames(doc);
    return {
      total: doc.dataset.rows.length,
      cohort: cohort.length,
      visible: visibleRows.length,
      selected: visibleRows.filter(row => selected.has(valueAt(row, doc.dataset.entityKey))).length,
      entities: new Set(visibleRows.map(row => valueAt(row, doc.dataset.entityKey))).size,
      selectedEntities: normalized.selected.length,
      time: normalized.time,
      mode: normalized.mode,
      missing: missingCount,
      missingByField,
      excludedByTime: cohort.length - visibleRows.length,
      excludedByCohort: doc.dataset.rows.length - cohort.length,
      frames: availableFrames.length,
      frameIndex: availableFrames.indexOf(normalized.time)
    };
  }

  function expandDomain(value, scale, date) {
    if (date) return [Math.max(-8640000000000000, value - 43200000), Math.min(8640000000000000, value + 43200000)];
    if (scale === "log") return [value / 10 > 0 ? value / 10 : value, Number.isFinite(value * 10) ? value * 10 : value];
    const amount = Math.max(Math.abs(value) * 0.05, Number.MIN_VALUE);
    if (value === 0) return [-1, 1];
    return [Number.isFinite(value - amount) ? value - amount : value, Number.isFinite(value + amount) ? value + amount : value];
  }

  function stableDomain(doc, field, scale, explicitDomain) {
    field = resolveField(doc, field);
    if (!field) throw new Error("Cannot compute domain for an undeclared field");
    const date = field.type === "date";
    const categorical = scale === "point" || (scale === undefined && ["string", "boolean"].includes(field.type));
    if (explicitDomain !== undefined) {
      validateDomain(field, scale, explicitDomain, "explicit domain for " + field.key);
      return categorical ? explicitDomain.slice() : explicitDomain.map(value => date ? new Date(finite(value) ? value : dateNumber(value)) : value);
    }
    if (categorical) {
      const values = Array.from(new Set(doc.dataset.rows.map(row => valueAt(row, field.key)).filter(value => !missing(value))));
      return values.sort((a, b) => typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b)));
    }
    let minimum = Infinity, maximum = -Infinity;
    for (const row of doc.dataset.rows) {
      const value = coordinate(field, valueAt(row, field.key));
      if (!Number.isFinite(value) || (scale === "log" && value <= 0)) continue;
      minimum = Math.min(minimum, value);
      maximum = Math.max(maximum, value);
    }
    let domain = minimum === Infinity ? (date ? [0, 86400000] : scale === "log" ? [1, 10] : [0, 1]) : minimum === maximum ? expandDomain(minimum, scale, date) : [minimum, maximum];
    return date ? domain.map(value => new Date(value)) : domain;
  }

  function formatValue(field, value) {
    if (missing(value)) return "Not observed";
    if (field && field.type === "date") return Number.isFinite(dateNumber(value)) ? value : "Not observed";
    if (field && field.type === "number") {
      if (!finite(value)) return "Not observed";
      const magnitude = Math.abs(value);
      const formatted = magnitude !== 0 && (magnitude < 0.001 || magnitude >= 1e12)
        ? value.toExponential(3).replace(/\.0+(?=e)/, "")
        : new Intl.NumberFormat("en-US", {maximumSignificantDigits: 6}).format(value);
      return field.unit ? formatted + " " + field.unit : formatted;
    }
    if (typeof value === "boolean") return value ? "Yes" : "No";
    return String(value);
  }

  // Geometry is derived from source records, never synthetic observations.
  // Null measurements always break a line; long intervals may get a dashed guide.
  function lineGeometry(doc, view, rows, cursor = null) {
    const fields = fieldMap(doc), series = view.series || view.color || doc.dataset.entityKey;
    const groups = new Map(), segments = [], points = new Set();
    const ordinal = new Map([...new Set(doc.dataset.rows.map(row => row[view.x]).filter(value => value != null))].map((value, index) => [value, index]));
    const numericX = ["number", "date"].includes(fields.get(view.x)?.type);
    const numericY = ["number", "date"].includes(fields.get(view.y)?.type);
    const x = row => numericX ? coordinate(fields.get(view.x), row[view.x]) : ordinal.get(row[view.x]);
    const y = row => numericY ? coordinate(fields.get(view.y), row[view.y]) : row[view.y];
    const valid = row => row[view.y] != null && (!numericY || Number.isFinite(y(row))) && (view.yScale !== "log" || y(row) > 0);
    for (const row of rows) if (Number.isFinite(x(row)) && (view.xScale !== "log" || x(row) > 0)) {
      const key = row[series]; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(row);
    }
    for (const entries of groups.values()) {
      entries.sort((a, b) => x(a) - x(b));
      let run = [], previous = null;
      const finish = () => {
        if (!run.length) return;
        if (run.length > 1) segments.push({rows: run, gap: false});
        points.add(run[0]); points.add(run.at(-1)); run = [];
      };
      for (const row of entries) {
        if (!valid(row)) { finish(); previous = null; continue; }
        if (previous && view.maxGap && x(row) - x(previous) > view.maxGap) {
          finish();
          if (view.gapStyle === "dashed") segments.push({rows: [previous, row], gap: true});
        }
        if (view.points !== "changes" || !previous || y(row) !== y(previous)) {
          points.add(row); if (previous) points.add(previous);
        }
        if (doc.time && coordinate(fields.get(doc.time.field), row[doc.time.field]) === coordinate(fields.get(doc.time.field), cursor)) points.add(row);
        run.push(row); previous = row;
      }
      finish();
    }
    return {segments, points: [...points]};
  }

  function serializeState(doc, state) { return JSON.stringify(normalizeState(doc, state)); }
  function deserializeState(doc, value) {
    if (typeof value !== "string") throw new TypeError("Saved exploration state must be a JSON string");
    return normalizeState(doc, JSON.parse(value));
  }

  function registerViewType(type) {
    if (typeof type !== "string" || !/^[a-z][a-z0-9_-]*$/.test(type)) throw new TypeError("A view type must start with a lowercase letter and contain only lowercase letters, digits, underscores, or hyphens");
    if (!VIEW_TYPES.has(type)) EXTENSION_TYPES.add(type);
    return type;
  }

  function isViewTypeRegistered(type) { return VIEW_TYPES.has(type) || EXTENSION_TYPES.has(type); }

  return Object.freeze({validate, fieldMap, fields: fieldMap, frames, createState, normalizeState,
    cohortRows, selectedRows, summarize, stableDomain, formatValue, serializeState, deserializeState,
    registerViewType, isViewTypeRegistered, lineGeometry});
});

"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const Core = require("../../assets/core.js");

function fixture() {
  return {
    version: 1, id: "observed-series", title: "Observed measurement series",
    dataset: {
      id: "measurements", title: "Measurements", entityKey: "entity", labelKey: "name",
      fields: [
        {key: "entity", type: "string"}, {key: "name", type: "string"},
        {key: "year", type: "number"}, {key: "value", type: "number", unit: "hours"},
        {key: "group", type: "string"}, {key: "verified", type: "boolean"}
      ],
      rows: [
        {entity: "a", name: "Alpha", year: 2024, value: 0, group: "Research", verified: true},
        {entity: "b", name: "Beta", year: 2020, value: null, group: "Production", verified: false},
        {entity: "a", name: "Alpha", year: 2020, value: 2, group: "Research", verified: true},
        {entity: "c", name: "Gamma", year: 2028, value: 8, group: "Production", verified: true},
        {entity: "b", name: "Beta", year: 2024, value: -2, group: "Production", verified: false}
      ],
      sources: [{title: "Synthetic test observations", url: "https://example.org/measurements"}]
    },
    time: {field: "year", mode: "snapshot"},
    filters: [{field: "group"}],
    views: [
      {id: "measurements", type: "scatter", x: "year", y: "value"},
      {id: "groups", type: "bar", x: "group", aggregate: "count"},
      {id: "table", type: "table", columns: ["entity", "value"]}
    ]
  };
}

function datedFixture() {
  const doc = fixture();
  doc.dataset.fields.find(field => field.key === "year").type = "date";
  const dates = new Map([[2020, "2020-01-01"], [2024, "2024-01-01"], [2028, "2028-01-01"]]);
  doc.dataset.rows.forEach(row => { row.year = dates.get(row.year); });
  doc.views[0].xScale = "utc";
  return doc;
}

test("observed frames sort without filling gaps; a cursor snaps to a measured frame", () => {
  const doc = fixture();
  assert.deepEqual(Core.frames(doc), [2020, 2024, 2028]);
  assert.equal(Core.createState(doc).time, 2028);
  assert.equal(Core.createState(doc, {time: 2022}).time, 2020);
  assert.equal(Core.createState(doc, {time: 2023}).time, 2024);
  assert.equal(Core.createState(doc, {time: -100}).time, 2020);
  assert.equal(Core.createState(doc, {time: 9999}).time, 2028);
  doc.time.initial = 2024;
  assert.equal(Core.createState(doc).time, 2024);
});

test("snapshot and cumulative counts reconcile against the raw observations", () => {
  const doc = fixture();
  const snapshot = Core.createState(doc, {time: 2024});
  const cumulative = Core.normalizeState(doc, {...snapshot, mode: "cumulative"});
  assert.deepEqual(Core.cohortRows(doc, snapshot).map(row => row.value), [0, -2]);
  assert.equal(Core.cohortRows(doc, cumulative).length, 4);
  assert.equal(Core.cohortRows(doc, snapshot, {ignoreTime: true}).length, 5);
  for (const frame of Core.frames(doc)) {
    const current = Core.normalizeState(doc, {...snapshot, time: frame, mode: "cumulative"});
    assert.deepEqual(Core.cohortRows(doc, current), doc.dataset.rows.filter(row => row.year <= frame));
  }
});

test("selection survives absent frames and does not change cohort denominators", () => {
  const doc = fixture();
  const state = Core.createState(doc, {time: 2028, selected: ["a", "a", "unknown"]});
  assert.deepEqual(state.selected, ["a"]);
  assert.equal(Core.cohortRows(doc, state).length, 1);
  assert.deepEqual(Core.selectedRows(doc, state), []);
  const earlier = Core.normalizeState(doc, {...state, time: 2024});
  assert.deepEqual(Core.selectedRows(doc, earlier).map(row => row.entity), ["a"]);
  assert.equal(Core.cohortRows(doc, earlier).length, 2);
  assert.equal(Core.summarize(doc, state).selectedEntities, 1);
  assert.equal(Core.summarize(doc, state).selected, 0);
});

test("shared categorical filters, case-insensitive search, and time compose", () => {
  const doc = fixture();
  const state = Core.createState(doc, {mode: "cumulative", filters: {group: ["Production"], verified: [false]}});
  assert.deepEqual(Core.cohortRows(doc, state).map(row => row.entity), ["b", "b"]);
  assert.deepEqual(Core.cohortRows(doc, {...state, search: "  BETA  "}).map(row => row.entity), ["b", "b"]);
  assert.deepEqual(Core.cohortRows(doc, {...state, search: "alpha"}), []);
  assert.equal(Core.cohortRows(doc, {...state, filters: {group: []}}).length, 5);
  assert.equal(Core.cohortRows(doc, {...state, filters: {group: ["Absent category"]}}).length, 0);
  assert.equal(Core.cohortRows(doc, {...state, filters: {value: [null]}}).length, 1);
  assert.equal(Core.cohortRows(doc, {...state, filters: {value: [0]}}).length, 1);
});

test("numeric brushing uses declared axes, excludes missing values, and is reversible", () => {
  const doc = fixture();
  const state = Core.createState(doc, {mode: "cumulative", brush: {view: "measurements", x: [2028, 2020], y: [0, 2]}});
  assert.deepEqual(state.brush.x, [2020, 2028]);
  assert.deepEqual(Core.cohortRows(doc, state).map(row => row.value), [0, 2]);
  assert.equal(Core.cohortRows(doc, state, {ignoreBrush: true}).length, 5);
  assert.equal(Core.normalizeState(doc, {...state, brush: {view: "groups", x: [0, 2]}}).brush, null);
  assert.equal(Core.normalizeState(doc, {...state, brush: {view: "measurements", x: [NaN, 2]}}).brush, null);
});

test("ISO dates use exact observed instants for playback and epoch coordinates for brush", () => {
  const doc = datedFixture();
  const state = Core.createState(doc, {
    time: "2025-01-01", mode: "cumulative",
    brush: {view: "measurements", x: [Date.parse("2023-01-01"), Date.parse("2025-01-01")]}
  });
  assert.equal(state.time, "2024-01-01");
  assert.deepEqual(Core.cohortRows(doc, state).map(row => row.year), ["2024-01-01", "2024-01-01"]);
  const domain = Core.stableDomain(doc, "year", "utc");
  assert.deepEqual(domain.map(value => value.toISOString()), ["2020-01-01T00:00:00.000Z", "2028-01-01T00:00:00.000Z"]);
});

test("equivalent date representations collapse frames and duplicate entity-time is rejected", () => {
  const doc = datedFixture();
  doc.dataset.rows[2].year = "2019-12-31T19:00:00-05:00";
  assert.equal(Core.frames(doc).length, 3);
  assert.equal(Core.cohortRows(doc, {time: "2020-01-01"}).length, 2);
  doc.dataset.rows.push({...doc.dataset.rows[2], year: "2020-01-01T00:00:00Z"});
  assert.throws(() => Core.validate(doc), /duplicates entity and observed time/);
});

test("missing measurements never enter domains, searches, or brushes as zero", () => {
  const doc = fixture();
  doc.dataset.rows.forEach(row => { row.value = null; });
  assert.deepEqual(Core.stableDomain(doc, "value", "linear"), [0, 1]);
  assert.deepEqual(Core.stableDomain(doc, "value", "log"), [1, 10]);
  assert.equal(Core.cohortRows(doc, {mode: "cumulative", brush: {view: "measurements", y: [0, 0]}}).length, 0);
  assert.equal(Core.cohortRows(doc, {mode: "cumulative", search: "null"}).length, 0);
  assert.equal(Core.formatValue({type: "number", unit: "hours"}, null), "Not observed");
  assert.equal(Core.formatValue({type: "number", unit: "hours"}, 0), "0 hours");
});

test("domains use the complete source and log domains exclude nonpositive measurements", () => {
  const doc = fixture();
  const original = JSON.stringify(doc);
  assert.deepEqual(Core.stableDomain(doc, "value", "linear"), [-2, 8]);
  Core.cohortRows(doc, {time: 2020, filters: {group: ["Research"]}});
  assert.deepEqual(Core.stableDomain(doc, "value", "linear"), [-2, 8]);
  assert.deepEqual(Core.stableDomain(doc, "value", "log"), [2, 8]);
  assert.deepEqual(Core.stableDomain(doc, "value", "linear", [0, 100]), [0, 100]);
  assert.throws(() => Core.stableDomain(doc, "value", "log", [0, 100]), /positive/);
  assert.equal(JSON.stringify(doc), original);
});

test("empty and singleton domains remain finite, nondegenerate, and positive for log", () => {
  const doc = fixture();
  for (const value of [0, 1, -1, Number.MAX_VALUE, -Number.MAX_VALUE, Number.MIN_VALUE]) {
    doc.dataset.rows = [{entity: "a", value}];
    const domain = Core.stableDomain(doc, "value", "linear");
    assert.ok(domain.every(Number.isFinite));
    assert.ok(domain[0] < domain[1]);
    assert.ok(domain[0] <= value && domain[1] >= value);
    const logDomain = Core.stableDomain(doc, "value", "log");
    assert.ok(logDomain.every(number => Number.isFinite(number) && number > 0));
    assert.ok(logDomain[0] < logDomain[1]);
  }
  doc.dataset.rows = [];
  assert.equal(Core.createState(doc).time, null);
  assert.deepEqual(Core.cohortRows(doc, Core.createState(doc)), []);
});

test("summary reconciles cohort, time, selection, and missing counts", () => {
  const doc = fixture();
  const state = Core.createState(doc, {time: 2020, filters: {group: ["Production"]}, selected: ["b"]});
  const summary = Core.summarize(doc, state);
  assert.equal(summary.total, 5);
  assert.equal(summary.cohort, 3);
  assert.equal(summary.visible, 1);
  assert.equal(summary.selected, 1);
  assert.equal(summary.missing, 1);
  assert.equal(summary.missingByField.value, 1);
  assert.equal(summary.total, summary.excludedByCohort + summary.excludedByTime + summary.visible);
  assert.equal(summary.frames, 3);
  assert.equal(summary.frameIndex, 0);
});

test("state survives JSON persistence and normalization without mutating caller input", () => {
  const doc = fixture();
  const initial = {time: 2024, mode: "cumulative", selected: ["a"], filters: {group: ["Research", "Research"]}, search: "a", view: "table", speed: 2, brush: {view: "measurements", y: [0, 9]}};
  const original = JSON.stringify(initial);
  const state = Core.createState(doc, initial);
  assert.deepEqual(Core.deserializeState(doc, Core.serializeState(doc, state)), state);
  assert.equal(JSON.stringify(initial), original);
  assert.equal(Core.normalizeState(doc, {speed: Infinity, view: "absent", mode: "interpolated"}).speed, 1);
  assert.equal(Core.normalizeState(doc, {speed: 0.001}).speed, 0.1);
  assert.equal(Core.normalizeState(doc, {speed: 100}).speed, 16);
  assert.throws(() => Core.deserializeState(doc, "not JSON"), SyntaxError);
});

test("schema validation rejects coercion, nonfinite data, missing identities, and undeclared fields", () => {
  for (const value of ["4", Infinity, NaN, {}, true]) {
    const doc = fixture();
    doc.dataset.rows[0].value = value;
    assert.throws(() => Core.validate(doc), /value must be number or null/);
  }
  let doc = fixture();
  delete doc.dataset.rows[0].entity;
  assert.throws(() => Core.validate(doc), /stable entity identifier/);
  doc = fixture();
  doc.dataset.rows[0].unexpected = 1;
  assert.throws(() => Core.validate(doc), /undeclared field/);
  doc = fixture();
  doc.views[0].x = "absent";
  assert.throws(() => Core.validate(doc), /undeclared field/);
  doc = fixture();
  doc.dataset.fields.push({...doc.dataset.fields[0]});
  assert.throws(() => Core.validate(doc), /duplicate field/);
  doc = fixture();
  doc.dataset.rows.push({...doc.dataset.rows[0]});
  assert.throws(() => Core.validate(doc), /duplicates entity and observed time/);
  delete doc.time;
  assert.throws(() => Core.validate(doc), /duplicates entity/);
});

test("date validation rejects ambiguous, impossible, and timezone-free timestamps", () => {
  for (const invalid of ["10/28/2026", "2026-02-30", "2026-13-01", "2026-01-01T00:00:00", "2026-01-01T25:00:00Z"]) {
    const doc = datedFixture();
    doc.dataset.rows[0].year = invalid;
    assert.throws(() => Core.validate(doc), /year must be date or null/);
  }
  const doc = datedFixture();
  doc.dataset.rows[0].year = "2024-02-29";
  assert.equal(Core.validate(doc), doc);
});

test("source links cannot execute script, and bars retain a zero baseline", () => {
  for (const url of ["javascript:alert(1)", "data:text/html,test", "//example.org/data", "/data.csv"]) {
    const doc = fixture();
    doc.dataset.sources[0].url = url;
    assert.throws(() => Core.validate(doc), /HTTP or HTTPS/);
  }
  const doc = fixture();
  doc.views[1].yDomain = [2, 10];
  assert.throws(() => Core.validate(doc), /include zero/);
  doc.views[1].yDomain = [0, 10];
  assert.equal(Core.validate(doc), doc);
  doc.views[1].yScale = "log";
  assert.throws(() => Core.validate(doc), /zero baseline/);
});

test("uncertainty intervals validate references, units, and bound order", () => {
  const doc = fixture();
  doc.dataset.fields.push({key: "lower", type: "number", unit: "hours"}, {key: "upper", type: "number", unit: "hours"});
  doc.views[0].low = "lower";
  doc.views[0].high = "upper";
  doc.dataset.rows[0].lower = -1;
  doc.dataset.rows[0].upper = 1;
  assert.equal(Core.validate(doc), doc);
  doc.dataset.rows[0].lower = 2;
  assert.throws(() => Core.validate(doc), /lower bound exceeds upper/);
  doc.dataset.rows[0].lower = -1;
  doc.dataset.fields.at(-1).unit = "seconds";
  assert.throws(() => Core.validate(doc), /units must match/);
});

test("prototype-shaped field names and entity values remain inert own data", () => {
  const doc = fixture();
  doc.dataset.fields.push({key: "__proto__", type: "string"}, {key: "constructor", type: "string"});
  doc.dataset.rows.forEach((row, index) => {
    Object.defineProperty(row, "__proto__", {value: index === 0 ? "accepted" : "other", enumerable: true});
    row.constructor = "ordinary data";
  });
  const initial = JSON.parse('{"filters":{"__proto__":["accepted"],"constructor":["ordinary data"]},"mode":"cumulative"}');
  const state = Core.createState(doc, initial);
  assert.equal(Object.getPrototypeOf(state.filters), null);
  assert.equal(Core.fieldMap(doc).get("__proto__").type, "string");
  assert.equal(Core.cohortRows(doc, state).length, 1);
  assert.deepEqual(Core.deserializeState(doc, Core.serializeState(doc, state)), state);
  assert.equal({}.accepted, undefined);
});

test("standalone browser script exposes the same API without a DOM or module loader", () => {
  const context = vm.createContext({URL, Intl});
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../../assets/core.js"), "utf8"), context);
  assert.deepEqual(Object.keys(context.DataExplorationCore), Object.keys(Core));
  assert.equal(context.DataExplorationCore.createState(fixture()).time, 2028);
});

test("absent prototype-shaped columns are missing, not inherited object properties", () => {
  const doc = fixture();
  doc.dataset.fields.push({key: "constructor", type: "string"}, {key: "__proto__", type: "string"});
  const state = Core.createState(doc, {mode: "cumulative", filters: {constructor: [null]}});
  assert.equal(Core.cohortRows(doc, state).length, 5);
  assert.equal(Core.summarize(doc, state).missingByField.constructor, 5);
  assert.deepEqual(Core.stableDomain(doc, "__proto__", "point"), []);
  assert.equal(Core.cohortRows(doc, {...state, search: "function Object"}).length, 0);
});

test("custom view types require explicit registration and declared x/y fields", () => {
  const doc = fixture();
  doc.views[0].type = "residual-plot";
  assert.equal(Core.isViewTypeRegistered("residual-plot"), false);
  assert.throws(() => Core.validate(doc), /type is unsupported/);
  assert.equal(Core.registerViewType("residual-plot"), "residual-plot");
  assert.equal(Core.isViewTypeRegistered("residual-plot"), true);
  assert.equal(Core.validate(doc), doc);
  delete doc.views[0].y;
  assert.throws(() => Core.validate(doc), /y references an undeclared field/);
  assert.throws(() => Core.registerViewType("<script>"), /view type must/);
});

test("local source provenance uses a title and SHA-256 checksum without inventing a URL", () => {
  const doc = fixture();
  doc.dataset.sources = [{title: "measurements.csv", sha256: "a".repeat(64), retrieved: "2026-10-28", license: "User supplied"}];
  assert.equal(Core.validate(doc), doc);
  delete doc.dataset.sources[0].sha256;
  assert.throws(() => Core.validate(doc), /SHA-256 checksum/);
  doc.dataset.sources[0].sha256 = "a".repeat(64);
  doc.dataset.sources[0].url = "javascript:alert(1)";
  assert.throws(() => Core.validate(doc), /HTTP or HTTPS/);
});

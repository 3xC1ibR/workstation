"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
let jsdom;
try { jsdom = require("jsdom"); } catch (_) {
  jsdom = require(path.join(process.env.DATA_OBSERVATORY_VALIDATION_ROOT || "/tmp/data-observatory-validation", "node_modules/jsdom"));
}
const {JSDOM, VirtualConsole, ResourceLoader} = jsdom;
const assetDirectory = path.resolve(__dirname, "../../assets");
const source = Object.fromEntries(["vendor/d3.min.js", "vendor/plot.umd.min.js", "core.js", "runtime.js", "style.css"].map(file => [file, fs.readFileSync(path.join(assetDirectory, file), "utf8")]));
const plain = value => JSON.parse(JSON.stringify(value));

function fixture() {
  return {
    version: 1, id: "runtime-validation", title: "Observed measurements",
    subtitle: "Synthetic observations for behavioral verification.",
    dataset: {
      id: "measurements", title: "Synthetic measurements", entityKey: "entity", labelKey: "name",
      fields: [
        {key: "entity", label: "Entity", type: "string"},
        {key: "name", label: "Name", type: "string"},
        {key: "year", label: "Observation year", type: "number"},
        {key: "value", label: "Measured duration", type: "number", unit: "hours"},
        {key: "group", label: "Group", type: "string"}
      ],
      rows: [
        {entity: "a", name: "Alpha", year: 2020, value: 2, group: "Research"},
        {entity: "b", name: "Beta", year: 2020, value: 3, group: "Production"},
        {entity: "a", name: "Alpha", year: 2024, value: 4, group: "Research"},
        {entity: "b", name: "Beta", year: 2024, value: null, group: "Production"},
        {entity: "a", name: "Alpha", year: 2028, value: 8, group: "Research"},
        {entity: "b", name: "Beta", year: 2028, value: 9, group: "Production"}
      ],
      sources: [{title: "Synthetic test observations", url: "https://example.test/measurements", license: "CC0", retrieved: "2026-10-28"}],
      notes: ["Measurements are synthetic and used only for runtime verification."],
      transforms: ["No transformations."]
    },
    time: {field: "year", mode: "snapshot", intervalMs: 100},
    filters: [{field: "group", label: "Group"}],
    views: [
      {id: "scatter", title: "Individual observations", type: "scatter", x: "year", y: "value", color: "group"},
      {id: "line", title: "Observed history", type: "line", x: "year", y: "value", series: "entity", color: "group", timeMode: "all"},
      {id: "bar", title: "Duration by group", type: "bar", x: "group", y: "value", aggregate: "sum", color: "group"},
      {id: "histogram", title: "Duration distribution", type: "histogram", x: "value"},
      {id: "table", title: "Observation records", type: "table", columns: ["name", "year", "value"]}
    ],
    questions: [{id: "earliest", title: "Start with the first observation", body: "Inspect the beginning of the measured series.", state: {time: 2020, view: "scatter"}}]
  };
}

function environment(t, {reducedMotion = false, recordAnimations = false} = {}) {
  const errors = [], requests = [], timers = new Map(), observers = new Set(), mediaListeners = new Set();
  const recordedAnimations = [];
  let timerId = 0;
  class Resources extends ResourceLoader {
    fetch(url) { requests.push(url); return Promise.resolve(Buffer.from("")); }
  }
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", error => errors.push(error));
  const dom = new JSDOM("<!doctype html><html><body><div id='first'></div><div id='second'></div></body></html>", {
    runScripts: "dangerously", pretendToBeVisual: true, url: "https://example.test/exploration/", virtualConsole, resources: new Resources()
  });
  const window = dom.window;
  if (recordAnimations) window.Element.prototype.animate = function (keyframes, options) {
    const animation = {element: this, keyframes, options, cancelled: false, cancel() { this.cancelled = true; }};
    recordedAnimations.push(animation);
    return animation;
  };
  window.ResizeObserver = class {
    constructor(callback) { this.callback = callback; observers.add(this); }
    observe() {}
    disconnect() { observers.delete(this); }
  };
  window.matchMedia = query => ({
    media: query, matches: reducedMotion,
    addEventListener(type, callback) { mediaListeners.add(callback); },
    removeEventListener(type, callback) { mediaListeners.delete(callback); }
  });
  window.setInterval = (callback, interval) => {
    const id = ++timerId;
    timers.set(id, {callback, interval});
    return id;
  };
  window.clearInterval = id => timers.delete(id);
  window.URL.createObjectURL = () => "blob:runtime-validation";
  window.URL.revokeObjectURL = () => {};
  window.HTMLElement.prototype.scrollIntoView = function () {};
  Object.defineProperty(window.HTMLElement.prototype, "clientWidth", {configurable: true, get() { return 1200; }});
  Object.defineProperty(window.HTMLElement.prototype, "scrollWidth", {configurable: true, get() { return 1200; }});
  Object.defineProperty(window.HTMLElement.prototype, "offsetWidth", {configurable: true, get() { return 1200; }});
  window.Element.prototype.getBoundingClientRect = function () { return new window.DOMRect(0, 0, 1200, 500); };
  for (const file of ["vendor/d3.min.js", "vendor/plot.umd.min.js", "core.js", "runtime.js"]) window.eval(source[file]);
  t.after(() => window.close());
  const create = (doc = fixture(), options = {}, id = "first") => window.DataExploration.create(window.document.getElementById(id), doc, {styles: source["style.css"], restoreURL: false, ...options});
  return {
    window, errors, requests, timers, observers, mediaListeners, recordedAnimations, create,
    tick() { for (const [id, timer] of [...timers]) if (timers.has(id)) timer.callback(); }
  };
}

function shadow(instance) { return instance.element.shadowRoot; }
function button(instance, text) {
  const control = [...shadow(instance).querySelectorAll("button")].find(element => element.textContent.trim() === text || element.getAttribute("aria-label") === text);
  assert.ok(control, "Expected a button labeled " + text);
  return control;
}
function chart(instance) {
  assert.equal(instance.audit().errors, 0, shadow(instance).textContent);
  const svg = shadow(instance).querySelector(".plot svg");
  assert.ok(svg, "The chart must expose an SVG, not just a successful audit");
  assert.ok(Number(svg.getAttribute("width")) > 300, "The chart should use its available width");
  return svg;
}
function marks(svg, label) { return svg.querySelectorAll('g[aria-label="' + label + '"] circle, g[aria-label="' + label + '"] rect, g[aria-label="' + label + '"] path'); }
function position(mark) {
  if (mark.hasAttribute("cx")) return {x: +mark.getAttribute("cx"), y: +mark.getAttribute("cy")};
  const match = mark.getAttribute("transform").match(/translate\(([-.\d]+)[, ]+([-.\d]+)\)/);
  assert.ok(match, "Symbol must have an observed position");
  return {x: +match[1], y: +match[2]};
}

test("scatter renders observations with and without optional color or injected styles", t => {
  const env = environment(t), doc = fixture();
  const instance = env.create(doc);
  assert.equal(marks(chart(instance), "dot").length, 2);
  assert.ok(shadow(instance).querySelector("style").textContent.length > 100);
  instance.dispose();
  delete doc.views[0].color;
  const fallback = env.create(doc, {styles: ""});
  assert.equal(marks(chart(fallback), "dot").length, 2);
  assert.ok([...marks(chart(fallback), "dot")].every(mark => +mark.getAttribute("r") === 3.5), "Unscaled observation circles retain their declared pixel radius");
  assert.deepEqual(env.errors, []);
});

test("line renders full history and preserves a measured null as a gap", t => {
  const env = environment(t), instance = env.create();
  instance.setState({view: "line"});
  const paths = [...marks(chart(instance), "line")];
  assert.equal(paths.length, 1, "Only Alpha has adjacent measured observations; Beta’s isolated points must not be joined");
  assert.equal(marks(chart(instance), "dot").length, 5, "All measured points remain visible on both sides of the missing value");
  assert.deepEqual(env.errors, []);
});

test("monochrome categories retain distinct symbols across time and filtering, and open bars retain outlines", t => {
  const env = environment(t), instance = env.create();
  const shapes = () => [...marks(chart(instance), "dot")].map(mark => mark.getAttribute("d"));
  const initial = shapes();
  assert.equal(new Set(initial).size, 2, "Categories must remain distinguishable without color");
  instance.seek(2020);
  assert.deepEqual(shapes(), initial, "Time must not reassign category symbols");
  instance.setState({filters: {group: ["Research"]}});
  assert.deepEqual(shapes(), [initial[0]], "A filtered category keeps its original symbol");
  const symbol = marks(chart(instance), "dot")[0];
  symbol.dispatchEvent(new env.window.MouseEvent("click", {bubbles: true}));
  assert.deepEqual(plain(instance.getState().selected), ["a"], "Symbol paths retain record selection");
  instance.setState({view: "bar", filters: {}, selected: []});
  const bars = [...marks(chart(instance), "bar")];
  assert.ok(bars.some(mark => mark.getAttribute("fill") === "#fff"), "At least one category has a white fill");
  assert.ok(bars.every(mark => (mark.getAttribute("stroke") || mark.parentNode.getAttribute("stroke")) === "#111"), "White-filled bars remain visible through their outlines");
});

test("bar and histogram produce quantitative marks and table view exposes records", t => {
  const env = environment(t), instance = env.create();
  instance.setState({view: "bar"});
  let svg = chart(instance);
  assert.ok([...svg.querySelectorAll("rect")].some(element => +element.getAttribute("height") > 0), "Bar view must contain nonzero bars");
  instance.setState({view: "histogram"});
  svg = chart(instance);
  assert.ok([...svg.querySelectorAll("rect")].some(element => +element.getAttribute("height") > 0), "Histogram must contain occupied bins");
  instance.setState({view: "table"});
  assert.ok(shadow(instance).querySelector("table"), "Table view must display row records");
  assert.match(shadow(instance).textContent, /Alpha/);
  assert.match(shadow(instance).textContent, /Beta/);
  assert.deepEqual(env.errors, []);
});

test("time scrub, category filter, search, and undo update one shared cohort", t => {
  const env = environment(t), instance = env.create();
  const input = shadow(instance).querySelector('input[aria-label="Observation time"]');
  input.value = "1";
  input.dispatchEvent(new env.window.Event("input", {bubbles: true}));
  assert.equal(instance.getState().time, 2024);
  assert.equal(instance.getRows().length, 2);
  const select = shadow(instance).querySelector(".filter-controls select");
  assert.ok(select);
  const option = [...select.options].find(item => item.textContent === "Research");
  assert.ok(option);
  select.value = option.value;
  select.dispatchEvent(new env.window.Event("change", {bubbles: true}));
  assert.deepEqual(plain(instance.getRows()).map(row => row.entity), ["a"]);
  const search = shadow(instance).querySelector('input[type="search"]');
  search.value = "Beta";
  search.dispatchEvent(new env.window.Event("input", {bubbles: true}));
  assert.equal(instance.getRows().length, 0);
  button(instance, "Undo").click();
  assert.equal(instance.getState().search, "");
  assert.deepEqual(plain(instance.getRows()).map(row => row.entity), ["a"]);
  button(instance, "Reset exploration").click();
  assert.equal(instance.getState().time, 2028);
  assert.equal(instance.getRows().length, 2);
});

test("clicking a visible scatter mark selects its observation", t => {
  const env = environment(t), instance = env.create();
  const point = marks(chart(instance), "dot")[0];
  const coordinates = {bubbles: true, clientX: position(point).x, clientY: position(point).y};
  const movement = new env.window.MouseEvent("pointermove", coordinates);
  Object.defineProperty(movement, "pointerType", {value: "mouse"});
  point.dispatchEvent(movement);
  point.dispatchEvent(new env.window.MouseEvent("click", coordinates));
  assert.equal(instance.getState().selected.length, 1, JSON.stringify({point: point.outerHTML, errors: env.errors.map(error => error.message)}));
  assert.equal(instance.getRows().length, 2);
});

test("data selection preserves cohort counts and stable entity IDs", t => {
  const env = environment(t), instance = env.create();
  instance.select("b");
  assert.equal(instance.getRows().length, 2);
  instance.seek(2024);
  assert.deepEqual(plain(instance.getState().selected), ["b"]);
  instance.setPresentation("data");
  const table = shadow(instance).querySelector(".data-panel table");
  assert.ok(table);
  assert.match(table.textContent, /Not observed/);
  assert.ok(table.querySelector("button"), "Row records must offer a keyboard accessible selection control");
  table.querySelector("button").click();
  assert.equal(instance.getRows().length, 2);
});

test("size-sorted scatter marks retain the entity identity at the clicked position", t => {
  const env = environment(t), doc = fixture();
  doc.dataset.fields.push({key: "sample_size", label: "Sample size", type: "number"});
  doc.dataset.rows.forEach(row => { row.sample_size = row.entity === "b" ? 100 : 1; });
  doc.views[0].size = "sample_size";
  const instance = env.create(doc);
  const points = [...marks(chart(instance), "dot")];
  const highestMeasurement = points.reduce((first, second) => position(first).y < position(second).y ? first : second);
  const coordinates = {bubbles: true, clientX: position(highestMeasurement).x, clientY: position(highestMeasurement).y};
  highestMeasurement.dispatchEvent(new env.window.MouseEvent("click", coordinates));
  assert.deepEqual(plain(instance.getState().selected), ["b"]);
});

test("bubble area is proportional to value and remains fixed across time, filters, and selection", t => {
  const env = environment(t), doc = fixture();
  doc.dataset.fields.push({key: "sample_size", label: "Sample size", type: "number"});
  doc.dataset.rows.forEach(row => { row.sample_size = (row.entity === "a" ? 1 : 4) * (row.year === 2028 ? 4 : 1); });
  doc.views[0].size = "sample_size";
  const instance = env.create(doc);
  const radii = () => [...marks(chart(instance), "dot")].map(mark => +mark.getAttribute("r")).sort((a, b) => a - b);
  const latest = radii();
  assert.equal(latest[1] ** 2 / latest[0] ** 2, 4, "Four times the value must occupy four times the area");
  instance.seek(2020);
  assert.equal(radii()[1], latest[0], "The same value has the same area at a different observed time");
  instance.setState({filters: {group: ["Production"]}});
  assert.deepEqual(radii(), [latest[0]], "Filtering out other values must not rescale retained bubbles");
  instance.select("b");
  assert.deepEqual(radii(), [latest[0]], "Selection must not distort a quantitative area encoding");
  instance.dispose();
  doc.dataset.rows.filter(row => row.year === 2020).forEach(row => { row.sample_size = row.entity === "a" ? null : -1; });
  const missing = env.create(doc);
  missing.seek(2020);
  assert.equal(shadow(missing).querySelectorAll('.plot circle').length, 0);
  assert.match(shadow(missing).textContent, /No observations in this view/);
  assert.match(shadow(missing).textContent, /2 excluded/);
});

test("clicking a category bar applies the matching shared filter", t => {
  const env = environment(t), instance = env.create();
  instance.setState({view: "bar"});
  const bar = marks(chart(instance), "bar")[0];
  assert.ok(bar);
  bar.dispatchEvent(new env.window.MouseEvent("click", {
    bubbles: true,
    clientX: +bar.getAttribute("x") + +bar.getAttribute("width") / 2,
    clientY: +bar.getAttribute("y") + +bar.getAttribute("height") / 2
  }));
  const groups = plain(instance.getState().filters).group;
  assert.equal(groups.length, 1);
  assert.equal(instance.getRows().length, 1);
  assert.ok(instance.getRows().every(row => row.group === groups[0]));
});

test("playback steps only observed frames, retains domains, and stops at the last frame", t => {
  const env = environment(t), instance = env.create();
  const domainLabels = () => [...chart(instance).querySelectorAll('g[aria-label$="axis tick label"] text')].map(element => element.textContent).join("|");
  const originalDomain = domainLabels();
  const visited = [];
  const unsubscribe = instance.subscribe(() => visited.push(instance.getState().time));
  instance.play();
  assert.equal(instance.getState().time, 2020);
  assert.equal(instance.audit().playing, true);
  assert.equal(env.timers.size, 1);
  env.tick();
  assert.equal(instance.getState().time, 2024);
  assert.equal(domainLabels(), originalDomain);
  env.tick();
  assert.equal(instance.getState().time, 2028);
  assert.equal(instance.audit().playing, false);
  assert.equal(env.timers.size, 0);
  assert.deepEqual(visited, [2020, 2024, 2028]);
  unsubscribe();
});

test("reduced-motion preference disables automatic playback but permits observed steps", t => {
  const env = environment(t, {reducedMotion: true}), instance = env.create();
  instance.play();
  assert.equal(env.timers.size, 0);
  assert.equal(instance.getState().time, 2028);
  button(instance, "Previous observed frame").click();
  assert.equal(instance.getState().time, 2024);
});

test("state and evidence exports retain cohort data, provenance, and selected entities", t => {
  const env = environment(t), instance = env.create();
  instance.setState({time: 2020, filters: {group: ["Research"]}, selected: ["a"], view: "scatter"});
  const state = JSON.parse(instance.exportState());
  assert.equal(state.time, 2020);
  assert.deepEqual(state.filters.group, ["Research"]);
  assert.deepEqual(state.selected, ["a"]);
  const evidence = plain(instance.exportEvidence());
  assert.equal(evidence.rows.length, 1);
  assert.equal(evidence.rows[0].entity, "a");
  assert.equal(evidence.sources[0].url, "https://example.test/measurements");
  assert.deepEqual(evidence.state, state);
  assert.match(instance.exportCSV(), /"Alpha"/);
  assert.doesNotMatch(instance.exportCSV(), /"Beta"/);
  assert.match(instance.exportSVG(), /^<svg/);
  instance.setState({time: 2028, filters: {}, selected: []});
  instance.setState(state);
  assert.deepEqual(plain(instance.getState()), state);
});

test("loading a new document replaces data, headings, source details, and state", t => {
  const env = environment(t), instance = env.create();
  instance.select("a");
  const next = fixture();
  next.id = "replacement";
  next.title = "Replacement observation study";
  next.subtitle = "Replacement coverage description.";
  next.dataset.rows = [{entity: "c", name: "Gamma", year: 2032, value: 11, group: "Independent"}];
  next.dataset.sources = [{title: "Replacement source", url: "https://example.test/replacement"}];
  instance.load(next);
  assert.equal(instance.getDocument().id, "replacement");
  assert.equal(instance.getRows().length, 1);
  assert.equal(instance.getRows()[0].entity, "c");
  assert.deepEqual(plain(instance.getState().selected), []);
  assert.equal(instance.getState().time, 2032);
  assert.equal(shadow(instance).querySelector("h1").textContent, next.title);
  assert.match(shadow(instance).textContent, /Replacement coverage description/);
  instance.setPresentation("sources");
  assert.match(shadow(instance).querySelector(".sources-panel").textContent, /Replacement source/);
});

test("two instances isolate state and disposal releases only the owning instance", t => {
  const env = environment(t), first = env.create(), second = env.create(fixture(), {}, "second");
  let firstEvents = 0, secondEvents = 0;
  first.subscribe(() => firstEvents++);
  second.subscribe(() => secondEvents++);
  first.select("a");
  first.seek(2020);
  assert.deepEqual(plain(second.getState().selected), []);
  assert.equal(second.getState().time, 2028);
  first.play();
  second.play();
  assert.equal(env.timers.size, 2);
  first.dispose();
  assert.equal(env.timers.size, 1);
  assert.equal(env.observers.size, 1);
  assert.equal(env.mediaListeners.size, 1);
  const eventsAtDisposal = firstEvents;
  env.tick();
  assert.equal(firstEvents, eventsAtDisposal);
  assert.ok(secondEvents > 0);
  assert.equal(second.getState().time, 2024);
  assert.equal(env.window.document.getElementById("first").children.length, 0);
  assert.throws(() => first.getState(), /disposed/i);
  second.dispose();
  assert.equal(env.timers.size, 0);
  assert.equal(env.observers.size, 0);
  assert.equal(env.mediaListeners.size, 0);
});

test("metadata and row labels render as text without creating active HTML or network requests", t => {
  const env = environment(t), doc = fixture();
  const payload = '<img src="https://example.test/attack" onerror="window.executionObserved=true"><script>window.executionObserved=true</script>';
  doc.title = payload;
  doc.subtitle = payload;
  doc.dataset.rows[4].name = payload;
  doc.dataset.notes = [payload];
  doc.dataset.sources[0].title = payload;
  doc.questions[0].title = payload;
  doc.questions[0].body = payload;
  const instance = env.create(doc);
  assert.equal(shadow(instance).querySelector("h1").textContent, payload);
  instance.select("a");
  instance.setPresentation("data");
  instance.setPresentation("sources");
  assert.equal(shadow(instance).querySelectorAll("script,img").length, 0);
  assert.equal(env.window.executionObserved, undefined);
  assert.deepEqual(env.requests, []);
  assert.deepEqual(env.errors, []);
});

test("custom renderers require explicit registration and render through the public extension API", t => {
  const env = environment(t), doc = fixture();
  doc.views[0].type = "custom-observation";
  assert.throws(() => env.create(doc), /unsupported/);
  let calls = 0;
  env.window.DataExploration.registerRenderer("custom-observation", context => {
    calls++;
    const svg = env.window.document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "600");
    svg.setAttribute("height", "400");
    svg.setAttribute("data-custom-renderer", "true");
    return svg;
  });
  const instance = env.create(doc);
  assert.ok(calls > 0);
  assert.ok(shadow(instance).querySelector('svg[data-custom-renderer="true"]'));
  assert.equal(instance.audit().errors, 0);
});

test("full-history views reconcile rows, summaries, evidence, CSV, and the Data panel", t => {
  const env = environment(t), instance = env.create();
  instance.setState({view: "line", mode: "snapshot", time: 2024});
  const rows = plain(instance.getRows());
  assert.equal(rows.length, 6);
  assert.deepEqual([...new Set(rows.map(row => row.year))].sort(), [2020, 2024, 2028]);
  const summary = instance.getSummary();
  assert.equal(summary.visible, 6);
  assert.equal(summary.frameVisible, 2);
  const evidence = plain(instance.exportEvidence());
  assert.deepEqual(evidence.rows, rows);
  assert.equal(evidence.summary.visible, 6);
  assert.equal(evidence.summary.frameVisible, 2);
  const csv = instance.exportCSV().split(/\r?\n/);
  assert.equal(csv.length, 7);
  assert.equal(csv.filter(line => line.includes('"2020"')).length, 2);
  assert.equal(csv.filter(line => line.includes('"2028"')).length, 2);
  instance.setPresentation("data");
  const tableRows = [...shadow(instance).querySelectorAll(".data-panel tbody tr")];
  assert.equal(tableRows.length, 6);
  assert.equal(tableRows.filter(row => row.textContent.replaceAll(",", "").includes("2020")).length, 2);
  assert.equal(tableRows.filter(row => row.textContent.replaceAll(",", "").includes("2028")).length, 2);
});

test("historical point inspection seeks the clicked measurement of a repeated entity", t => {
  const env = environment(t), instance = env.create();
  instance.setState({view: "line", mode: "snapshot", time: 2028});
  const points = [...marks(chart(instance), "dot")];
  const earliestX = Math.min(...points.map(point => position(point).x));
  const earliestPoints = points.filter(point => position(point).x === earliestX);
  const firstAlpha = earliestPoints.reduce((first, second) => position(first).y > position(second).y ? first : second);
  firstAlpha.dispatchEvent(new env.window.MouseEvent("click", {
    bubbles: true, clientX: position(firstAlpha).x, clientY: position(firstAlpha).y
  }));
  assert.equal(instance.getState().time, 2020);
  assert.deepEqual(plain(instance.getState().selected), ["a"]);
  const terms = [...shadow(instance).querySelectorAll("aside dt")];
  const measuredDuration = terms.find(term => term.textContent.includes("Measured duration"));
  const observationYear = terms.find(term => term.textContent.includes("Observation year"));
  assert.ok(measuredDuration, "Inspector must expose the selected measurement");
  assert.ok(observationYear, "Inspector must expose the selected observation year");
  assert.equal(measuredDuration.nextElementSibling.textContent, "2 hours");
  assert.equal(observationYear.nextElementSibling.textContent.replaceAll(",", ""), "2020");
  assert.equal(instance.getRows().length, 6, "Inspecting history must preserve the full-history cohort");
});

test("Compare entities permits additive mark and table selection without modifier keys", t => {
  const env = environment(t), instance = env.create();
  button(instance, "Compare entities").click();
  assert.equal(button(instance, "Compare entities").getAttribute("aria-pressed"), "true");
  const clickPoint = index => {
    const point = marks(chart(instance), "dot")[index];
    point.dispatchEvent(new env.window.MouseEvent("click", {
      bubbles: true, clientX: position(point).x, clientY: position(point).y
    }));
  };
  clickPoint(0);
  clickPoint(1);
  assert.deepEqual(plain(instance.getState().selected).sort(), ["a", "b"]);
  instance.setPresentation("data");
  const clickRecord = name => {
    const row = [...shadow(instance).querySelectorAll(".data-panel tbody tr")].find(element => element.textContent.includes(name));
    assert.ok(row, "Expected row " + name);
    const control = row.querySelector("button");
    assert.ok(control, "Expected a selection control for " + name);
    control.click();
  };
  clickRecord("Alpha");
  assert.deepEqual(plain(instance.getState().selected), ["b"]);
  clickRecord("Beta");
  assert.deepEqual(plain(instance.getState().selected), []);
  clickRecord("Alpha");
  clickRecord("Beta");
  assert.deepEqual(plain(instance.getState().selected).sort(), ["a", "b"]);
  assert.equal(instance.getRows().length, 2);
});

test("drawing starts without a data sheet and inspection remains keyboard accessible", t => {
  const env = environment(t), instance = env.create(), root = shadow(instance);
  assert.equal(root.querySelector('.sidebar').hidden, true);
  assert.equal(instance.audit().panel, null);
  const mark = marks(chart(instance), 'dot')[0];
  assert.equal(mark.getAttribute('tabindex'), '0');
  mark.dispatchEvent(new env.window.KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
  assert.equal(instance.audit().panel, 'inspect');
  assert.equal(root.querySelector('.sidebar').hidden, false);
  assert.equal(root.activeElement, root.querySelector('.sidebar'));
  button(instance, 'Close data sheet').click();
  assert.equal(instance.audit().panel, null);
  assert.deepEqual(plain(instance.getState().selected), []);
  button(instance, 'Explore').click();
  assert.equal(instance.audit().panel, 'explore');
  assert.equal(button(instance, 'Explore').getAttribute('aria-expanded'), 'true');
  root.dispatchEvent(new env.window.KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  assert.equal(instance.audit().panel, null);
});

test("focused histories and nested cohorts restore exact parent comparisons", t => {
  const env = environment(t), instance = env.create();
  instance.setState({time: 2020, search: 'Alpha', selected: ['a']});
  const parent = plain(instance.getState());
  assert.equal(instance.focusEntity('a'), true);
  assert.equal(instance.audit().depth, 1);
  assert.equal(instance.getState().view, 'line');
  assert.deepEqual(plain(instance.getRows()).map(row => row.year), [2020, 2024, 2028]);
  assert.ok(instance.getRows().every(row => row.entity === 'a'));
  assert.equal(instance.focusCohort('group', 'Research'), true);
  assert.equal(instance.audit().depth, 2);
  assert.equal(instance.exportEvidence().navigation.parents.length, 2);
  instance.back();
  assert.equal(instance.audit().depth, 1);
  instance.back();
  assert.deepEqual(plain(instance.getState()), parent);
  assert.equal(instance.audit().panel, 'inspect');
  assert.equal(instance.audit().depth, 0);
  instance.setPresentation('sources');
  assert.equal(instance.audit().panel, null);
  instance.back();
  assert.equal(instance.audit().presentation, 'chart');
  assert.deepEqual(plain(instance.getState()), parent);
});

test("observed-frame motion preserves exact coordinates, cancels cleanly, and respects reduced motion", t => {
  const env = environment(t, {recordAnimations: true}), instance = env.create();
  instance.seek(2020);
  const movements = env.recordedAnimations.filter(animation => animation.element.hasAttribute('data-observation-key') && animation.keyframes[0].transform);
  assert.ok(movements.length > 0, 'Repeated entities should move between observed positions');
  assert.ok(movements.every(animation => animation.options.duration === 420));
  assert.equal(instance.audit().animating, true);
  const rows = instance.getRows();
  const svg = chart(instance);
  for (const mark of marks(svg, 'dot')) {
    const row = rows[Number(mark.dataset.rowIndex)];
    const location = position(mark);
    assert.equal(location.x, svg.scale('x').apply(row.year));
    assert.equal(location.y, svg.scale('y').apply(row.value));
  }
  assert.deepEqual(plain(instance.exportEvidence().rows).map(row => row.year), [2020, 2020]);
  instance.seek(2024);
  assert.ok(movements.every(animation => animation.cancelled), 'A new frame interrupts previous motion');
  instance.dispose();
  assert.ok(env.recordedAnimations.every(animation => animation.cancelled));
  const quiet = environment(t, {recordAnimations: true, reducedMotion: true}), reduced = quiet.create();
  reduced.seek(2020);
  assert.equal(quiet.recordedAnimations.length, 0);
  assert.equal(reduced.audit().animating, false);
});

test("undo restores focus context and repeated-entity record navigation retains inspection", t => {
  const env = environment(t), instance = env.create();
  const initial = plain(instance.getState());
  instance.focusCohort('group', 'Research');
  assert.equal(instance.audit().depth, 1);
  button(instance, 'Undo').click();
  assert.equal(instance.audit().depth, 0);
  assert.equal(instance.audit().focus, 'Overview');
  assert.deepEqual(plain(instance.getState()), initial);
  instance.focusEntity('a');
  const first = [...marks(chart(instance), 'dot')][0];
  first.dispatchEvent(new env.window.MouseEvent('click', {bubbles: true}));
  assert.equal(instance.getState().time, 2020);
  button(instance, 'Next observation').click();
  assert.equal(instance.getState().time, 2024);
  assert.deepEqual(plain(instance.getState().selected), ['a']);
  assert.equal(instance.audit().panel, 'inspect');
  assert.equal(shadow(instance).querySelectorAll('[data-time-cursor]').length, 1);
  assert.equal(instance.focusCohort('group', 'Unknown group'), false);
});

test("sampled steps and sparse markers preserve exact selection and explicit gap guides", t => {
  const env=environment(t),doc=fixture();
  doc.dataset.rows=[[2020,2],[2021,2],[2022,2],[2023,3],[2030,4],[2031,4]].map(([year,value])=>({entity:"a",name:"Alpha",year,value,group:"Research"}));
  Object.assign(doc.views[1],{curve:"step-after",points:"changes",maxGap:5,gapStyle:"dashed",clip:true,yReverse:true,yDomain:[1,5]});
  const instance=env.create(doc,{state:{view:"line"}}),svg=chart(instance);
  assert.ok(svg.querySelector('[aria-description="Unsampled interval"]'),"Long unsampled intervals must be distinct");
  assert.ok(svg.querySelector('clipPath'),"An explicit rank window clips off-window geometry");
  assert.equal(marks(svg,"dot").length,5);
  const positions=[...marks(svg,"dot")].map(position);
  assert.ok(positions[0].y<positions.at(-1).y,"Rank 1 is above larger rank numbers");
  const last=[...marks(svg,"dot")].at(-1); last.dispatchEvent(new env.window.MouseEvent("click",{bubbles:true}));
  assert.equal(instance.getState().time,2031,"Sparse marker selection maps to the actual source record");
  assert.equal(instance.getRows().length,6,"Marker reduction never removes observations from export");
  assert.deepEqual(env.errors,[]);
});

test("focused ranges stay fixed across time and live load preserves navigation and presentation", t => {
  const env=environment(t),doc=fixture();
  doc.views[0].detailView="line"; doc.views[1].domainScope="cohort";
  const instance=env.create(doc); instance.select("a");
  const parent=plain(instance.getState());
  assert.equal(instance.focusEntity("a"),true);
  const domain=()=>plain(chart(instance).scale("y").domain);
  assert.deepEqual(domain(),[2,8]);
  instance.seek(2020); assert.deepEqual(domain(),[2,8]);
  instance.setPresentation("sources");
  const refreshed=fixture();refreshed.views=doc.views;
  refreshed.dataset.rows.push({entity:"a",name:"Alpha",year:2032,value:16,group:"Research"});
  instance.load(refreshed,{preserveState:true});
  assert.equal(instance.audit().depth,1);assert.equal(instance.audit().presentation,"sources");
  assert.equal(instance.getState().time,2020);
  instance.back(); assert.deepEqual(domain(),[2,16]);
  instance.back(); assert.deepEqual(plain(instance.getState()),parent);
  instance.load(refreshed);assert.equal(instance.audit().depth,0);assert.equal(instance.getState().time,2032);
  assert.deepEqual(env.errors,[]);
});

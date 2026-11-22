"use strict";
(() => {
  const element = id => document.getElementById(id);
  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  let reports = [], token, revision = 0, signature = "", undo = null;
  const pickers = new Map();
  const rows = new Map();
  const pending = new Set();
  const feedback = text => { element("report-feedback").textContent = text; };
  const error = text => { element("report-error").textContent = text; element("report-error").hidden = !text; };
  const origin = report => [report.origin.agent, report.origin.provider, report.origin.workspace, report.origin.host].filter(Boolean).join(" · ");
  const time = value => new Date(value).toLocaleString(undefined, {year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"});
  function createPicker(select) {
    const wrapper = make("div", null, "collection-picker"), button = make("button", null, "collection-picker-trigger");
    const value = make("span"), options = make("div", null, "collection-picker-options");
    let active = select.selectedIndex, prefix = "", typedAt = 0;
    button.type = "button"; button.id = select.id + "-trigger"; value.id = select.id + "-value";
    options.id = select.id + "-options"; options.hidden = true;
    button.setAttribute("role", "combobox"); button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false"); button.setAttribute("aria-controls", options.id);
    button.setAttribute("aria-labelledby", select.id + "-label " + value.id);
    for (const attribute of ["aria-required", "aria-describedby"]) {
      if (select.hasAttribute(attribute)) button.setAttribute(attribute, select.getAttribute(attribute));
    }
    options.setAttribute("role", "listbox"); options.setAttribute("aria-labelledby", select.id + "-label");
    element(select.id + "-label").htmlFor = button.id;
    select.before(wrapper); wrapper.append(select, button, options); button.append(value);
    select.classList.add("collection-native-select"); select.tabIndex = -1; select.setAttribute("aria-hidden", "true");
    function highlight(index, scroll = false) {
      active = Math.max(0, Math.min(index, select.options.length - 1));
      [...options.children].forEach((option, position) => { option.dataset.active = String(position === active); });
      const current = options.children[active];
      if (!options.hidden && current) {
        button.setAttribute("aria-activedescendant", current.id);
        if (scroll) current.scrollIntoView({block: "nearest"});
      }
    }
    function close() {
      options.hidden = true; button.setAttribute("aria-expanded", "false");
      button.removeAttribute("aria-activedescendant"); prefix = "";
    }
    function sync() {
      const highlightedValue = options.children[active]?.dataset.value;
      value.textContent = select.selectedOptions[0]?.textContent || ""; button.title = value.textContent;
      options.replaceChildren();
      [...select.options].forEach((entry, index) => {
        const option = make("div", entry.textContent, "collection-picker-option");
        option.id = select.id + "-option-" + index; option.dataset.value = entry.value;
        option.setAttribute("role", "option"); option.setAttribute("aria-selected", String(entry.selected));
        option.addEventListener("pointermove", () => highlight(index));
        option.addEventListener("mousedown", event => event.preventDefault());
        option.onclick = () => choose(index); options.append(option);
      });
      const preserved = [...select.options].findIndex(entry => entry.value === highlightedValue);
      highlight(!options.hidden && preserved >= 0 ? preserved : select.selectedIndex);
    }
    function open() {
      for (const picker of pickers.values()) picker.close();
      button.focus({preventScroll: true});
      options.hidden = false; button.setAttribute("aria-expanded", "true"); highlight(select.selectedIndex, true);
    }
    function choose(index) {
      select.selectedIndex = index; close(); sync();
      select.dispatchEvent(new Event("input", {bubbles: true})); button.focus({preventScroll: true});
    }
    button.onclick = () => options.hidden ? open() : close();
    button.onkeydown = event => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === "Tab") { close(); return; }
      if (event.key === "Escape") { if (!options.hidden) event.preventDefault(); close(); return; }
      if (["Enter", " ", "ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const wasClosed = options.hidden;
        if (wasClosed) open();
        if (event.key === "Home") highlight(0, true);
        else if (event.key === "End") highlight(select.options.length - 1, true);
        else if (!wasClosed && (event.key === "Enter" || event.key === " ")) choose(active);
        else if (!wasClosed) highlight(active + (event.key === "ArrowDown" ? 1 : -1), true);
      } else if (event.key.length === 1) {
        event.preventDefault(); if (options.hidden) open();
        const now = Date.now(); prefix = now - typedAt > 700 ? event.key : prefix + event.key; typedAt = now;
        const query = [...prefix].every(letter => letter === prefix[0]) ? prefix[0] : prefix;
        for (let offset = 1; offset <= select.options.length; offset++) {
          const index = (active + offset) % select.options.length;
          if (select.options[index].textContent.toLowerCase().startsWith(query.toLowerCase())) { highlight(index, true); break; }
        }
      }
    };
    button.addEventListener("blur", close);
    document.addEventListener("pointerdown", event => { if (!wrapper.contains(event.target)) close(); });
    select.addEventListener("input", sync); sync();
    return {sync, close};
  }
  async function request(path, body) {
    const response = await fetch(path, {cache: "no-store", ...(body === undefined ? {} : {
      method: "POST", headers: {"Content-Type": "application/json", "X-Status-Token": token}, body: JSON.stringify(body)
    })});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || "The status collection is unavailable. Try Refresh.");
    return result;
  }
  function render() {
    const view = element("report-view").value, project = element("report-project").value, query = element("report-search").value.trim().toLowerCase();
    const visible = reports.filter(report => (view === "all" || Boolean(report.dismissed_at) === (view === "dismissed")) &&
      (!project || report.origin.workspace === project) && (!query || [report.title, report.subject, report.summary, origin(report)].join(" ").toLowerCase().includes(query)));
    const list = element("report-list");
    for (const [index, report] of visible.entries()) {
      let row = rows.get(report.id);
      if (!row) {
        row = make("li", null, "collection-row"); row.dataset.reportId = report.id;
        const record = make("div", null, "collection-record"), heading = make("h2");
        const title = make("a", report.title, "collection-title");
        title.href = "/reports/" + report.id; title.target = "_blank"; title.rel = "noopener";
        title.setAttribute("aria-label", report.title + " (opens in a new tab)"); heading.append(title);
        record.append(heading, make("p", report.summary, "collection-summary"), make("p", origin(report) || report.subject, "collection-note"),
          make("p", "", "collection-note"));
        if (report.response_field_count) record.append(window.createStatusResponses(report, {make, request, createPicker, pickers, time}));
        const action = make("button", "", "collection-action"); action.type = "button";
        row.append(record, action); rows.set(report.id, row);
      }
      const action = row.querySelector(".collection-action");
      action.textContent = report.dismissed_at ? "Restore" : "Dismiss";
      action.setAttribute("aria-label", `${report.dismissed_at ? "Restore" : "Dismiss"} ${report.title}`);
      action.disabled = pending.has(report.id) || !token;
      action.onclick = () => changeDismissal(report.id, !report.dismissed_at);
      row.querySelector(".collection-record > .collection-note:last-of-type").textContent = "Generated " + time(report.generated_at) + (report.dismissed_at ? " · Dismissed " + time(report.dismissed_at) : "");
      if (list.children[index] !== row) list.insertBefore(row, list.children[index] || null);
    }
    const visibleIds = new Set(visible.map(report => report.id));
    for (const row of [...list.children]) if (!visibleIds.has(row.dataset.reportId)) row.remove();
    element("report-empty").hidden = visible.length > 0;
    element("report-empty").textContent = reports.length ? "No reports match this view." : "No reports yet. Ask an agent to use the status skill; its HTML report will appear here.";
    element("report-counts").textContent = `${reports.filter(report => !report.dismissed_at).length} in inbox · ${reports.filter(report => report.dismissed_at).length} dismissed`;
  }
  async function load(manual = false) {
    const current = ++revision;
    try {
      token = (await request("/api/config")).token;
      const result = await request("/api/reports");
      if (current !== revision) return;
      error("");
      element("report-coverage").hidden = !result.unreadable;
      element("report-coverage").textContent = `${result.unreadable} report record(s) could not be read. Other reports remain available.`;
      const nextSignature = JSON.stringify(result);
      if (nextSignature !== signature) {
        signature = nextSignature; reports = result.reports;
        const picker = element("report-project"), selectedProject = picker.value;
        picker.replaceChildren(new Option("All projects", ""));
        for (const project of [...new Set(reports.map(report => report.origin.workspace).filter(Boolean))].sort()) picker.add(new Option(project, project));
        picker.value = [...picker.options].some(option => option.value === selectedProject) ? selectedProject : "";
        pickers.get("report-project").sync();
        render();
      }
      if (!undo || manual) feedback(manual ? "Reports refreshed." : "");
    } catch (failure) { if (current === revision) { error(failure.message); feedback("Could not refresh reports."); } }
  }
  async function changeDismissal(id, dismissed, isUndo = false) {
    if (pending.has(id)) return;
    pending.add(id); revision += 1; render();
    try {
      const updated = await request("/api/dismiss", {id, dismissed});
      reports = reports.map(report => report.id === id ? updated : report);
      undo = isUndo ? null : {id, dismissed: !dismissed};
      element("undo-report").hidden = !undo;
      signature = ""; error("");
      feedback(dismissed ? "Report dismissed. Future reports from this agent will still appear." : "Report restored to the inbox.");
    } catch (failure) { error(failure.message); }
    finally {
      pending.delete(id); render();
      if (undo) element("undo-report").focus({preventScroll: true});
      else document.querySelector(`[data-report-id="${id}"] a`)?.focus({preventScroll: true});
    }
  }
  document.querySelector("form").onsubmit = event => event.preventDefault();
  for (const id of ["report-view", "report-project"]) pickers.set(id, createPicker(element(id)));
  for (const id of ["report-view", "report-project", "report-search"]) element(id).addEventListener("input", render);
  element("refresh-reports").onclick = () => load(true);
  element("undo-report").onclick = () => { if (undo) changeDismissal(undo.id, undo.dismissed, true); };
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  const timer = setInterval(() => { if (!document.hidden && !pending.size) load(); }, 10000);
  addEventListener("pagehide", () => clearInterval(timer));
  addEventListener("beforeunload", event => {
    if ([...rows.values()].some(row => row.querySelector('[data-dirty="true"]'))) {
      event.preventDefault(); event.returnValue = "";
    }
  });
  load();
})();

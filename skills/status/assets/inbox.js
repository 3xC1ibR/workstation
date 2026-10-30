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
  const pending = new Set();
  const feedback = text => { element("report-feedback").textContent = text; };
  const error = text => { element("report-error").textContent = text; element("report-error").hidden = !text; };
  const origin = report => [report.origin.agent, report.origin.provider, report.origin.workspace, report.origin.host].filter(Boolean).join(" · ");
  const time = value => new Date(value).toLocaleString(undefined, {year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"});
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
    const list = element("report-list"); list.replaceChildren();
    for (const report of visible) {
      const row = make("li", null, "collection-row"); row.dataset.reportId = report.id;
      const record = make("div", null, "collection-record"), heading = make("h2");
      const title = make("a", report.title, "collection-title");
      title.href = "/reports/" + report.id; title.target = "_blank"; title.rel = "noopener";
      title.setAttribute("aria-label", report.title + " (opens in a new tab)"); heading.append(title);
      record.append(heading, make("p", report.summary, "collection-summary"), make("p", origin(report) || report.subject, "collection-note"),
        make("p", "Generated " + time(report.generated_at) + (report.dismissed_at ? " · Dismissed " + time(report.dismissed_at) : ""), "collection-note"));
      const action = make("button", report.dismissed_at ? "Restore" : "Dismiss", "collection-action"); action.type = "button";
      action.setAttribute("aria-label", `${report.dismissed_at ? "Restore" : "Dismiss"} ${report.title}`);
      action.disabled = pending.has(report.id) || !token;
      action.onclick = () => changeDismissal(report.id, !report.dismissed_at);
      row.append(record, action); list.append(row);
    }
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
  for (const id of ["report-view", "report-project", "report-search"]) element(id).addEventListener("input", render);
  element("refresh-reports").onclick = () => load(true);
  element("undo-report").onclick = () => { if (undo) changeDismissal(undo.id, undo.dismissed, true); };
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  const timer = setInterval(() => { if (!document.hidden && !pending.size) load(); }, 10000);
  addEventListener("pagehide", () => clearInterval(timer));
  load();
})();

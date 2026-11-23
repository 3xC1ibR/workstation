"use strict";
(() => {
  const {make, time, elapsed, base, request, measure} = window.StatusControls;
  const element = id => document.getElementById(id);
  let review = null, signature = "", undo = null, noticeTimer = null, revision = 0, searched = "";
  const WEEK = 7 * 86400e3, olderOpen = {deliveries: false, operations: false};       // the reader's own choice for each Older group
  const pending = new Set();
  const view = () => document.querySelector('input[name="view"]:checked').value;
  const plural = (count, noun, many = noun + "s") => `${count} ${count === 1 ? noun : many}`;
  const matches = (query, ...parts) => !query || parts.filter(Boolean).join(" ").toLowerCase().includes(query);

  function notice(text, reverse) {
    undo = reverse || null;
    element("review-notice").firstElementChild.textContent = text;
    element("review-undo").hidden = !undo;
    element("review-notice").hidden = false;
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => { element("review-notice").hidden = true; undo = null; }, 8000);
  }
  function failure(text) { element("review-error").textContent = text; element("review-error").hidden = !text; }

  // A row is a title and one quiet line: state words first, then the kind, then an excerpt.
  function row({key, state, closed, href, title, flags, excerpt, at, actions}) {
    const item = make("li", null, "row"); item.dataset.key = key; item.dataset.state = state; item.dataset.closed = String(Boolean(closed));
    item.dataset.kind = key.split("-")[0];
    const main = make("div", null, "row-main"), link = make("a", title, "row-title");
    link.href = href;
    if (state === "unread") link.setAttribute("aria-label", "Unread: " + title);
    main.append(link);
    const parts = [...flags, excerpt].filter(Boolean);
    if (parts.length) {
      const details = make("p", null, "row-meta");
      parts.forEach((part, index) => { if (index) details.append(" · "); details.append(part); });
      main.append(details);
    }
    const marker = make("span", null, "marker"); marker.setAttribute("aria-hidden", "true");
    const aside = make("div", null, "row-aside"); aside.append(stamp(at));
    const controls = make("div", null, "row-actions");
    for (const [label, handler, className] of actions || []) {
      const button = make("button", label, className || ""); button.type = "button";
      button.disabled = pending.has(key); button.onclick = handler; controls.append(button);
    }
    item.append(marker, main, aside, controls);
    return item;
  }
  const stamp = value => { const node = make("time", elapsed(value)); node.dateTime = value; node.title = time(value); return node; };
  const flag = (text, className) => make("span", text, className);
  function excerpt(text, lead) {
    if (!text) return null;
    const node = make("span", null, "row-excerpt");
    if (lead) node.append(make("strong", lead + " "));
    node.append(text);
    return node;
  }

  // Ribbon Field accepted a resolution: drop the ask at once, then read Ribbon Field's list again.
  function askChanged(message, id) {
    review.asks.asks = review.asks.asks.filter(ask => ask.id !== id);
    signature = ""; render(); notice(message); load(true);
  }
  const askRow = ask => window.StatusAsks.createAskRow(ask, {changed: askChanged, publicUrl: review.public_url});
  // A delivery leaves Open once he has responded and has seen its latest version.
  const settled = delivery => Boolean(delivery.response) && !delivery.unread;
  function deliveryRow(delivery) {
    // A delivery is one row whatever its number of versions. A response stays with it; a version newer than the one
    // he read makes the row unread again and names the version his response was given on.
    const response = delivery.response, responded = Boolean(response);
    const given = responded && response.version !== delivery.id ? ` version ${delivery.response_version_number || "earlier"}` : "";
    const outcome = !response ? (delivery.version_count > 1 ? `Version ${delivery.version_count}` : null)
      : response.type === "accepted" ? flag("Accepted" + given, "outcome-accepted") : "Dismissed" + given;
    const actions = [];
    if (!responded && delivery.recommended_default) actions.push(["Do it", () => respond(delivery, "accept", "recommended_default")]);
    actions.push(responded ? ["Reopen", () => respond(delivery, "reopen"), "quiet"] : ["Dismiss", () => respond(delivery, "dismiss"), "quiet"]);
    return row({
      key: "delivery-" + delivery.series, state: delivery.unread ? "unread" : "read", closed: settled(delivery),
      href: `${base}/deliveries/${delivery.id}`, title: delivery.title, flags: [outcome, delivery.category || delivery.origin.agent],
      excerpt: !responded && delivery.recommended_default ? excerpt(delivery.recommended_default, "Recommended:") : excerpt(delivery.summary),
      at: delivery.received_at, actions});
  }
  function operationRow(operation) {
    const dismissed = Boolean(operation.dismissed_at);
    return row({
      key: "operation-" + operation.id, state: operation.unread && !dismissed ? "unread" : "read", closed: dismissed,
      href: `${base}/reports/${operation.latest}`, title: operation.title,
      flags: [operation.ask_count ? flag(plural(operation.ask_count, "ask") + " open", "flag-needs") : null,
              operation.response_field_count ? flag(plural(operation.response_field_count, "question") + " for you", "flag-needs") : null],
      excerpt: excerpt(operation.summary), at: operation.received_at,
      actions: [dismissed ? ["Restore", () => dismissOperation(operation, false), "quiet"] : ["Dismiss", () => dismissOperation(operation, true), "quiet"]]});
  }

  function fill(list, items, build) {
    const focused = document.activeElement?.closest?.(".row"), focusKey = list.contains(focused) && focused.dataset.key;
    const focusIndex = focusKey ? [...focused.querySelectorAll("a, button, textarea")].indexOf(document.activeElement) : -1;
    list.replaceChildren(...items.map(build));
    if (focusKey) [...(list.querySelector(`[data-key="${focusKey}"]`)?.querySelectorAll("a, button, textarea") || [])][focusIndex]?.focus({preventScroll: true});
  }
  // One list, newest first. Items with nothing new for a week go to the closed Older group; a search that matches inside opens it.
  function section(name, items, build, query) {
    const node = element(name), group = node.querySelector(".older"), at = item => Date.parse(item.received_at) || 0;
    if (group) items.sort((first, second) => at(second) - at(first));              // asks keep Ribbon Field's order
    let older = group ? items.filter(item => Date.now() - at(item) > WEEK) : [];
    if (older.length === items.length) older = [];                                   // a section holding nothing newer shows its rows directly
    fill(node.querySelector(".rows"), items.filter(item => !older.includes(item)), build);
    node.querySelector(".count").textContent = String(items.length);
    node.hidden = !items.length;
    if (group) {
      fill(group.querySelector(".rows"), older, build);
      group.querySelector(".count").textContent = String(older.length);
      group.hidden = !older.length;
      if (query !== searched) group.open = query ? true : olderOpen[name];
    }
    return items.length;
  }

  function render() {
    if (!review) return;
    const show = view(), query = element("review-search").value.trim().toLowerCase();
    const wanted = closed => show === "all" || closed === (show === "done");
    const asks = show === "done" ? [] : review.asks.asks.filter(ask => matches(query, ask.title, ask.detail, ask.context, ask.unblocks, ask.project_label, ask.thread_title));
    const deliveries = review.deliveries.filter(delivery => wanted(settled(delivery)) &&
      matches(query, delivery.title, delivery.summary, delivery.recommended_default, delivery.category, delivery.origin.agent, delivery.origin.workspace));
    const operations = review.operations.filter(operation => wanted(Boolean(operation.dismissed_at)) &&
      matches(query, operation.title, operation.subject, operation.summary, operation.origin.agent, operation.origin.workspace));
    const shown = section("asks", asks, askRow, query) + section("deliveries", deliveries, deliveryRow, query) + section("operations", operations, operationRow, query);
    searched = query;
    element("review-source").hidden = review.asks.available || show === "done";
    element("review-source").replaceChildren(...(review.asks.available ? [] : [make("strong", "Asks unavailable. "), review.asks.reason]));
    const awaiting = review.deliveries.filter(delivery => !settled(delivery)).length;
    const updated = review.operations.filter(operation => operation.unread && !operation.dismissed_at).length;
    const blocking = review.asks.asks.filter(ask => ask.blocking).length;
    element("review-counts").textContent = [
      review.asks.asks.length ? plural(review.asks.asks.length, "ask") + (blocking ? ` (${blocking} blocking)` : "") : null,
      awaiting ? plural(awaiting, "delivery", "deliveries") + " to review" : null,
      updated ? plural(updated, "operation") + " unread" : null].filter(Boolean).join(" · ") || (review.asks.available ? "Nothing is waiting for you" : "");
    element("review-search").parentElement.hidden = !review.deliveries.length && !review.operations.length && !review.asks.asks.length;
    const empty = element("review-empty");
    empty.hidden = shown > 0;
    if (!shown) {
      const nothing = !review.deliveries.length && !review.operations.length;
      empty.firstElementChild.textContent = query ? "No matches" : show === "done" ? "No responses yet"
        : nothing ? "No reports or deliveries yet" : "All reviewed";
      empty.lastElementChild.textContent = query ? "Search covers titles, summaries, agents and projects in this view."
        : show === "done" ? "Deliveries you accept or dismiss, and operations you dismiss, are kept here."
        : nothing ? "Operation reports and proactive deliveries from your agents will appear here as they are published."
        : "New proactive work, operation reports and asks will appear here.";
    }
    document.title = (awaiting + updated + review.asks.asks.length ? `(${awaiting + updated + review.asks.asks.length}) ` : "") + "Review";
  }

  async function load(freshAsks = false) {
    const current = ++revision;
    try {
      const result = await request("/api/review" + (freshAsks ? "?fresh=asks" : ""));
      if (current !== revision) return;
      failure("");
      element("review-coverage").hidden = !result.unreadable;
      element("review-coverage").textContent = `${plural(result.unreadable, "record")} could not be read. Everything else remains available.`;
      const next = JSON.stringify(result);
      if (next !== signature) { signature = next; review = result; render(); }
    } catch (error) { if (current === revision) failure(error.message); }
  }

  async function change(key, action, message, reverse) {
    if (pending.has(key)) return;
    pending.add(key); revision += 1; render();
    try { await action(); failure(""); if (message) notice(message, reverse); }
    catch (error) { failure(error.message); }
    finally { pending.delete(key); signature = ""; await load(); }
  }
  function respond(delivery, action, choice) {
    const message = {accept: "Accepted.", dismiss: "Dismissed.", reopen: ""}[action];
    return change("delivery-" + delivery.id, () => request("/api/delivery-response", {id: delivery.id, action, ...(choice ? {choice} : {})}),
      message, action === "reopen" ? null : () => respond(delivery, "reopen"));
  }
  function dismissOperation(operation, dismissed) {
    return change("operation-" + operation.id, () => request("/api/dismiss", {id: operation.latest, dismissed}),
      dismissed ? "Dismissed until its next version." : "", dismissed ? () => dismissOperation(operation, false) : null);
  }

  document.querySelector("form").onsubmit = event => event.preventDefault();
  const parameters = new URLSearchParams(location.search);
  if (["done", "all"].includes(parameters.get("view"))) document.querySelector(`input[name="view"][value="${parameters.get("view")}"]`).checked = true;
  for (const input of document.querySelectorAll('input[name="view"]')) input.addEventListener("change", () => {
    history.replaceState(null, "", view() === "open" ? location.pathname : "?view=" + view()); render();
  });
  element("review-search").addEventListener("input", render);
  for (const name of Object.keys(olderOpen)) {
    const group = element(name).querySelector(".older");
    group.addEventListener("toggle", () => { if (!element("review-search").value.trim()) olderOpen[name] = group.open; });
  }
  element("review-undo").onclick = () => { const reverse = undo; element("review-notice").hidden = true; undo = null; if (reverse) reverse(); };
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !window.StatusAsks.editing()) load(); });
  const timer = setInterval(() => { if (!document.hidden && !pending.size && !window.StatusAsks.editing()) load(); }, 20000);
  addEventListener("pagehide", () => clearInterval(timer));
  addEventListener("pageshow", event => { if (event.persisted) load(); });
  load();
  measure({type: "page_open", view: "review"});
})();

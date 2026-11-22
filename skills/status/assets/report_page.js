"use strict";
// Navigation for a report served by the Status service: version history, dismissal, and the operation's asks.
(() => {
  const {make, time, elapsed, request, measure, localizeTimes} = window.StatusControls;
  const configuration = JSON.parse(document.getElementById("status-configuration").textContent);
  localizeTimes();
  measure({type: "item_open", view: "operation", item_kind: "operation", item: configuration.report});
  const dismiss = document.getElementById("operation-dismiss");
  let dismissed = configuration.dismissed;
  function label() { dismiss.textContent = dismissed ? "Restore to Review" : "Dismiss"; dismiss.title = dismissed ? "" : "Hide this operation from Review until its next version"; }
  if (configuration.latest) {
    dismiss.hidden = false; label();
    dismiss.onclick = async () => {
      dismiss.disabled = true;
      try { await request("/api/dismiss", {id: configuration.report, dismissed: !dismissed}); dismissed = !dismissed; label(); }
      catch (error) { dismiss.textContent = error.message; }
      finally { dismiss.disabled = false; }
    };
  }
  const history = document.querySelector(".version-history");
  document.addEventListener("click", event => { if (history?.open && !history.contains(event.target)) history.open = false; });
  document.addEventListener("keydown", event => { if (event.key === "Escape" && history?.open) { history.open = false; history.querySelector("summary").focus(); } });
  request("/api/operations/" + configuration.operation).then(({asks}) => {
    const section = document.getElementById("operation-asks");
    if (!asks.available || !asks.asks.length) return;
    const list = make("ol", null, "rows");
    for (const ask of asks.asks) {
      const item = make("li", null, "row"); item.dataset.state = ask.blocking ? "blocking" : "waiting";
      const marker = make("span", null, "marker"), main = make("div", null, "row-main"), link = make("a", ask.title, "row-title");
      marker.setAttribute("aria-hidden", "true"); link.href = ask.thread_link; link.setAttribute("aria-label", ask.title + " (opens Ribbon Field)");
      const stamp = make("time", elapsed(ask.created_at)); stamp.dateTime = ask.created_at; stamp.title = time(ask.created_at);
      const meta = make("p", null, "row-meta"), aside = make("div", null, "row-aside");
      if (ask.blocking) meta.append(make("span", "Blocking", "flag-blocking"), " · ");
      meta.append((ask.kind ? ask.kind[0].toUpperCase() + ask.kind.slice(1) : "Ask") + (ask.effort_minutes ? `, ${ask.effort_minutes} min` : ""));
      aside.append(stamp); main.append(link);
      if (ask.unblocks) main.append(make("p", "Unblocks: " + ask.unblocks, "row-summary"));
      main.append(meta); item.append(marker, main, aside); list.append(item);
    }
    section.replaceChildren(make("h2", asks.asks.length === 1 ? "This operation needs you" : `This operation needs you (${asks.asks.length})`),
      make("p", "Answered in Ribbon Field", "section-note"), list);
    section.hidden = false;
  }).catch(() => {});
})();

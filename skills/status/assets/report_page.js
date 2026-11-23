"use strict";
// Navigation for a report served by the Status service: version history, dismissal, and the operation's asks.
(() => {
  const {make, request, measure, localizeTimes} = window.StatusControls;
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
  const section = document.getElementById("operation-asks");
  function showAsks(fresh = false) {
    return request("/api/operations/" + configuration.operation + (fresh ? "?fresh=asks" : "")).then(({asks, public_url}) => {
      section.hidden = !asks.available || !asks.asks.length;
      if (section.hidden) return;
      const list = make("ol", null, "rows");
      for (const ask of asks.asks) list.append(window.StatusAsks.createAskRow(ask, {changed: () => showAsks(true), publicUrl: public_url, within: "operation"}));
      const heading = make("h2", "Needs you "); heading.append(make("span", String(asks.asks.length), "count"));
      section.replaceChildren(heading, list);
      window.StatusControls.fitTitles(section);
    }).catch(() => {});
  }
  showAsks();

  // A new version of this operation replaces the open one as soon as it is published, at the same scroll position.
  // While he is part-way through writing (a response, an ask, a message about a selection) it is offered instead.
  const ARRIVED = "status-version-arrived", POLL_MILLISECONDS = 5000;
  const arrived = JSON.parse(sessionStorage.getItem(ARRIVED) || "null");
  if (arrived && arrived.report === configuration.report) {
    sessionStorage.removeItem(ARRIVED);
    requestAnimationFrame(() => scrollTo(0, arrived.scroll));
    const note = make("p", "Updated to the newest version just now. Earlier versions are in the version menu.", "version-arrived");
    note.setAttribute("role", "status");
    document.querySelector("article.sheet")?.prepend(note);
  }
  if (configuration.latest) {
    const writing = () => Boolean(document.querySelector('[data-dirty="true"]') || document.activeElement?.matches?.("textarea, input")
      || document.querySelector(".selection-panel:not([hidden])") || window.StatusAsks?.editing?.());
    const show = latest => {
      sessionStorage.setItem(ARRIVED, JSON.stringify({report: latest, scroll: scrollY}));
      location.replace(`${window.StatusControls.base}/reports/${latest}`);
    };
    let offered = false, checking = false;
    async function check() {
      if (checking || document.visibilityState !== "visible") return;
      checking = true;
      try {
        const {latest} = await request(`/api/operations/${configuration.operation}/latest`);
        if (latest === configuration.report) return;
        if (!writing()) { show(latest); return; }
        if (offered) return;
        offered = true;
        const note = make("p", "A newer version arrived. ", "version-arrived");
        note.setAttribute("role", "status");
        const open = make("button", "Show it", "quiet");
        open.type = "button";
        open.onclick = () => show(latest);
        note.append(open);
        document.querySelector("article.sheet")?.prepend(note);
      } catch { /* the service is restarting or unreachable; the next check tries again */ }
      finally { checking = false; }
    }
    setInterval(check, POLL_MILLISECONDS);
    document.addEventListener("visibilitychange", check);
  }
})();

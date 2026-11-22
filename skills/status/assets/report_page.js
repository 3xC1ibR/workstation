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
      for (const ask of asks.asks) list.append(window.StatusAsks.createAskRow(ask, {changed: () => showAsks(true), publicUrl: public_url}));
      section.replaceChildren(make("h2", asks.asks.length === 1 ? "This operation needs you" : `This operation needs you (${asks.asks.length})`), list);
    }).catch(() => {});
  }
  showAsks();
})();

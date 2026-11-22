"use strict";
(() => {
  const {make, time, request, measure, localizeTimes} = window.StatusControls;
  const configuration = JSON.parse(document.getElementById("status-configuration").textContent);
  localizeTimes();
  for (const button of document.querySelectorAll(".copy-path")) button.onclick = async () => {
    try { await navigator.clipboard.writeText(button.dataset.path); button.textContent = "Copied"; }
    catch { button.textContent = "Select the path to copy"; }
  };
  if (!configuration.delivery) return;
  let delivery = configuration.delivery, noteOpen = false, noteText = "", busy = false, failed = "";
  const panel = document.getElementById("delivery-response");
  const options = delivery.decision?.options || [];

  async function respond(action, choice) {
    if (busy) return;
    busy = true; failed = ""; render();
    try {
      const note = noteOpen && noteText.trim() && action !== "discuss" && action !== "reopen" ? noteText.trim() : undefined;
      delivery = await request("/api/delivery-response", {id: delivery.id, action, ...(choice ? {choice} : {}), ...(note ? {note} : {})});
      if (action === "accept" || action === "dismiss") { noteOpen = false; noteText = ""; }
    } catch (error) { failed = error.message + " Your note is still here."; }
    finally { busy = false; render(); }
  }

  function render() {
    const response = delivery.response, content = [];
    if (response) {
      const outcome = make("div", null, "response-outcome"), line = make("p");
      const accepted = response.type === "accepted";
      line.append(make("span", accepted ? "Accepted" : "Dismissed", accepted ? "outcome-accepted" : "outcome-dismissed"),
        ` ${time(response.at)}` + (accepted && response.choice !== "recommended_default" ? `: ${response.choice}` : accepted ? ": the recommended default" : ""));
      outcome.append(line);
      const reopen = make("button", "Change response", "quiet"); reopen.type = "button"; reopen.disabled = busy; reopen.onclick = () => respond("reopen");
      outcome.append(reopen); content.push(outcome);
      if (response.note) content.push(make("p", "Your note: " + response.note, "note text"));
      content.push(make("p", accepted ? "The agent reads this response on its next wake." : "The agent sees the dismissal and your reason on its next wake.", "note"));
    } else {
      const buttons = make("div", null, "response-buttons");
      const add = (label, handler, className) => { const button = make("button", label, className || ""); button.type = "button"; button.disabled = busy; button.onclick = handler; buttons.append(button); };
      if (delivery.recommended_default) add("Do it", () => respond("accept", "recommended_default"), "primary");
      for (const option of options) add(option, () => respond("accept", option));
      add("Dismiss", () => respond("dismiss"));
      buttons.append(make("span", null, "spacer"));
      if (!noteOpen) add("Add a note", () => { noteOpen = true; render(); panel.querySelector("textarea").focus(); }, "quiet");
      content.push(buttons);
      if (noteOpen) {
        const field = make("textarea", null, "response-note"); field.rows = 3; field.value = noteText; field.maxLength = 4000;
        field.placeholder = "A note or reason for the agent. Sent with Do it, an option, or Dismiss.";
        field.setAttribute("aria-label", "Note for the agent"); field.oninput = () => { noteText = field.value; };
        content.push(field);
      }
    }
    if (delivery.thread) {
      const discuss = make("a", "Discuss in Ribbon Field", "link-button"); discuss.href = delivery.thread;
      discuss.onclick = () => { request("/api/delivery-response", {id: delivery.id, action: "discuss"}).then(next => { delivery = next; }).catch(() => {}); };
      content[0].append(discuss);
    }
    if (failed) { const alert = make("p", failed, "failure"); alert.setAttribute("role", "alert"); content.push(alert); }
    panel.replaceChildren(...content);
  }
  render();
  request("/api/delivery-response", {id: delivery.id, action: "read"}).then(next => { if (!busy) { delivery = next; render(); } }).catch(() => {});
  measure({type: "item_open", view: "delivery", item_kind: "delivery", item: delivery.id});
  addEventListener("beforeunload", event => { if (noteOpen && noteText.trim()) { event.preventDefault(); event.returnValue = ""; } });
})();

"use strict";
(() => {
  const {make, time, moment, createChoices, createLine, request, measure, localizeTimes} = window.StatusControls;
  const configuration = JSON.parse(document.getElementById("status-configuration").textContent);
  localizeTimes();
  for (const button of document.querySelectorAll(".copy-path")) button.onclick = async () => {
    try { await navigator.clipboard.writeText(button.dataset.path); button.textContent = "Copied"; }
    catch { button.textContent = "Select the path to copy"; }
  };
  if (!configuration.delivery) return;
  let delivery = configuration.delivery, noteText = "", busy = false, failed = "";
  const panel = document.getElementById("delivery-response");
  // The recommendation leads the choices and starts chosen; the agent's other options follow it.
  const RECOMMENDED = "recommended_default";
  const choices = [...(delivery.recommended_default ? [{value: RECOMMENDED, label: delivery.recommended_default, tag: "Recommended"}] : []),
                   ...(delivery.decision?.options || []).map(option => ({value: option, label: option}))];
  let chosen = delivery.recommended_default ? RECOMMENDED : null;

  async function respond(action, choice) {
    if (busy) return;
    busy = true; failed = ""; render();
    try {
      const note = noteText.trim() && action !== "discuss" && action !== "reopen" ? noteText.trim() : undefined;
      delivery = await request("/api/delivery-response", {id: delivery.id, action, ...(choice ? {choice} : {}), ...(note ? {note} : {})});
      if (action === "accept" || action === "dismiss") noteText = "";
    } catch (error) { failed = error.message + " Your note is still here."; }
    finally { busy = false; render(); }
  }

  function render() {
    const response = delivery.response, content = [], quiet = make("div", null, "response-quiet");
    const add = (parent, label, handler, className) => { const button = make("button", label, className || ""); button.type = "button"; button.disabled = busy; button.onclick = handler; parent.append(button); };
    const typing = panel.contains(document.activeElement) && document.activeElement.classList.contains("response-note");
    const recommendation = document.querySelector(".recommendation");            // shown as the first choice while the delivery is open
    if (recommendation) recommendation.hidden = !response && choices.length > 1;
    if (response) {
      const outcome = make("div", null, "response-outcome"), line = make("p");
      const accepted = response.type === "accepted";
      const when = make("time", moment(response.at)); when.dateTime = response.at; when.title = time(response.at);
      line.append(make("span", accepted ? "Accepted" : "Dismissed", accepted ? "outcome-accepted" : "outcome-dismissed"), " ", when,
        accepted && response.choice !== RECOMMENDED ? `: ${response.choice}` : accepted ? ": the recommended default" : "");
      add(quiet, "Change response", () => respond("reopen"), "quiet");
      outcome.append(line, quiet); content.push(outcome);
      if (response.note) content.push(make("p", "Your note: " + response.note, "note text"));
    } else {
      // Choices as rows, a line for a note, and one solid button that sends what is chosen. A lone recommendation needs no row.
      if (choices.length > 1) content.push(createChoices("delivery-choice", "Choices", choices, chosen, busy, value => { chosen = value; }));
      const field = createLine("response-note", noteText, "Note for the agent", "Note for the agent", 4000, text => { noteText = text; });
      field.disabled = busy; content.push(field);
      const buttons = make("div", null, "response-buttons");
      if (choices.length) add(buttons, "Do it", () => { if (chosen) respond("accept", chosen); else panel.querySelector(".choice input").focus(); }, "primary");
      add(quiet, "Dismiss", () => respond("dismiss"), "quiet");
      buttons.append(quiet); content.push(buttons);
    }
    if (delivery.thread) {
      const discuss = make("a", "Discuss in Ribbon Field"); discuss.href = delivery.thread;
      discuss.onclick = () => { request("/api/delivery-response", {id: delivery.id, action: "discuss"}).then(next => { delivery = next; }).catch(() => {}); };
      quiet.append(discuss);
    }
    if (failed) { const alert = make("p", failed, "failure"); alert.setAttribute("role", "alert"); content.push(alert); }
    panel.replaceChildren(...content);
    if (typing) panel.querySelector(".response-note")?.focus();
  }
  render();
  request("/api/delivery-response", {id: delivery.id, action: "read"}).then(next => { if (!busy) { delivery = next; render(); } }).catch(() => {});
  measure({type: "item_open", view: "delivery", item_kind: "delivery", item: delivery.id});
  addEventListener("beforeunload", event => { if (noteText.trim()) { event.preventDefault(); event.returnValue = ""; } });
})();

"use strict";
(() => {
  const {make, time, moment, request, measure, localizeTimes} = window.StatusControls;
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
      const outcome = make("div", null, "response-outcome"), line = make("p"), quiet = make("div", null, "response-quiet");
      const accepted = response.type === "accepted";
      const when = make("time", moment(response.at)); when.dateTime = response.at; when.title = time(response.at);
      line.append(make("span", accepted ? "Accepted" : "Dismissed", accepted ? "outcome-accepted" : "outcome-dismissed"), " ", when,
        accepted && response.choice !== "recommended_default" ? `: ${response.choice}` : accepted ? ": the recommended default" : "");
      outcome.append(line);
      const reopen = make("button", "Change response", "quiet"); reopen.type = "button"; reopen.disabled = busy; reopen.onclick = () => respond("reopen");
      quiet.append(reopen); outcome.append(quiet); content.push(outcome);
      if (response.note) content.push(make("p", "Your note: " + response.note, "note text"));
    } else {
      // One solid button accepts the recommendation; the other answers are outlined, and the rest stay quiet.
      const buttons = make("div", null, "response-buttons");
      const add = (label, handler, className) => { const button = make("button", label, className || ""); button.type = "button"; button.disabled = busy; button.onclick = handler; buttons.append(button); };
      if (delivery.recommended_default) add("Do it", () => respond("accept", "recommended_default"), "primary");
      for (const option of options) add(option, () => respond("accept", option));
      const quiet = make("div", null, "response-quiet"), answers = buttons;
      buttons.append(quiet);
      const addQuiet = (label, handler) => { add(label, handler, "quiet"); quiet.append(answers.lastElementChild); };
      if (!noteOpen) addQuiet("Add a note", () => { noteOpen = true; render(); panel.querySelector("textarea").focus(); });
      addQuiet("Dismiss", () => respond("dismiss"));
      content.push(buttons);
      if (noteOpen) {
        const field = make("textarea", null, "response-note"); field.rows = 2; field.value = noteText; field.maxLength = 4000;
        field.placeholder = "A note or reason for the agent, sent with your response";
        field.setAttribute("aria-label", "Note for the agent"); field.oninput = () => { noteText = field.value; };
        content.push(field);
      }
    }
    if (failed) { const alert = make("p", failed, "failure"); alert.setAttribute("role", "alert"); content.push(alert); }
    if (delivery.thread) {
      const discuss = make("a", "Discuss in Ribbon Field"); discuss.href = delivery.thread;
      discuss.onclick = () => { request("/api/delivery-response", {id: delivery.id, action: "discuss"}).then(next => { delivery = next; }).catch(() => {}); };
      content[0].querySelector(".response-quiet").append(discuss);
    }
    panel.replaceChildren(...content);
  }
  render();
  request("/api/delivery-response", {id: delivery.id, action: "read"}).then(next => { if (!busy) { delivery = next; render(); } }).catch(() => {});
  measure({type: "item_open", view: "delivery", item_kind: "delivery", item: delivery.id});
  addEventListener("beforeunload", event => { if (noteOpen && noteText.trim()) { event.preventDefault(); event.returnValue = ""; } });
})();

"use strict";
(() => {
  const {make, time, moment, createChoices, createLine, request, measure, localizeTimes} = window.StatusControls;
  const configuration = JSON.parse(document.getElementById("status-configuration").textContent);
  localizeTimes();
  for (const button of document.querySelectorAll(".copy-path")) button.onclick = async () => {
    try { await navigator.clipboard.writeText(button.dataset.path); button.textContent = "Copied"; }
    catch { button.textContent = "Select the path to copy"; }
  };
  const history = document.querySelector(".version-history");
  document.addEventListener("click", event => { if (history?.open && !history.contains(event.target)) history.open = false; });
  document.addEventListener("keydown", event => { if (event.key === "Escape" && history?.open) { history.open = false; history.querySelector("summary").focus(); } });
  if (!configuration.delivery) return;
  // `delivery` is the version this page shows. Responses belong to the whole delivery and name the version they were given on.
  let delivery = configuration.delivery, noteText = "", busy = false, failed = "";
  let proposal = null, proposalReady = false, proposalTimer = null;
  const CONFIRM_DELAY = 600;             // a proposal that has just appeared cannot be confirmed by a click already under way
  const panel = document.getElementById("delivery-response");
  // The recommendation leads the choices and starts chosen; the agent's other options follow it.
  const RECOMMENDED = "recommended_default", options = delivery.decision?.options || [];
  const choices = [...(delivery.recommended_default ? [{value: RECOMMENDED, label: delivery.recommended_default, tag: "Recommended"}] : []),
                   ...options.map(option => ({value: option, label: option}))];
  let chosen = delivery.recommended_default ? RECOMMENDED : null;

  async function respond(action, choice, proposedNote) {
    if (busy) return;
    busy = true; failed = ""; render();
    try {
      const note = action === "discuss" || action === "reopen" ? undefined : proposedNote || noteText.trim() || undefined;
      delivery = await request("/api/delivery-response", {id: delivery.id, action, ...(choice ? {choice} : {}), ...(note ? {note} : {})});
      if (action === "accept" || action === "dismiss") { noteText = ""; proposal = null; }
    } catch (error) { failed = error.message + " Your note is still here."; }
    finally { busy = false; render(); }
  }

  // The embedded document may propose a response. It is shown here, in the page's own words, and recorded only by Confirm.
  function propose({action, choice, note}) {
    if (!delivery.latest) return false;
    if (action === "accept") {
      choice = choice === undefined ? RECOMMENDED : choice;
      if (choice === RECOMMENDED ? !delivery.recommended_default : !options.includes(choice)) return false;
    } else if (choice !== undefined) return false;
    const next = {action, choice: action === "accept" ? choice : undefined, note: typeof note === "string" && note.trim() ? note.trim() : undefined};
    if (proposal && JSON.stringify(proposal) === JSON.stringify(next)) return false;
    proposal = next; proposalReady = false;
    clearTimeout(proposalTimer);
    proposalTimer = setTimeout(() => { proposalReady = true; render(); }, CONFIRM_DELAY);
    render();
    return true;
  }
  window.StatusDelivery = {propose};

  function proposalBlock() {
    const block = make("div", null, "response-proposal"), buttons = make("div", null, "response-buttons"), quiet = make("div", null, "response-quiet");
    const what = proposal.action === "dismiss" ? "dismiss this delivery"
      : proposal.choice === RECOMMENDED ? "accept the recommended default" : `accept \u201c${proposal.choice}\u201d`;
    block.append(make("p", `The document proposes: ${what}.`));
    if (proposal.note) block.append(make("p", "With the note: " + proposal.note, "note text"));
    const confirm = make("button", "Confirm"), ignore = make("button", "Ignore", "quiet");
    confirm.type = ignore.type = "button"; confirm.disabled = busy || !proposalReady; ignore.disabled = busy;
    confirm.onclick = () => respond(proposal.action, proposal.choice, proposal.note);
    ignore.onclick = () => { proposal = null; render(); };
    quiet.append(ignore); buttons.append(confirm, quiet);
    block.append(buttons);
    return block;
  }

  function render() {
    const response = delivery.response, content = [], quiet = make("div", null, "response-quiet");
    const add = (parent, label, handler, className) => { const button = make("button", label, className || ""); button.type = "button"; button.disabled = busy; button.onclick = handler; parent.append(button); };
    const typing = panel.contains(document.activeElement) && document.activeElement.classList.contains("response-note");
    const recommendation = document.querySelector(".recommendation");            // shown as the first choice while the delivery is open
    if (recommendation) recommendation.hidden = !response && delivery.latest && choices.length > 1;
    if (response) {
      const outcome = make("div", null, "response-outcome"), line = make("p");
      const accepted = response.type === "accepted";
      const when = make("time", moment(response.at)); when.dateTime = response.at; when.title = time(response.at);
      line.append(make("span", accepted ? "Accepted" : "Dismissed", accepted ? "outcome-accepted" : "outcome-dismissed"), " ", when,
        accepted && response.choice !== RECOMMENDED ? `: ${response.choice}` : accepted ? ": the recommended default" : "");
      outcome.append(line);
      if (response.version !== delivery.id) {              // what the response refers to stays beside it, ahead of the action that changes it
        const given = delivery.response_version_number ? `version ${delivery.response_version_number}` : "an earlier version";
        outcome.append(make("p", `You ${accepted ? "accepted" : "dismissed"} ${given}; this is version ${delivery.number}.`, "response-version"));
      }
      if (delivery.latest) add(quiet, "Change response", () => respond("reopen"), "quiet");
      outcome.append(quiet); content.push(outcome);
      if (response.note) content.push(make("p", "Your note: " + response.note, "note text"));
    } else if (delivery.latest) {
      // Choices as rows, a line for a note, and one solid button that sends what is chosen. A lone recommendation needs no row.
      if (choices.length > 1) content.push(createChoices("delivery-choice", "Choices", choices, chosen, busy, value => { chosen = value; }));
      const field = createLine("response-note", noteText, "Note for the agent", "Note for the agent", 4000, text => { noteText = text; });
      field.disabled = busy; content.push(field);
      const buttons = make("div", null, "response-buttons");
      if (choices.length) add(buttons, "Do it", () => { if (chosen) respond("accept", chosen); else panel.querySelector(".choice input").focus(); }, "primary");
      add(quiet, "Dismiss", () => respond("dismiss"), "quiet");
      buttons.append(quiet); content.push(buttons);
    }
    if (!delivery.latest) content.push(make("p", "Responses are given on the latest version.", "note"));      // the notice above links to it
    if (proposal && delivery.latest) content.push(proposalBlock());
    if (failed) { const alert = make("p", failed, "failure"); alert.setAttribute("role", "alert"); content.push(alert); }
    if (delivery.thread && delivery.latest) {
      const discuss = make("a", "Discuss in Ribbon Field"); discuss.href = delivery.thread;
      discuss.onclick = () => { request("/api/delivery-response", {id: delivery.id, action: "discuss"}).then(next => { delivery = next; }).catch(() => {}); };
      quiet.append(discuss);
    }
    panel.replaceChildren(...content);
    if (typing) panel.querySelector(".response-note")?.focus();
  }
  render();
  request("/api/delivery-response", {id: delivery.id, action: "read"}).then(next => { if (!busy) { delivery = next; render(); } }).catch(() => {});
  measure({type: "item_open", view: "delivery", item_kind: "delivery", item: delivery.id});
  addEventListener("beforeunload", event => { if (noteText.trim()) { event.preventDefault(); event.returnValue = ""; } });
})();

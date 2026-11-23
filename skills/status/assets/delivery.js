"use strict";
(() => {
  const {make, time, moment, base, request, measure, localizeTimes} = window.StatusControls;
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
  let delivery = configuration.delivery, noteOpen = false, noteText = "", busy = false, failed = "";
  let proposal = null, proposalReady = false, proposalTimer = null;
  const CONFIRM_DELAY = 600;             // a proposal that has just appeared cannot be confirmed by a click already under way
  const panel = document.getElementById("delivery-response");
  const options = delivery.decision?.options || [];

  async function respond(action, choice, proposedNote) {
    if (busy) return;
    busy = true; failed = ""; render();
    try {
      const typed = noteOpen && noteText.trim() ? noteText.trim() : undefined;
      const note = action === "discuss" || action === "reopen" ? undefined : proposedNote || typed;
      delivery = await request("/api/delivery-response", {id: delivery.id, action, ...(choice ? {choice} : {}), ...(note ? {note} : {})});
      if (action === "accept" || action === "dismiss") { noteOpen = false; noteText = ""; proposal = null; }
    } catch (error) { failed = error.message + " Your note is still here."; }
    finally { busy = false; render(); }
  }

  // The embedded document may propose a response. It is shown here, in the page's own words, and recorded only by Confirm.
  function propose({action, choice, note}) {
    if (!delivery.latest) return false;
    if (action === "accept") {
      choice = choice === undefined ? "recommended_default" : choice;
      if (choice === "recommended_default" ? !delivery.recommended_default : !options.includes(choice)) return false;
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
    const block = make("div", null, "response-proposal"), buttons = make("div", null, "response-buttons");
    const what = proposal.action === "dismiss" ? "dismiss this delivery"
      : proposal.choice === "recommended_default" ? "accept the recommended default" : `accept \u201c${proposal.choice}\u201d`;
    block.append(make("p", `The document proposes: ${what}.`));
    if (proposal.note) block.append(make("p", "With the note: " + proposal.note, "note text"));
    const confirm = make("button", "Confirm"), ignore = make("button", "Ignore", "quiet");
    confirm.type = ignore.type = "button"; confirm.disabled = busy || !proposalReady; ignore.disabled = busy;
    confirm.onclick = () => respond(proposal.action, proposal.choice, proposal.note);
    ignore.onclick = () => { proposal = null; render(); };
    buttons.append(confirm, ignore);
    block.append(buttons, make("p", "Nothing is recorded until you confirm.", "note"));
    return block;
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
      if (delivery.latest) {
        const reopen = make("button", "Change response", "quiet"); reopen.type = "button"; reopen.disabled = busy; reopen.onclick = () => respond("reopen");
        quiet.append(reopen);
      }
      outcome.append(quiet); content.push(outcome);
      if (response.version !== delivery.id) {
        const given = delivery.response_version_number ? `version ${delivery.response_version_number}` : "an earlier version";
        content.push(make("p", `You ${accepted ? "accepted" : "dismissed"} ${given}; this is version ${delivery.number}.`, "response-version"));
      }
      if (response.note) content.push(make("p", "Your note: " + response.note, "note text"));
    } else if (delivery.latest) {
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
    if (!delivery.latest) {
      const later = make("p", "Responses are given on the latest version. ", "note"), link = make("a", "Open the latest version");
      link.href = `${base}/deliveries/${delivery.version}`; later.append(link); content.push(later);
    }
    if (proposal && delivery.latest) content.push(proposalBlock());
    if (failed) { const alert = make("p", failed, "failure"); alert.setAttribute("role", "alert"); content.push(alert); }
    if (delivery.thread && delivery.latest) {
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

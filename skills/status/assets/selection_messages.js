"use strict";
// Selected text on a report or a delivery goes to the conversation of the agent that published it. "Explain" sends it
// with a standing request; "Question…" with the owner's own words. The skill tells the agent to answer in the
// conversation or publish a new version of the item, whichever serves; an open report switches to a new version itself.
(() => {
  const {make, request, measure} = window.StatusControls;
  const ribbonField = window.StatusAsks?.ribbonField;
  const configuration = JSON.parse(document.getElementById("status-configuration").textContent);
  const item = target(configuration);
  const scope = document.querySelector("article.sheet");
  if (!item || !scope || !ribbonField) return;
  const QUOTE_LIMIT = 2000;
  const EXPLAIN = "Explain this: what it means, why it matters, and what you recommend.";

  function target(configuration) {
    if (configuration.conversation) {
      const c = configuration.conversation;
      return {kind: "report", view: "operation", usageKind: "operation", id: configuration.report, session: c.session, link: c.link,
        label: `your report "${c.title}" (version ${c.version})`};
    }
    const d = configuration.delivery;
    const thread = typeof d?.thread === "string" && d.thread.match(/^agentcoord:\/\/thread\/([A-Za-z0-9_-]{1,128})$/);
    if (!thread) return null;
    return {kind: "delivery", view: "delivery", usageKind: "delivery", id: d.id, session: thread[1], link: d.thread,
      label: `your delivery "${d.title}"` + (d.version_count > 1 ? ` (version ${d.versions.length - d.versions.findIndex(v => v.id === d.id)})` : "")};
  }

  // The words the agent receives: where the text is, the text and its passage quoted, and the request. How to respond
  // is the status skill's standing instruction ("Messages from the review page"), not part of each message.
  function message(selection, note) {
    const quoted = selection.text.length > QUOTE_LIMIT ? selection.text.slice(0, QUOTE_LIMIT) + "…" : selection.text;
    return [`Question from the review page about ${item.label}` + (selection.heading ? `, under "${selection.heading}"` : "") + ":",
      "", ...quoted.split("\n").map(line => "> " + line), "",
      ...(selection.context ? ["The passage it comes from:", "", ...selection.context.split("\n").map(line => "> " + line), ""] : []),
      note || EXPLAIN].join("\n");
  }

  // The heading of the part of the page the selection starts in, so the agent knows where to look.
  function headingOf(node) {
    let element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    for (; element && element !== scope.parentElement; element = element.parentElement) {
      const heading = element.matches("section, aside, details, header") &&
        element.querySelector(":scope > h1, :scope > h2, :scope > summary, :scope > .notice h2");
      if (heading) {
        const name = heading.cloneNode(true);
        name.querySelectorAll(".count").forEach(count => count.remove());      // "Workstreams", not its tally
        return name.textContent.replace(/\s+/g, " ").trim().slice(0, 120);
      }
    }
    return "";
  }

  // A short selection, often a fragment of a word or phrase, travels with the passage it was taken from.
  function contextOf(range, text) {
    const start = range.startContainer.nodeType === Node.ELEMENT_NODE ? range.startContainer : range.startContainer.parentElement;
    const block = start?.closest("p, li, td, dd, dt, h1, h2, h3, summary, figure, .event-body, .ws-head");
    const passage = block && scope.contains(block) ? block.textContent.replace(/[ \t]+/g, " ").trim() : "";
    return passage && passage !== text && passage.length <= 1200 && passage.includes(text.replace(/\s+/g, " ").slice(0, 40)) ? passage : "";
  }

  const panel = make("div", null, "selection-panel");
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Send the selected text to the agent");
  panel.hidden = true;
  document.body.append(panel);
  let selection = null, expanded = false, pressed = false, timer = null, busy = false;

  function hide() {
    panel.hidden = true; expanded = false; selection = null; busy = false;
  }
  function place(rect) {
    const width = panel.offsetWidth, margin = 8;
    const left = Math.min(Math.max(rect.left + scrollX, scrollX + margin), scrollX + document.documentElement.clientWidth - width - margin);
    panel.style.left = left + "px";
    panel.style.top = (rect.bottom + scrollY + margin) + "px";
  }
  function status(text, failed) {
    const line = make("p", text, failed ? "selection-status failure-text" : "selection-status");
    line.setAttribute("role", "status");
    return line;
  }

  async function deliver(note) {
    if (busy || !selection) return;
    busy = true;
    const text = message(selection, note.trim());
    const pending = status("Sending…");
    panel.querySelector(".selection-status")?.remove();
    panel.append(pending);
    try {
      if (ribbonField.local) await request("/api/item-message", {kind: item.kind, id: item.id, message: text});
      else {
        const {state} = await ribbonField.connect();
        if (state === "unpaired") throw Error("This browser is not paired with Ribbon Field. Pair it in Ribbon Field on your Mac, or send from the Mac.");
        if (state !== "ready") throw Error("Ribbon Field is not reachable from this address. Send from the Mac.");
        await ribbonField.send(`/api/browser/sessions/${encodeURIComponent(item.session)}/queue`,
          {message: text, requestId: "review-page-selection-" + crypto.randomUUID()});
      }
      measure({type: "item_message", view: item.view, item_kind: item.usageKind, item: item.id, action: note.trim() ? "question" : "explain"});
      const sent = status(note.trim() ? "Sent your question to the agent's conversation. " : "Asked the agent to explain. ");
      if (ribbonField.local) { const open = make("a", "Open the conversation"); open.href = item.link; sent.append(open); }
      panel.replaceChildren(sent);
      getSelection()?.removeAllRanges();
      expanded = true;                                  // the confirmation stays until it times out or a click elsewhere
      setTimeout(() => { if (panel.contains(sent)) hide(); }, 6000);
    } catch (error) {
      pending.replaceWith(status(error.message || "The message was not sent. Your text is still here; try again.", true));
    } finally { busy = false; }
  }

  function showActions() {
    const explain = make("button", "Explain", "primary");
    explain.type = "button";
    explain.title = "Send the selected text to the agent and ask for an explanation";
    explain.onclick = () => deliver("");
    const question = make("button", "Question…", "quiet");
    question.type = "button";
    question.onclick = showComposer;
    const actions = make("div", null, "selection-actions");
    actions.append(explain, question);
    panel.replaceChildren(actions);
  }
  function showComposer() {
    expanded = true;
    const quote = make("p", "“" + selection.text.replace(/\s+/g, " ").slice(0, 140) + (selection.text.length > 140 ? "…" : "") + "”", "selection-quote");
    const field = make("textarea");
    field.rows = 1;
    field.placeholder = "Your question or note for the agent";
    field.setAttribute("aria-label", "Your question or note for the agent");
    const send = make("button", "Explain", "primary");
    send.type = "button";
    field.oninput = () => { send.textContent = field.value.trim() ? "Send" : "Explain"; };
    field.onkeydown = event => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); deliver(field.value); }
    };
    send.onclick = () => deliver(field.value);
    const cancel = make("button", "Cancel", "quiet");
    cancel.type = "button";
    cancel.onclick = hide;
    const actions = make("div", null, "selection-actions");
    actions.append(send, cancel);
    panel.replaceChildren(quote, field, actions);
    field.focus({preventScroll: true});
  }

  // A settled selection inside the item's text shows the panel under it; a selection anywhere else, or none, hides it.
  function evaluate() {
    if (pressed || expanded) return;
    const current = getSelection();
    const text = current && !current.isCollapsed ? current.toString().trim() : "";
    if (text.length < 2 || !current.rangeCount) { hide(); return; }
    const range = current.getRangeAt(0);
    const start = range.startContainer.nodeType === Node.ELEMENT_NODE ? range.startContainer : range.startContainer.parentElement;
    if (!scope.contains(range.commonAncestorContainer) || start?.closest("input, textarea, button, .response-editor, #delivery-response, .embedded")) {
      hide(); return;
    }
    selection = {text, heading: headingOf(range.startContainer), context: contextOf(range, text)};
    showActions();
    panel.hidden = false;
    const rects = range.getClientRects();
    place(rects.length ? rects[rects.length - 1] : range.getBoundingClientRect());
  }
  const schedule = () => { clearTimeout(timer); timer = setTimeout(evaluate, 300); };
  document.addEventListener("selectionchange", schedule);
  document.addEventListener("pointerdown", event => {
    if (panel.contains(event.target)) return;
    pressed = true;
    if (expanded && !busy) hide();
  });
  // A long press that starts a native selection on a phone ends in pointercancel, not pointerup.
  for (const type of ["pointerup", "pointercancel"]) document.addEventListener(type, () => { pressed = false; schedule(); });
  document.addEventListener("keydown", event => { if (event.key === "Escape" && !panel.hidden) { hide(); } });
})();

"use strict";
// Asks belong to Ribbon Field. This component shows one ask in full and, when this browser is paired with
// Ribbon Field on the same address, sends the user's resolution straight to Ribbon Field. Nothing is stored here.
(() => {
  const {make, time, elapsed, request, measure} = window.StatusControls;
  const LABELS = {answered: "Send answer", done: "Done", not_done: "Not done", approved: "Approve", declined: "Decline",
                  accepted: "Accept", changes_requested: "Request changes", granted: "Grant", dismissed: "Dismiss"};
  const OUTCOMES = {answered: "Answered", done: "Marked done", not_done: "Marked not done", approved: "Approved", declined: "Declined",
                    accepted: "Accepted", changes_requested: "Changes requested", granted: "Granted", dismissed: "Dismissed", snoozed: "Snoozed"};
  const drafts = new Map();          // ask id -> {open, text, error, busy}; survives list refreshes
  const draft = id => drafts.get(id) || drafts.set(id, {open: false, text: "", error: "", busy: false}).get(id);
  let connection = null;             // {state: "local"} | {state: "ready", token} | {state: "unpaired"} | {state: "elsewhere"}
  const LOCAL = ["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);

  // Ribbon Field answers at the root of the tailnet address this page shares. Anywhere else there is nothing to ask.
  async function connect(renew = false) {
    if (connection && !renew) return connection;
    // On this Mac the Status service forwards answers to Ribbon Field's loopback interface; no pairing is needed.
    if (LOCAL) return (connection = {state: "local"});
    try {
      const response = await fetch("/api/browser/config", {cache: "no-store", credentials: "same-origin"});
      const body = await response.json().catch(() => null);
      connection = response.ok && body && typeof body.token === "string" && "askKinds" in body ? {state: "ready", token: body.token}
        : response.status === 401 ? {state: "unpaired"} : {state: "elsewhere"};
    } catch { connection = {state: "elsewhere"}; }
    return connection;
  }
  async function send(path, body, retried = false) {
    const {state, token} = await connect();
    if (state !== "ready") throw Error("Ribbon Field is not reachable from this page.");
    let response;
    try {
      response = await fetch(path, {method: "POST", cache: "no-store", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-Agent-Coord-Token": token}, body: JSON.stringify(body)});
    } catch { throw Error("Could not reach Ribbon Field. Your text is still here; try again."); }
    if (response.status === 403 && !retried) { await connect(true); return send(path, body, true); }     // Ribbon Field restarted
    const result = await response.json().catch(() => ({}));
    if (response.status === 401) { connection = {state: "unpaired"}; throw Error("This browser is no longer paired with Ribbon Field."); }
    if (!response.ok) throw Error(result.error || "Ribbon Field did not accept this. Your text is still here.");
    return result;
  }

  const LINK = /(https?:\/\/[^\s<>"')\]]+)/g;
  function prose(text, className) {
    const block = make("div", null, className);
    for (const paragraph of text.split(/\n{2,}/)) {
      const node = make("p");
      paragraph.split(LINK).forEach((part, index) => {
        if (index % 2 === 0) { node.append(part); return; }
        const address = part.replace(/[.,;:]+$/, ""), link = make("a", address);
        link.href = address; link.target = "_blank"; link.rel = "noreferrer noopener";
        node.append(link, part.slice(address.length));
      });
      block.append(node);
    }
    return block;
  }
  const snoozeChoices = () => {
    const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1); tomorrow.setHours(9, 0, 0, 0);
    return [["For 1 hour", Date.now() + 3600e3], ["For 3 hours", Date.now() + 3 * 3600e3], ["Until tomorrow, 9 AM", tomorrow.getTime()],
            ["For a week", Date.now() + 7 * 86400e3]];
  };

  // Build one ask row. `changed(message)` is called after Ribbon Field accepts a resolution or a snooze.
  function createAskRow(ask, {changed, publicUrl}) {
    const state = draft(ask.id), item = make("li", null, "row ask");
    item.dataset.key = "ask-" + ask.id; item.dataset.kind = "ask"; item.dataset.state = ask.blocking ? "blocking" : "waiting";
    const marker = make("span", null, "marker"); marker.setAttribute("aria-hidden", "true");
    const main = make("div", null, "row-main"), toggle = make("button", null, "ask-toggle");
    const stamp = make("time", elapsed(ask.created_at)); stamp.dateTime = ask.created_at; stamp.title = time(ask.created_at);
    const aside = make("span", null, "row-aside"); aside.append(stamp);
    toggle.type = "button"; toggle.append(make("span", ask.title, "row-title"), aside);       // the heading strip, age and chevron toggle together
    const kind = ask.kind ? ask.kind[0].toUpperCase() + ask.kind.slice(1) : "Ask";
    const meta = make("p", null, "row-meta");
    const parts = [ask.blocking && make("span", "Blocking", "flag-blocking"), kind + (ask.effort_minutes ? `, ${ask.effort_minutes} min` : ""),
      ask.thread_title || ask.project_label, ask.overdue && make("span", "Overdue", "flag-attention"),
      ask.stale && make("span", ask.thread_closed ? "Thread closed" : "Agent inactive", "flag-attention")].filter(Boolean);
    parts.forEach((part, index) => { if (index) meta.append(" · "); meta.append(part); });
    const rest = [ask.detail, ask.unblocks && "Unblocks: " + ask.unblocks, ask.context].filter(Boolean).join("\n\n");
    const preview = rest ? make("p", rest.replace(/\s+/g, " "), "row-summary") : null;
    const body = make("div", null, "ask-detail"); body.id = `ask-${ask.id}-detail`;
    toggle.setAttribute("aria-controls", body.id);
    main.append(toggle, meta); if (preview) main.append(preview); main.append(body);
    item.append(marker, main);

    async function resolve(payload, action) {
      if (state.busy) return;
      state.busy = true; state.error = ""; draw();
      try {
        if (connection && connection.state === "local") {
          await request("/api/ask-resolution", {id: ask.id, body: payload, snooze: payload.until !== undefined});
        } else {
          await send(payload.until === undefined ? `/api/browser/asks/${ask.id}` : `/api/browser/asks/${ask.id}/snooze`, payload);
        }
        drafts.delete(ask.id);
        measure({type: "ask_resolution", view: "review", item_kind: "ask", item: String(ask.id), action});
        changed(`${OUTCOMES[action] || "Resolved"}. Ribbon Field ${action === "snoozed" ? "will show it again later" : "has told the agent"}.`, ask.id);
      } catch (error) { state.busy = false; state.error = error.message; draw(); }
    }

    function controls() {
      const panel = make("div", null, "ask-response"), text = state.text.trim();
      const add = (parent, label, handler, className) => {
        const button = make("button", label, className || ""); button.type = "button"; button.disabled = state.busy; button.onclick = handler;
        parent.append(button); return button;
      };
      const decision = (ask.resolutions || []).includes("answered");
      if ((ask.options || []).length) {
        const options = make("div", null, "ask-options"); options.setAttribute("role", "group"); options.setAttribute("aria-label", "Choices");
        for (const option of ask.options) add(options, option, () => resolve({resolution: "answered", option, ...(state.text.trim() ? {note: state.text.trim()} : {})}, "answered"));
        panel.append(options);
      }
      const field = make("textarea", null, "ask-note"); field.rows = 2; field.maxLength = 8000; field.value = state.text; field.disabled = state.busy;
      field.placeholder = !decision ? "Add a note for the agent (optional)" : (ask.options || []).length ? "Or write your own answer, or a note to send with a choice" : "Your answer";
      field.setAttribute("aria-label", decision ? "Your answer or a note" : "Note for the agent");
      const buttons = make("div", null, "ask-buttons");
      field.oninput = () => { state.text = field.value; const answer = buttons.querySelector("[data-answer]"); if (answer) answer.disabled = state.busy || !field.value.trim(); };
      panel.append(field);
      const note = () => (state.text.trim() ? {note: state.text.trim()} : {});
      for (const resolution of ask.resolutions || []) {
        if (resolution === "dismissed") continue;
        if (resolution === "answered") {
          const answer = add(buttons, LABELS.answered, () => resolve({resolution, answer: state.text.trim()}, resolution), "primary");
          answer.dataset.answer = "true"; answer.disabled = state.busy || !text;
        } else add(buttons, LABELS[resolution] || resolution.replace(/_/g, " "), () => resolve({resolution, ...note()}, resolution));
      }
      const later = make("details", null, "ask-snooze"), menu = make("div", null, "ask-snooze-choices");
      later.append(make("summary", "Snooze"), menu);
      for (const [label, until] of snoozeChoices()) add(menu, label, () => resolve({until: Math.floor(until / 1000)}, "snoozed"), "quiet");
      buttons.append(later);
      if ((ask.resolutions || []).includes("dismissed")) add(buttons, "Dismiss", () => resolve({resolution: "dismissed", ...note()}, "dismissed"), "quiet");
      panel.append(buttons);
      return panel;
    }
    function links() {
      const line = make("p", null, "ask-links"), thread = make("a", "Open the thread in Ribbon Field"); thread.href = ask.thread_link; line.append(thread);
      if (/^https?:\/\//.test(ask.link || "")) {
        const where = make("a", "Open where this is done"); where.href = ask.link; where.target = "_blank"; where.rel = "noreferrer noopener";
        line.append(" · ", where);
      }
      return line;
    }
    function unavailable() {
      const note = make("p", null, "ask-unavailable");
      if (connection.state === "unpaired") {
        const pair = make("a", "Open Ribbon Field"); pair.href = "/";
        const local = make("a", "http://127.0.0.1:8766/"); local.href = "http://127.0.0.1:8766/";
        note.append("This browser is not paired with Ribbon Field, so an answer cannot be sent from this address. On the Mac itself, answer at ", local,
                    " with no pairing. On another device, create a pairing link in Ribbon Field on your Mac, or answer there. ", pair);
      } else if (publicUrl && !location.href.startsWith(publicUrl)) {
        const address = make("a", publicUrl + "/"); address.href = publicUrl + "/";
        note.append("Answers are sent through Ribbon Field's tailnet address. Open this page at ", address, " to answer here, or answer in Ribbon Field.");
      } else note.append("Ribbon Field is not reachable at this address, so answer this ask in Ribbon Field.");
      return note;
    }
    function draw() {
      item.dataset.open = String(state.open); toggle.setAttribute("aria-expanded", String(state.open));
      if (preview) preview.hidden = state.open;
      body.hidden = !state.open;
      if (!state.open) { body.replaceChildren(); return; }
      const content = [];
      if (ask.detail) content.push(prose(ask.detail, "ask-text"));
      if (ask.unblocks) content.push(prose("Unblocks: " + ask.unblocks, "ask-text"));
      if (ask.context) content.push(prose(ask.context, "ask-text ask-context"));
      content.push(!connection ? make("p", "Checking Ribbon Field…", "note") : ["ready", "local"].includes(connection.state) ? controls() : unavailable());
      if (state.error) { const alert = make("p", state.error, "failure"); alert.setAttribute("role", "alert"); content.push(alert); }
      content.push(links());
      const focused = body.contains(document.activeElement) && document.activeElement.className;
      body.replaceChildren(...content);
      if (focused === "ask-note") body.querySelector(".ask-note")?.focus();
    }
    toggle.onclick = async () => {
      state.open = !state.open; draw();
      if (state.open && !connection) { await connect(); if (state.open) draw(); }
    };
    draw();
    if (state.open && !connection) connect().then(() => { if (state.open) draw(); });
    return item;
  }
  // True while the user is part-way through an answer, so a list refresh must not disturb it.
  const editing = () => [...drafts.values()].some(state => state.busy) || Boolean(document.activeElement?.closest?.(".ask-detail"));
  window.StatusAsks = {createAskRow, editing};
})();

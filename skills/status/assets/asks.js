"use strict";
// Asks belong to Ribbon Field. This component shows one ask in full and, when this browser is paired with
// Ribbon Field on the same address, sends the user's resolution straight to Ribbon Field. Nothing is stored here.
(() => {
  const {make, time, elapsed, listTitle, fitTitles, addressText, createChoices, createLine, request, measure, destination} = window.StatusControls;
  const LABELS = {answered: "Send", done: "Done", not_done: "Not done", approved: "Approve", declined: "Decline",
                  accepted: "Accept", changes_requested: "Request changes", granted: "Grant", dismissed: "Dismiss"};
  const OUTCOMES = {answered: "Answered", done: "Marked done", not_done: "Marked not done", approved: "Approved", declined: "Declined",
                    accepted: "Accepted", changes_requested: "Changes requested", granted: "Granted", dismissed: "Dismissed", snoozed: "Snoozed"};
  const drafts = new Map();          // ask id -> {open, text, option, error, busy}; survives list refreshes
  const draft = id => drafts.get(id) || drafts.set(id, {open: false, text: "", option: null, error: "", busy: false}).get(id);
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
  // A page of the review page or another application on this host opens in this tab; any other address in a new one.
  function linkTo(link, address, publicUrl) {
    const target = destination(address, publicUrl);
    if (target && (target.kind === "page" || target.kind === "application")) link.href = target.href;
    else { link.href = address; link.target = "_blank"; link.rel = "noreferrer noopener"; }
    return link;
  }
  function linked(node, text, publicUrl) {
    text.split(LINK).forEach((part, index) => {
      if (index % 2 === 0) { node.append(part); return; }
      const address = part.replace(/[.,;:]+$/, "");
      node.append(linkTo(addressText(make("a"), address), address, publicUrl), part.slice(address.length));
    });
    return node;
  }
  // The agent's text, with web addresses linked. A line that begins with a number becomes a step with a hanging indent.
  function prose(text, className, publicUrl) {
    const block = make("div", null, className);
    for (const paragraph of text.split(/\n{2,}/)) {
      let plain = [];
      const flush = () => { if (plain.length) block.append(linked(make("p"), plain.join("\n"), publicUrl)); plain = []; };
      for (const line of paragraph.split("\n")) {
        const step = line.match(/^\s*(\d{1,2}[.)])\s+(.*)$/);
        if (step) { flush(); const node = make("p", null, "step"); node.append(make("span", step[1]), linked(make("span"), step[2], publicUrl)); block.append(node); }
        else plain.push(line);
      }
      flush();
    }
    return block;
  }
  // The same words the Status service sends on the local address (ribbon_field_asks.reply_message).
  const replyMessage = (ask, text) => `Reply to ask #${ask.id} (${ask.title}), sent from the review page without resolving it:\n\n${text}\n\n` +
    `Ask #${ask.id} is still open. Resolve it, replace it or withdraw it once you have acted on this reply.`;
  const snoozeChoices = () => {
    const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1); tomorrow.setHours(9, 0, 0, 0);
    return [["For 1 hour", Date.now() + 3600e3], ["For 3 hours", Date.now() + 3 * 3600e3], ["Until tomorrow, 9 AM", tomorrow.getTime()],
            ["For a week", Date.now() + 7 * 86400e3]];
  };

  // Build one ask row. `changed(message)` is called after Ribbon Field accepts a resolution or a snooze.
  function createAskRow(ask, {changed, publicUrl, within}) {
    const state = draft(ask.id), item = make("li", null, "row ask");
    item.dataset.key = "ask-" + ask.id; item.dataset.kind = "ask"; item.dataset.state = ask.blocking ? "blocking" : "waiting";
    const marker = make("span", null, "marker"); marker.setAttribute("aria-hidden", "true");
    const main = make("div", null, "row-main"), toggle = make("button", null, "ask-toggle");
    const stamp = make("time", elapsed(ask.created_at)); stamp.dateTime = ask.created_at; stamp.title = time(ask.created_at);
    const aside = make("span", null, "row-aside"); aside.append(stamp);
    toggle.type = "button"; toggle.append(make("span", listTitle(ask.title), "row-title"), aside);       // the whole heading line toggles; the margin chevron shows it
    // A decision is the ordinary ask, so only the other kinds are named. Inside an operation's report its own name is left out.
    const kind = ask.kind && ask.kind !== "decision" ? ask.kind[0].toUpperCase() + ask.kind.slice(1) : "";
    const effort = ask.effort_minutes ? `${ask.effort_minutes} min` : "";
    // The line under the title has one order: state words, then what it costs him, then where it comes from.
    const meta = make("p", null, "row-meta"), cost = [kind, effort].filter(Boolean).join(", ");
    const parts = [ask.blocking && make("span", "Blocking", "flag-blocking"), ask.overdue && make("span", "Overdue", "flag-attention"),
      ask.stale && make("span", ask.thread_closed ? "Thread closed" : "Agent inactive", "flag-attention"),
      ask.replied_at && make("span", "Replied", "flag-needs"), cost && make("span", cost, "flag-needs"),
      within !== "operation" && (ask.thread_title || ask.project_label)].filter(Boolean);
    parts.forEach((part, index) => { if (index) meta.append(" · "); meta.append(part); });
    meta.hidden = !parts.length;
    // At phone width the age ends this line, joined to the word before it so that it never stands alone on a line.
    if (parts.length) { const age = make("span", "\u00a0·\u00a0", "row-age"); age.append(stamp.cloneNode(true)); meta.append(age); }
    const body = make("div", null, "ask-detail"); body.id = `ask-${ask.id}-detail`;
    toggle.setAttribute("aria-controls", body.id);
    main.append(toggle, meta, body);
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
      const panel = make("div", null, "ask-response");
      const add = (parent, label, handler, className) => {
        const button = make("button", label, className || ""); button.type = "button"; button.disabled = state.busy; button.onclick = handler;
        parent.append(button); return button;
      };
      const decision = (ask.resolutions || []).includes("answered"), options = ask.options || [];
      if (options.length) panel.append(createChoices(`ask-${ask.id}-choice`, "Choices", options.map(option => ({value: option, label: option})),
        state.option, state.busy, option => { state.option = option; }));
      const field = createLine("ask-note", state.text, !decision ? "Note for the agent" : options.length ? "Other answer or note" : "Your answer",
        decision ? "Your answer or a note" : "Note for the agent", 8000, text => { state.text = text; });
      field.disabled = state.busy;
      panel.append(field);
      const buttons = make("div", null, "ask-buttons"), note = () => (state.text.trim() ? {note: state.text.trim()} : {});
      // "Send answer" sends the chosen row with the words as its note, or the words alone. With neither it leads to where an answer goes.
      const answer = () => {
        if (state.option) resolve({resolution: "answered", option: state.option, ...note()}, "answered");
        else if (state.text.trim()) resolve({resolution: "answered", answer: state.text.trim()}, "answered");
        else (panel.querySelector(".choice input") || field).focus();
      };
      let primary = "primary";                 // the first resolution is the panel's one solid button
      for (const resolution of ask.resolutions || []) {
        if (resolution === "dismissed") continue;
        if (resolution === "answered") add(buttons, LABELS.answered, answer, primary);
        else add(buttons, LABELS[resolution] || resolution.replace(/_/g, " "), () => resolve({resolution, ...note()}, resolution), primary);
        primary = "";
      }
      // A reply sends his own words to the asking conversation and leaves the ask open: for when no offered answer fits.
      const reply = async () => {
        const text = state.text.trim();
        if (!text) { field.focus(); return; }
        if (state.busy) return;
        state.busy = true; state.error = ""; draw();
        try {
          if (connection && connection.state === "local") await request("/api/ask-reply", {id: ask.id, text});
          else await send(`/api/browser/sessions/${encodeURIComponent(ask.session_id)}/queue`,
            {message: replyMessage(ask, text), requestId: "review-page-reply-" + crypto.randomUUID()});
          state.text = ""; state.option = undefined; state.busy = false;
          await measure({type: "ask_resolution", view: "review", item_kind: "ask", item: String(ask.id), action: "replied"});
          ask.replied_at = new Date().toISOString();
          draw();
          changed("Replied in the conversation. The ask stays open until the agent acts.", null);
        } catch (error) { state.busy = false; state.error = error.message; draw(); }
      };
      const replyButton = add(buttons, "Reply", reply);
      replyButton.title = "Send your words to the agent's conversation and keep the ask open";
      buttons.append(make("span", null, "spacer"));
      const later = make("details", null, "ask-snooze"), menu = make("div", null, "ask-snooze-choices");
      later.append(make("summary", "Snooze"), menu);
      for (const [label, until] of snoozeChoices()) add(menu, label, () => resolve({until: Math.floor(until / 1000)}, "snoozed"), "quiet");
      buttons.append(later);
      if ((ask.resolutions || []).includes("dismissed")) add(buttons, "Dismiss", () => resolve({resolution: "dismissed", ...note()}, "dismissed"), "quiet");
      buttons.append(discuss());
      panel.append(buttons);
      return panel;
    }
    // What answering enables, and the place where the work is done, stay beside the controls.
    function lead() {
      if (!ask.unblocks && !/^https?:\/\//.test(ask.link || "")) return null;
      const line = make("p", null, "ask-lead");
      if (ask.unblocks) linked(line, "Unblocks: " + ask.unblocks, publicUrl);
      if (/^https?:\/\//.test(ask.link || "")) {
        let host = ask.link; try { host = new URL(ask.link).hostname.replace(/^www\./, ""); } catch { /* keep the address as written */ }
        const where = linkTo(make("a", "Open " + host), ask.link, publicUrl); where.title = ask.link;
        if (ask.unblocks) line.append(" ");
        line.append(where);
      }
      return line;
    }
    // The conversation itself is one step away for anything the controls here do not cover.
    const discuss = () => {
      const link = make("a", "Reply in conversation", "quiet-link"); link.href = ask.thread_link;
      link.title = "Open this conversation in Ribbon Field";
      return link;
    };
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
      note.append(" ", discuss());                  // the conversation is always one step away, also when nothing can be sent from here
      return note;
    }
    function draw() {
      item.dataset.open = String(state.open); toggle.setAttribute("aria-expanded", String(state.open));
      body.hidden = !state.open;
      if (item.isConnected) fitTitles(item);             // an open ask shows its whole title
      if (!state.open) { body.replaceChildren(); return; }
      // The response comes first, directly under the title; the whole question and its context follow.
      const content = [lead(), !connection ? make("p", "Checking Ribbon Field…", "note") : ["ready", "local"].includes(connection.state) ? controls() : unavailable()].filter(Boolean);
      if (state.error) { const alert = make("p", state.error, "failure"); alert.setAttribute("role", "alert"); content.push(alert); }
      if (ask.replied_at) content.push(make("p", `You replied in the conversation ${elapsed(ask.replied_at)}. The ask stays open until the agent acts.`, "note ask-replied"));
      if (ask.detail) content.push(prose(ask.detail, "ask-text", publicUrl));
      if (ask.context) content.push(prose(ask.context, "ask-text ask-context", publicUrl));
      const focused = body.contains(document.activeElement) && document.activeElement.className;
      body.replaceChildren(...content);
      if (focused && focused.includes("ask-note")) body.querySelector(".ask-note")?.focus();
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

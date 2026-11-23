"use strict";
// Host side of the bridge between an item's page and the sandboxed document embedded in it. The document is built
// by an agent and has no access to this page or its origin. It can only send the messages below, and this script
// decides what each one does. A message is accepted only from the item's own frame, as a plain object with a known
// type and sizes within limits; everything else is ignored without a reply.
(() => {
  const {request, measure, destination} = window.StatusControls;
  const frame = document.getElementById("embedded-document");
  if (!frame) return;
  const {kind, item, latest, public_url: publicUrl} = JSON.parse(document.getElementById("status-configuration").textContent).embedded;
  const HEIGHT_MINIMUM = 120, HEIGHT_MAXIMUM = 20000, STATE_LIMIT = 64 * 1024, CHOICE_LIMIT = 300, NOTE_LIMIT = 4000;
  const SAVE_INTERVAL = 1000, PROPOSAL_INTERVAL = 1000, OPEN_INTERVAL = 500;
  const view = kind === "delivery" ? "delivery" : "operation";
  // The frame's origin is opaque, so a reply cannot name it; the reply goes to whatever the item's frame now holds.
  const reply = message => { try { frame.contentWindow.postMessage(message, "*"); } catch { /* the frame is gone */ } };
  const reference = value => typeof value === "number" && Number.isSafeInteger(value) ? value : undefined;

  if (item) frame.addEventListener("load", () => measure({type: "item_open", view, item_kind: view, item, action: "interactive_document"}), {once: true});

  // Saves are sent at most once a second; a newer state replaces one that has not been sent yet.
  let unsent = null, timer = null, sentAt = 0, proposedAt = 0, openedAt = 0;
  function sendState() {
    clearTimeout(timer); timer = null;
    if (!unsent) return;
    const {state, references} = unsent;
    unsent = null; sentAt = Date.now();
    request("/api/document-state", {kind, id: item, state}).then(
      saved => references.forEach(request_ => reply({type: "status:state:saved", ok: true, saved_at: saved.saved_at, request: request_})),
      () => references.forEach(request_ => reply({type: "status:state:saved", ok: false, request: request_})));
  }
  addEventListener("pagehide", sendState);
  document.addEventListener("visibilitychange", () => { if (document.hidden) sendState(); });

  // The document asks; this page decides. Pages of the review page, other applications on this host (framed by the
  // embedded view) and Ribbon Field links replace this tab; another website opens a new one. Anything else is ignored.
  function open(href) {
    const target = destination(href, publicUrl, item);
    if (!target || Date.now() - openedAt < OPEN_INTERVAL) return;
    openedAt = Date.now();
    if (target.kind === "website") window.open(target.href, "_blank", "noopener,noreferrer");
    else location.assign(target.href);
  }

  const handlers = {
    "status:resize": ({height}) => {
      if (typeof height !== "number" || !Number.isFinite(height)) return;
      frame.style.height = Math.min(HEIGHT_MAXIMUM, Math.max(HEIGHT_MINIMUM, Math.ceil(height))) + "px";
    },
    "status:state:save": data => {
      if (!item || !("state" in data)) return;
      let size;
      try { size = new TextEncoder().encode(JSON.stringify(data.state)).length; } catch { return; }
      if (!(size <= STATE_LIMIT)) return;
      if (!latest) { reply({type: "status:state:saved", ok: false, request: reference(data.request)}); return; }   // an earlier version never overwrites
      unsent = {state: data.state, references: [...(unsent ? unsent.references : []), reference(data.request)]};
      if (!timer) timer = setTimeout(sendState, Math.max(0, SAVE_INTERVAL - (Date.now() - sentAt)));
    },
    "status:state:load": data => {
      if (!item) { reply({type: "status:state", available: false, state: null, saved_at: null, request: reference(data.request)}); return; }
      request(`/api/document-state/${kind}/${item}`).then(
        saved => reply({type: "status:state", available: true, state: saved.state, saved_at: saved.saved_at, request: reference(data.request)}),
        () => reply({type: "status:state", available: false, state: null, saved_at: null, request: reference(data.request)}));
    },
    // A proposal is only shown, in this page's own response panel. Recording it takes the user's Confirm there.
    "status:propose": ({action, choice, note}) => {
      if (!window.StatusDelivery || (action !== "accept" && action !== "dismiss")) return;
      if (choice !== undefined && (typeof choice !== "string" || !choice || choice.length > CHOICE_LIMIT)) return;
      if (note !== undefined && (typeof note !== "string" || note.length > NOTE_LIMIT)) return;
      if (Date.now() - proposedAt < PROPOSAL_INTERVAL) return;
      if (window.StatusDelivery.propose({action, choice, note})) proposedAt = Date.now();
    },
    "status:open": ({href}) => open(href),
  };

  addEventListener("message", event => {
    const data = event.data;
    if (event.source !== frame.contentWindow || data === null || typeof data !== "object") return;
    if (Object.getPrototypeOf(data) !== Object.prototype || typeof data.type !== "string" || !Object.hasOwn(handlers, data.type)) return;
    handlers[data.type](data);
  });
  // A document that loaded before this script was listening repeats its height and unanswered requests when told.
  reply({type: "status:ready"});
})();

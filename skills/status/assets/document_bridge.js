"use strict";
// Helper for an interactive document shown inside the review page. Load it from the document with
//   <script src="<review page address>/document_bridge.js"></script>
// The document runs in a sandbox without the page's origin, so it reaches the page only through window.postMessage.
// This file sends those messages: it keeps the frame as tall as the document, hands link clicks to the page, and
// offers window.StatusDocument for saved state and proposed responses. Opened outside the review page, the
// document still works; saving and loading then report that no page answered.
(() => {
  if (window.StatusDocument) return;
  const page = window.parent !== window ? window.parent : null;
  const send = message => { if (page) page.postMessage(message, "*"); };
  const waiting = new Map();
  let sequence = 0, reported = 0;

  addEventListener("message", event => {
    const data = event.data;
    if (event.source !== page || !data || typeof data !== "object") return;
    if (data.type === "status:ready") {                 // the page began listening after this document did: say again what it missed
      reported = 0; resize();
      for (const {message} of waiting.values()) send(message);
      return;
    }
    if (!waiting.has(data.request)) return;
    const {type, settle} = waiting.get(data.request);
    if (data.type === type) { waiting.delete(data.request); settle(data); }
  });
  function ask(message, type) {
    return new Promise((resolve, reject) => {
      if (!page) { reject(Error("This document is not open inside the review page.")); return; }
      const request = ++sequence;
      const timer = setTimeout(() => { waiting.delete(request); reject(Error("The review page did not answer.")); }, 15000);
      waiting.set(request, {type, message: {...message, request}, settle: data => { clearTimeout(timer); resolve(data); }});
      send({...message, request});
    });
  }

  // Keep the frame as tall as the document. The root element's own box is the content height, whatever the frame's height.
  function resize(height) {
    height = Math.ceil(typeof height === "number" ? height : document.documentElement.getBoundingClientRect().height);
    if (height !== reported) { reported = height; send({type: "status:resize", height}); }
  }
  if (window.ResizeObserver) new ResizeObserver(() => resize()).observe(document.documentElement);
  addEventListener("load", () => resize());
  resize();

  // The sandbox cannot navigate the page, so a link click asks the page to open the address. Links inside the document still work.
  document.addEventListener("click", event => {
    const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
    if (!page || !anchor || event.defaultPrevented || event.button !== 0 || anchor.hasAttribute("download")) return;
    if (anchor.getAttribute("href").startsWith("#") || !/^(?:https?|agentcoord):/.test(anchor.href)) return;
    event.preventDefault();
    send({type: "status:open", href: anchor.href});
  });

  window.StatusDocument = {
    embedded: Boolean(page),
    // Save any JSON value up to 64 KB for this item. It is the document's own data, not a response from the reader.
    saveState: state => ask({type: "status:state:save", state}, "status:state:saved").then(result => {
      if (!result.ok) throw Error("The review page could not save this state.");
      return {saved_at: result.saved_at};
    }),
    // Resolves with {state, saved_at}; state is null when nothing has been saved.
    loadState: () => ask({type: "status:state:load"}, "status:state").then(result => {
      if (!result.available) throw Error("The review page could not load the saved state.");
      return {state: result.state, saved_at: result.saved_at};
    }),
    // Ask the page to show a proposed response to a delivery. Only the reader's own Confirm on the page records it.
    propose: ({action, choice, note}) => send({type: "status:propose", action, ...(choice === undefined ? {} : {choice}), ...(note === undefined ? {} : {note})}),
    open: href => send({type: "status:open", href: new URL(href, location.href).href}),
    resize,
  };
})();

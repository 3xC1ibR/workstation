"use strict";
(() => {
  const element = id => document.getElementById(id);
  const pickers = new Map();
  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const time = value => new Date(value).toLocaleString(undefined, {year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"});
  function createPicker(select) {
    const wrapper = make("div", null, "picker"), button = make("button", null, "picker-trigger");
    const value = make("span"), options = make("div", null, "picker-options");
    let active = select.selectedIndex, prefix = "", typedAt = 0;
    button.type = "button"; button.id = select.id + "-trigger"; value.id = select.id + "-value";
    options.id = select.id + "-options"; options.hidden = true;
    button.setAttribute("role", "combobox"); button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false"); button.setAttribute("aria-controls", options.id);
    button.setAttribute("aria-labelledby", select.id + "-label " + value.id);
    for (const attribute of ["aria-required", "aria-describedby"]) {
      if (select.hasAttribute(attribute)) button.setAttribute(attribute, select.getAttribute(attribute));
    }
    options.setAttribute("role", "listbox"); options.setAttribute("aria-labelledby", select.id + "-label");
    element(select.id + "-label").htmlFor = button.id;
    select.before(wrapper); wrapper.append(select, button, options); button.append(value);
    select.classList.add("picker-native"); select.tabIndex = -1; select.setAttribute("aria-hidden", "true");
    function highlight(index, scroll = false) {
      active = Math.max(0, Math.min(index, select.options.length - 1));
      [...options.children].forEach((option, position) => { option.dataset.active = String(position === active); });
      const current = options.children[active];
      if (!options.hidden && current) {
        button.setAttribute("aria-activedescendant", current.id);
        if (scroll) current.scrollIntoView({block: "nearest"});
      }
    }
    function close() {
      options.hidden = true; button.setAttribute("aria-expanded", "false");
      button.removeAttribute("aria-activedescendant"); prefix = "";
    }
    function sync() {
      const highlightedValue = options.children[active]?.dataset.value;
      value.textContent = select.selectedOptions[0]?.textContent || ""; button.title = value.textContent;
      options.replaceChildren();
      [...select.options].forEach((entry, index) => {
        const option = make("div", entry.textContent, "picker-option");
        option.id = select.id + "-option-" + index; option.dataset.value = entry.value;
        option.setAttribute("role", "option"); option.setAttribute("aria-selected", String(entry.selected));
        option.addEventListener("pointermove", () => highlight(index));
        option.addEventListener("mousedown", event => event.preventDefault());
        option.onclick = () => choose(index); options.append(option);
      });
      const preserved = [...select.options].findIndex(entry => entry.value === highlightedValue);
      highlight(!options.hidden && preserved >= 0 ? preserved : select.selectedIndex);
    }
    function open() {
      for (const picker of pickers.values()) picker.close();
      button.focus({preventScroll: true});
      options.hidden = false; button.setAttribute("aria-expanded", "true"); highlight(select.selectedIndex, true);
    }
    function choose(index) {
      select.selectedIndex = index; close(); sync();
      select.dispatchEvent(new Event("input", {bubbles: true})); button.focus({preventScroll: true});
    }
    button.onclick = () => options.hidden ? open() : close();
    button.onkeydown = event => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === "Tab") { close(); return; }
      if (event.key === "Escape") { if (!options.hidden) event.preventDefault(); close(); return; }
      if (["Enter", " ", "ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const wasClosed = options.hidden;
        if (wasClosed) open();
        if (event.key === "Home") highlight(0, true);
        else if (event.key === "End") highlight(select.options.length - 1, true);
        else if (!wasClosed && (event.key === "Enter" || event.key === " ")) choose(active);
        else if (!wasClosed) highlight(active + (event.key === "ArrowDown" ? 1 : -1), true);
      } else if (event.key.length === 1) {
        event.preventDefault(); if (options.hidden) open();
        const now = Date.now(); prefix = now - typedAt > 700 ? event.key : prefix + event.key; typedAt = now;
        const query = [...prefix].every(letter => letter === prefix[0]) ? prefix[0] : prefix;
        for (let offset = 1; offset <= select.options.length; offset++) {
          const index = (active + offset) % select.options.length;
          if (select.options[index].textContent.toLowerCase().startsWith(query.toLowerCase())) { highlight(index, true); break; }
        }
      }
    };
    button.addEventListener("blur", close);
    document.addEventListener("pointerdown", event => { if (!wrapper.contains(event.target)) close(); });
    select.addEventListener("input", sync); sync();
    return {sync, close};
  }
  // Age as a person would say it: relative within a day, then the calendar date. The exact time stays in the title.
  function elapsed(value, now = Date.now()) {
    const seconds = Math.max(0, (now - new Date(value).getTime()) / 1000), date = new Date(value);
    if (seconds < 90) return "now";
    if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
    if (seconds < 86400) return `${Math.round(seconds / 3600)} h`;
    return date.toLocaleDateString(undefined, {month: "short", day: "numeric",
      ...(date.getFullYear() === new Date(now).getFullYear() ? {} : {year: "numeric"})});
  }
  // Requests to the Status service that served this page. Portable reports do not use these.
  const base = document.documentElement.dataset.base || "";
  let token;
  async function request(path, body) {
    let response;
    try {
      if (body !== undefined && !token) token = (await request("/api/config")).token;
      response = await fetch(base + path, {cache: "no-store", ...(body === undefined ? {} : {
        method: "POST", headers: {"Content-Type": "application/json", "X-Status-Token": token}, body: JSON.stringify(body)
      })});
    } catch (failure) {
      if (failure.status) throw failure;
      throw Error("Could not reach the Status service. Check the connection and try again.");
    }
    const result = await response.json().catch(() => ({}));
    if (response.status === 403 && body !== undefined) token = undefined;      // the service restarted; fetch a new token next time
    if (!response.ok) throw Object.assign(Error(result.error || "The Status service could not complete this request."), {status: response.status});
    return result;
  }
  // Content-free usage measurement; a failed measurement never interrupts the page.
  const measure = fields => request("/api/events", {...fields, narrow: matchMedia("(max-width: 640px)").matches}).catch(() => {});
  const localizeTimes = (root = document) => {
    for (const node of root.querySelectorAll("time[datetime]")) { node.textContent = time(node.dateTime); }
  };
  // Where an address leads from this page, so that everything on this host stays in this tab. `publicUrl` is the
  // review page's address on the shared host, when one is configured; `item` is the report or delivery to return to.
  // Result: {kind, href}. "page" is a page of the review page under the address in use; "application" is another
  // application on the shared host, shown framed by /embedded; "website" is any other host; "ribbon-field" is an
  // agentcoord:// link. null means the address is none of these and must not be opened on a document's request.
  const PAGE_ROUTE = /^\/(?:(?:reports|operations)\/[a-f0-9]{64}|deliveries\/[a-f0-9]{64}(?:\/attachments\/[0-9]{1,2})?)?$/;
  const APPLICATION_ADDRESS = /^(?:\/[A-Za-z0-9._~-]+)+\/?$/;
  function destination(href, publicUrl, item) {
    if (typeof href !== "string" || !href || href.length > 2000) return null;
    if (/^agentcoord:\/\/[^\s]+$/.test(href)) return {kind: "ribbon-field", href};
    if (!/^(?:https?:\/\/|\/(?!\/))/.test(href)) return null;                           // javascript:, data:, and every other scheme
    let target, shared = null;
    try { target = new URL(href, location.origin); if (publicUrl) shared = new URL(publicUrl); } catch { return null; }
    if (target.username || target.password) return null;
    const onSharedHost = Boolean(shared) && target.origin === shared.origin;
    if (!onSharedHost && target.origin !== location.origin) return {kind: "website", href: target.href};
    const prefix = shared ? shared.pathname.replace(/\/$/, "") : "", path = target.pathname;
    const page = route => PAGE_ROUTE.test(route) && !target.search ? {kind: "page", href: base + route + target.hash} : null;
    const within = path === prefix || path.startsWith(prefix + "/");
    if (!onSharedHost) {                                                                // this machine's own address: every path is the review page's
      if (PAGE_ROUTE.test(path) || !shared || !prefix || within) return page(path);
    } else if (!prefix || within) return page(path.slice(prefix.length) || "/");        // the review page on the shared host
    else if (path !== "/" && PAGE_ROUTE.test(path)) return page(path);                   // a page route written without the prefix
    if (target.search || target.hash || !APPLICATION_ADDRESS.test(path)) return null;
    return {kind: "application", href: `${base}/embedded?address=${path}` + (item ? `&from=${item}` : "")};
  }
  window.StatusControls = {make, time, elapsed, createPicker, pickers, base, request, measure, localizeTimes, destination};
})();

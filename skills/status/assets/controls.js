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
  // A list title is set without its closing full stop; question marks and ellipses stay.
  const listTitle = text => String(text).replace(/([^.])\.\s*$/, "$1");
  // A title too long for its lines ends at a whole word, never inside a figure; the full title stays in its tooltip and name.
  function fitTitles(root = document) {
    for (const node of root.querySelectorAll(".row-title")) {
      const full = node.dataset.full || node.textContent, named = node.closest("a, button");
      node.dataset.full = full; node.textContent = full; node.removeAttribute("title");
      if (named && named.dataset.fitted) { named.removeAttribute("aria-label"); delete named.dataset.fitted; }
      if (node.scrollHeight <= node.clientHeight + 1) continue;
      const words = full.split(" "); let low = 1, high = words.length - 1;
      const cut = count => words.slice(0, count).join(" ").replace(/[\s,;:.(\-–—]+$/, "") + "…";
      while (low < high) {
        const middle = Math.ceil((low + high) / 2); node.textContent = cut(middle);
        if (node.scrollHeight <= node.clientHeight + 1) low = middle; else high = middle - 1;
      }
      node.textContent = cut(low); node.title = full;
      if (named && !named.hasAttribute("aria-label")) { named.setAttribute("aria-label", full); named.dataset.fitted = "true"; }
    }
  }
  let fitting = 0;
  addEventListener("resize", () => { cancelAnimationFrame(fitting); fitting = requestAnimationFrame(() => fitTitles()); });
  // Choices as rows: one is chosen, then sent with the panel's solid button. Choosing the chosen row again clears it.
  // `choices` holds {value, label, tag}; `change(value)` receives the chosen value, or null when cleared.
  function createChoices(name, label, choices, chosen, disabled, change) {
    const group = make("div", null, "choices"); group.setAttribute("role", "radiogroup"); group.setAttribute("aria-label", label);
    for (const choice of choices) {
      const row = make("label", null, "choice"), input = make("input"), text = make("span", choice.label, "choice-text");
      input.type = "radio"; input.name = name; input.value = choice.value; input.checked = choice.value === chosen; input.disabled = disabled;
      input.setAttribute("aria-label", choice.label);
      input.onclick = () => { if (chosen === choice.value) { input.checked = false; chosen = null; } else chosen = choice.value; change(chosen); };
      row.append(input, make("span", null, "choice-mark"), text);
      if (choice.tag) row.append(make("span", choice.tag, "choice-tag"));
      group.append(row);
    }
    return group;
  }
  // A single line for words that grows with what is written.
  function createLine(className, value, placeholder, label, limit, input) {
    const field = make("textarea", null, className + " line-field"); field.rows = 1; field.maxLength = limit; field.value = value;
    field.placeholder = placeholder; field.setAttribute("aria-label", label);
    const fit = () => { if (!CSS.supports("field-sizing", "content")) { field.style.height = "auto"; field.style.height = field.scrollHeight + field.offsetHeight - field.clientHeight + "px"; } };
    field.oninput = () => { input(field.value); fit(); };
    queueMicrotask(fit);
    return field;
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
  // A moment in the reader's own timezone: the year appears only when it is not this one, and the full form stays in the title.
  const moment = value => { const date = new Date(value); return date.toLocaleString(undefined, {month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    ...(date.getFullYear() === new Date().getFullYear() ? {} : {year: "numeric"})}); };
  const localizeTimes = (root = document) => {
    for (const node of root.querySelectorAll("time[datetime]")) { node.textContent = moment(node.dateTime); node.title = time(node.dateTime); }
  };
  window.StatusControls = {make, time, moment, elapsed, listTitle, fitTitles, createChoices, createLine, createPicker, pickers, base, request, measure, localizeTimes};
})();

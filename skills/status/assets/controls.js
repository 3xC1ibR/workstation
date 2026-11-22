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
  // Elapsed time in the units a person would say aloud; exact time stays available as a title.
  function elapsed(value, now = Date.now()) {
    const seconds = Math.max(0, (now - new Date(value).getTime()) / 1000);
    if (seconds < 90) return "just now";
    for (const [unit, size] of [["min", 60], ["h", 3600], ["d", 86400]]) {
      const next = unit === "min" ? 3600 : unit === "h" ? 86400 * 2 : 86400 * 14;
      if (seconds < next) return `${Math.round(seconds / size)} ${unit} ago`;
    }
    return new Date(value).toLocaleDateString(undefined, {month: "short", day: "numeric", year: "numeric"});
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
  window.StatusControls = {make, time, elapsed, createPicker, pickers, base, request, measure, localizeTimes};
})();

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
    const wrapper = make("div", null, "collection-picker"), button = make("button", null, "collection-picker-trigger");
    const value = make("span"), options = make("div", null, "collection-picker-options");
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
    select.classList.add("collection-native-select"); select.tabIndex = -1; select.setAttribute("aria-hidden", "true");
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
        const option = make("div", entry.textContent, "collection-picker-option");
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
  window.StatusControls = {make, time, createPicker, pickers};
})();

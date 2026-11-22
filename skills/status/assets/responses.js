"use strict";
// The report snapshot stays inert. These trusted controls belong to the collection.
window.createStatusResponses = (report, {make, request, createPicker, pickers, time}) => {
  const details = make("details", null, "response-editor");
  const summary = make("summary", `Responses · ${report.response_field_count} fields`);
  const status = make("p", "", "collection-note"), failure = make("p", "", "collection-error");
  status.setAttribute("role", "status"); failure.setAttribute("role", "alert"); failure.hidden = true;
  const form = make("form"), fields = make("fieldset", null, "response-fields");
  const actions = make("div", null, "response-actions");
  const save = make("button", "Save responses"), reload = make("button", "Load saved responses");
  save.type = "submit"; reload.type = "button";
  actions.append(save, reload); fields.append(actions); form.append(fields);
  details.append(summary, status, failure, form); form.hidden = true;
  let state, loading = false;
  const controls = new Map();
  const showError = message => { failure.textContent = message; failure.hidden = !message; };
  function markDirty() {
    details.dataset.dirty = "true";
    status.textContent = "Unsaved changes."; reload.textContent = "Discard edits and reload";
  }
  function savedState(next) {
    state = next; details.dataset.dirty = "false";
    reload.textContent = "Load saved responses";
    status.textContent = next.updated_at ? "Saved " + time(next.updated_at) + ". The agent can read these responses." : "No responses saved.";
  }
  function build(next) {
    if (controls.size) {
      for (const [identifier, control] of controls) {
        control.value = next.values[identifier] == null ? "" : String(next.values[identifier]);
        pickers.get(control.id)?.sync();
      }
      return;
    }
    for (const field of next.fields) {
      const wrapper = make("div", null, "response-field");
      const control = make(field.type === "multiline" ? "textarea" : ["choice", "boolean"].includes(field.type) ? "select" : "input");
      control.id = `response-${report.id}-${field.id}`; control.name = field.id;
      const label = make("label", field.label + (field.required ? " ·\u00a0Required" : ""));
      label.id = control.id + "-label"; label.htmlFor = control.id;
      if (control.tagName === "SELECT") {
        control.add(new Option("Choose a response", ""));
        if (field.type === "boolean") { control.add(new Option("Yes", "true")); control.add(new Option("No", "false")); }
        else for (const option of field.options) control.add(new Option(option, option));
      } else {
        if (control.tagName === "TEXTAREA") control.rows = 4;
        else { control.type = field.type === "number" ? "number" : "text"; if (field.type === "number") control.step = "any"; }
        if (field.type !== "number") control.maxLength = 20000;
        control.required = Boolean(field.required);
      }
      control.setAttribute("aria-required", String(Boolean(field.required)));
      control.value = next.values[field.id] == null ? "" : String(next.values[field.id]);
      wrapper.append(label);
      if (field.help) {
        const help = make("p", field.help, "collection-note"); help.id = control.id + "-help";
        control.setAttribute("aria-describedby", help.id); wrapper.append(help);
      }
      wrapper.append(control); fields.insertBefore(wrapper, actions); controls.set(field.id, control);
      if (control.tagName === "SELECT") pickers.set(control.id, createPicker(control));
      control.addEventListener("input", markDirty);
    }
    form.hidden = false;
  }
  async function load() {
    if (loading) return;
    loading = true; fields.disabled = true; showError(""); status.textContent = "Loading saved responses…";
    try {
      const next = await request("/api/responses/" + report.id);
      build(next); savedState(next);
    } catch (error) {
      showError(error.message); status.textContent = details.dataset.dirty === "true" ? "Unsaved changes retained." : "Could not load responses.";
      if (!state) { form.hidden = false; save.disabled = true; }
    } finally { loading = false; fields.disabled = false; if (state) save.disabled = false; }
  }
  details.addEventListener("toggle", () => { if (details.open && !state) load(); });
  reload.onclick = load;
  form.onsubmit = async event => {
    event.preventDefault();
    if (!state || loading) return;
    const values = {};
    for (const field of state.fields) {
      const control = controls.get(field.id), value = control.value;
      if (!value.trim()) {
        if (field.required) {
          showError(field.label + ": a response is required.");
          (document.getElementById(control.id + "-trigger") || control).focus(); return;
        }
        continue;
      }
      values[field.id] = field.type === "number" ? Number(value) : field.type === "boolean" ? value === "true" : value;
    }
    loading = true; fields.disabled = true; showError(""); status.textContent = "Saving responses…";
    try {
      const next = await request("/api/responses", {id: report.id, revision: state.revision, values});
      savedState(next);
    } catch (error) { showError(error.message); status.textContent = "Responses were not saved. Your input is still here."; }
    finally { loading = false; fields.disabled = false; }
  };
  return details;
};

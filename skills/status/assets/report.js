// The portable report embeds this file in a closure that defines embeddedConfiguration.
// The Status service loads it as a file and supplies the same object in a data block.
(() => {
  const configuration = typeof embeddedConfiguration === "undefined"
    ? JSON.parse(document.getElementById("status-configuration").textContent).responses : embeddedConfiguration;
  const {make, time, createPicker, pickers} = window.StatusControls;
  const report = {id: configuration.connection?.id || "preview", response_field_count: configuration.fields.length};
  async function request(path, body) {
    if (!configuration.connection) throw Error("This preview is not connected for saving responses.");
    let response;
    try {
      response = await fetch(configuration.connection.url, {cache: "no-store", credentials: "omit",
        headers: {"X-Status-Report-Token": configuration.connection.token, ...(body === undefined ? {} : {"Content-Type": "application/json"})},
        ...(body === undefined ? {} : {method: "POST", body: JSON.stringify({revision: body.revision, values: body.values})})});
    } catch {
      throw Error("Could not reach the Status service. Your input is still here; retry when it is available.");
    }
    const result = await response.json();
    if (!response.ok) throw Error(result.error || "Responses could not be saved. Your input is still here.");
    return result;
  }
  document.getElementById("status-response-fields").append(window.createStatusResponses(report, {
    make, time, createPicker, pickers, request, expanded: true,
    initialState: {fields: configuration.fields, values: {}, revision: 0, updated_at: null}
  }));
  addEventListener("beforeunload", event => {
    if (document.querySelector('[data-dirty="true"]')) { event.preventDefault(); event.returnValue = ""; }
  });
})();

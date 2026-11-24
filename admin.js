/**
 * Admin page: sign in by email link, approve or reject visitor submissions,
 * find any organization to verify or edit, add new ones, and upload CSVs.
 * Database access rules (supabase/migrations) allow these writes only for
 * emails in the `admins` table. Helpers come from forms.js.
 */

const ADDRESS_KEYS = ["address", "city", "state", "postal_code"];

const ui = {
  message: document.querySelector("#admin-message"),
  signIn: document.querySelector("#sign-in"),
  signInForm: document.querySelector("#sign-in-form"),
  area: document.querySelector("#admin-area"),
  email: document.querySelector("#admin-email"),
  signOut: document.querySelector("#sign-out"),
  pendingCount: document.querySelector("#pending-count"),
  pendingList: document.querySelector("#pending-list"),
  searchForm: document.querySelector("#search-form"),
  searchResults: document.querySelector("#search-results"),
  newOrganization: document.querySelector("#new-organization"),
  editor: document.querySelector("#editor"),
  editorTitle: document.querySelector("#editor-title"),
  editorForm: document.querySelector("#editor-form"),
  editorFields: document.querySelector("#editor-fields"),
  locate: document.querySelector("#locate"),
  remove: document.querySelector("#remove"),
  cancelEdit: document.querySelector("#cancel-edit"),
  csvInput: document.querySelector("#csv-file"),
  csvMessage: document.querySelector("#csv-message"),
};

let client;
let filters = [];
let editing = null; // { id, properties } for an existing row, { id: null } for a new one.

function fail(error) {
  console.error(error);
  showMessage(ui.message, escapeText(error.message ?? String(error)), "error");
}

function check({ data, error }) {
  if (error) throw new Error(error.message);
  return data;
}

function rowSummary(properties) {
  const place = [properties.city, properties.state].filter(Boolean).join(", ");
  const pin = Number.isFinite(properties.latitude) ? "" : ` · <span class="warning-text">no map pin</span>`;
  const site = properties.website_url
    ? ` · <a class="popup-link" href="${escapeText(properties.website_url)}" target="_blank" rel="noopener noreferrer">website</a>`
    : "";
  return `<strong>${escapeText(properties.name)}</strong><span>${escapeText(place)} · ${escapeText(properties.gcc_verification ?? "Not Verified")}${site}${pin}</span>`;
}

async function loadPending() {
  const rows = check(
    await client.from("organizations").select("id, properties").eq("review_status", "pending").order("created_at"),
  );
  ui.pendingCount.textContent = rows.length ? `(${rows.length} waiting)` : "";
  ui.pendingList.innerHTML = rows.length
    ? rows
        .map(
          (row) => `
          <div class="admin-row" data-id="${escapeText(row.id)}">
            <div class="admin-row-copy">${rowSummary(row.properties)}</div>
            <div class="button-row">
              <button class="primary-button small" data-action="approve" type="button">Approve</button>
              <button class="text-button" data-action="edit" type="button">Edit</button>
              <button class="text-button danger" data-action="delete" type="button">Delete</button>
            </div>
          </div>`,
        )
        .join("")
    : `<p class="form-help">No new organizations waiting for approval.</p>`;
}

async function setReviewStatus(id, review_status) {
  check(await client.from("organizations").update({ review_status }).eq("id", id));
}

/**
 * Delete an organization. Rows added through the forms are deleted outright.
 * Pipeline rows (IRS `org_…`, survey `survey_…`) are also in the static map
 * file and would be re-sent by the next sync, so they keep a "removed" marker
 * that hides them on the map and stops the sync from restoring them.
 */
/** Site-styled confirmation (native <dialog>: focus trap and Escape come built in). */
function confirmAction(title, text, confirmLabel, { danger = true } = {}) {
  const dialog = document.querySelector("#confirm-dialog");
  dialog.querySelector("#confirm-title").textContent = title;
  dialog.querySelector("#confirm-text").textContent = text;
  const confirm = dialog.querySelector("button[value=confirm]");
  confirm.textContent = confirmLabel;
  confirm.classList.toggle("danger-button", danger);
  dialog.returnValue = "";
  dialog.showModal();
  dialog.querySelector("button[value=cancel]").focus();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
  });
}

async function deleteOrganization(id, name) {
  const added = id.startsWith("added_");
  const confirmed = await confirmAction(
    `Delete ${name}?`,
    added
      ? "It will be removed from the map and the database. This cannot be undone."
      : "It will be hidden from the map. You can restore it later by searching for it, opening Edit and clicking Save.",
    "Delete",
  );
  if (!confirmed) return false;
  if (id.startsWith("added_")) check(await client.from("organizations").delete().eq("id", id));
  else check(await client.from("organizations").update({ review_status: "removed", updated_via: "admin" }).eq("id", id));
  showMessage(ui.message, `Deleted <strong>${escapeText(name)}</strong>.`, "success");
  return true;
}

/**
 * Open the editor for an organization (`id`) or a new one (null). A survey
 * review passes `fromResponse` (the response) and `overrides` (values from its
 * answers, shown on top of the current listing).
 */
async function openEditor(id, { overrides = null, fromResponse = null } = {}) {
  if (id) {
    const row = check(await client.from("organizations").select("id, properties").eq("id", id).single());
    editing = { id: row.id, properties: row.properties };
    ui.editorTitle.textContent = `${fromResponse ? "Verify" : "Edit"} ${row.properties.name}`;
  } else {
    editing = { id: null, properties: null };
    ui.editorTitle.textContent = fromResponse ? `Add ${overrides?.name ?? "organization"} from the survey` : "Add a new organization";
  }
  editing.fromResponse = fromResponse;
  renderOrganizationFields(ui.editorFields, filters, { admin: true });
  if (editing.properties) fillForm(ui.editorForm, editing.properties);
  if (overrides) fillForm(ui.editorForm, overrides);
  enhanceOrganizationFields(ui.editorForm, {
    // An exact address pick places the pin right away (shown in the coordinates).
    onPick: (picked) => {
      if (!picked.precise) return;
      ui.editorForm.elements.latitude.value = picked.latitude;
      ui.editorForm.elements.longitude.value = picked.longitude;
      ui.editorForm.dataset.precision = "address_suggestion";
    },
  });
  // An exact point picked in the survey is kept unless the address is edited here.
  ui.editorForm.dataset.precision = overrides?.location_precision ?? "";
  ui.remove.hidden = !editing.id;
  ui.editor.hidden = false;
  ui.editor.scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeEditor() {
  editing = null;
  ui.editor.hidden = true;
}

/** Locate the address into `values` and the form; returns the location or null. */
async function locateInto(values) {
  const location = await locateOrganization(values, ui.editorForm);
  if (!location) return null;
  Object.assign(values, location);
  ui.editorForm.elements.latitude.value = location.latitude;
  ui.editorForm.elements.longitude.value = location.longitude;
  ui.editorForm.dataset.precision = location.location_precision;
  return location;
}

async function saveEditor(event) {
  event.preventDefault();
  const { errors, values } = validateOrganization(readForm(ui.editorForm), filters, { admin: true });
  if (errors.length) return showMessage(ui.message, errors.map(escapeText).join("<br>"), "error");
  const base = editing.properties;
  if (ui.editorForm.dataset.precision) values.location_precision = ui.editorForm.dataset.precision;
  // A changed address moves the pin unless the coordinates were also edited by hand.
  const addressChanged = !base || ADDRESS_KEYS.some((key) => String(base[key] ?? "") !== values[key]);
  const coordinatesEdited = base && (String(base.latitude ?? "") !== values.latitude || String(base.longitude ?? "") !== values.longitude);
  let note = "";
  if (addressChanged && !coordinatesEdited && !ui.editorForm.dataset.precision) {
    const location = await locateInto(values);
    note = location ? locationNote(location, values) : "The address was not found, so the map pin was not moved. Enter latitude and longitude to place it.";
  }
  const response = editing.fromResponse;
  const newOptions = response
    ? { source: "GCC survey", note: "Added from the GCC verification survey." }
    : { source: "GCC admin", note: "Added by the GCC admin." };
  const properties = await buildProperties(values, filters, base ? { base } : newOptions);
  const today = new Date().toISOString().slice(0, 10);
  if (response && values.gcc_verification === "Verified") {
    properties.verification_source = `Answered the GCC verification survey on ${response.created_at.slice(0, 10)}; verified by the GCC admin on ${today}.`;
  } else if (values.gcc_verification === "Verified" && base?.gcc_verification !== "Verified") {
    properties.verification_source = `Verified by the GCC admin on ${today}.`;
  }
  const row = { properties, review_status: "approved", updated_via: "admin" };
  if (editing.id) check(await client.from("organizations").update(row).eq("id", editing.id));
  else check(await client.from("organizations").insert({ id: properties.id, ...row }));
  if (response) {
    check(
      await client
        .from("survey_responses")
        .update({ review_status: "approved", applied_organization_id: editing.id ?? properties.id, reviewed_at: new Date().toISOString() })
        .eq("id", response.id),
    );
  }
  const live = Number.isFinite(properties.latitude) ? "It is live on the map." : "It has no map pin yet, so it is not shown on the map.";
  showMessage(ui.message, `Saved <strong>${escapeText(properties.name)}</strong>. ${live}${note ? ` ${escapeText(note)}` : ""}`, "success");
  closeEditor();
  await refreshLists();
}

let lastQuery = "";

/** Reload the review lists and re-run the last search so statuses are current. */
async function refreshLists() {
  await Promise.all([loadPending(), loadSurveyResponses(), loadRuns()]);
  if (lastQuery) await search();
}

/* ---------------- Extraction runs (pipeline_runs, .github/workflows/pipeline.yml) ---------------- */

// Average spend per organization in the Massachusetts and California runs
// (about $40 for 3,355): Brave searches, OpenRouter fallbacks and Jev.
const COST_PER_ORGANIZATION = 0.012;
const RUN_STATUS = {
  queued: "queued", running: "running", succeeded: "finished", failed: "failed", cancelled: "cancelled",
};
let pendingByState = {};
let runPoll = null;

/** GitHub's answer when a run never started (shown only for queued runs). */
async function dispatchProblem(run) {
  const minutes = (Date.now() - new Date(run.created_at)) / 60000;
  const [result] = check(await client.rpc("pipeline_dispatch_result", { run_id: run.id }));
  if (result?.status_code && result.status_code !== 204) {
    return `GitHub refused to start it (${result.status_code}: ${result.message ?? ""}). The GitHub token in Supabase Vault may have expired, or the workflow isn't on the master branch yet. Cancel it, fix that, and run again.`;
  }
  return minutes > 10 ? "Queued for over 10 minutes. GitHub may be busy, or the start request was lost; check the Actions tab, or cancel and run again." : "";
}

function runSummary(run) {
  const s = run.summary ?? {};
  if (run.status === "succeeded" && run.kind === "extract") {
    return `${s.processed ?? 0} processed · ${s.websites_found ?? 0} websites found · ${s.failed ?? 0} errors · ${s.remaining ?? 0} still waiting in ${run.state}`;
  }
  if (run.status === "succeeded") return `${s.organizations ?? 0} organizations, ${s.saved ?? 0} changed`;
  return run.error ?? "";
}

async function loadRuns() {
  const [pending, runs] = await Promise.all([
    client.rpc("extraction_pending").then(check),
    client.from("pipeline_runs").select("*").order("id", { ascending: false }).limit(10).then(check),
  ]);
  pendingByState = Object.fromEntries(pending.map((row) => [row.state, row.pending]));
  const select = document.querySelector("#run-form").elements.state;
  const chosen = select.value;
  select.innerHTML = `<option value="">Choose a state</option>${Object.entries(US_STATES)
    .filter(([code]) => !["AS", "GU", "MP", "PR", "VI"].includes(code)) // territories aren't in the IRS state files
    .sort(([, a], [, b]) => a.localeCompare(b))
    .map(([code, name]) => {
      const waiting = pendingByState[code] ?? 0;
      return `<option value="${code}" ${waiting ? "" : "disabled"}>${escapeText(name)} (${waiting.toLocaleString()} waiting)</option>`;
    })
    .join("")}`;
  select.value = chosen;
  updateEstimate();

  const problems = await Promise.all(runs.map((run) => (run.status === "queued" ? dispatchProblem(run) : "")));
  const active = runs.find((run) => run.status === "queued" || run.status === "running");
  document.querySelector("#run-status").textContent = active ? `(${RUN_STATUS[active.status]})` : "";
  document.querySelector("#run-list").innerHTML = runs.length
    ? runs.map((run, index) => {
        const what = run.kind === "extract" ? `${US_STATES[run.state] ?? run.state}, up to ${run.org_limit}` : "IRS data refresh";
        const when = new Date(run.created_at).toLocaleString();
        const log = run.run_url?.startsWith("https://") ? ` · <a class="popup-link" href="${escapeText(run.run_url)}" target="_blank" rel="noopener noreferrer">log</a>` : "";
        const detail = problems[index] || runSummary(run);
        const warn = run.status === "failed" || problems[index];
        return `
          <div class="admin-row" data-run="${run.id}">
            <div class="admin-row-copy">
              <strong>${escapeText(what)}</strong>
              <span>${escapeText(RUN_STATUS[run.status])} · ${escapeText(when)}${run.requested_by ? ` · ${escapeText(run.requested_by)}` : ""}${log}</span>
              ${detail ? `<span class="${warn ? "warning-text" : ""}">${escapeText(detail)}</span>` : ""}
            </div>
            ${run.status === "queued" || run.status === "running" ? `<button class="text-button danger" data-action="cancel-run" type="button">Cancel</button>` : ""}
          </div>`;
      }).join("")
    : `<p class="form-help">No runs yet.</p>`;

  // Follow an active run without reloading the page.
  clearTimeout(runPoll);
  if (active) runPoll = setTimeout(() => loadRuns().catch(fail), 30000);
}

function updateEstimate() {
  const { state, org_limit } = readForm(document.querySelector("#run-form"));
  const waiting = pendingByState[state] ?? 0;
  const count = Math.min(Number(org_limit) || 0, waiting);
  document.querySelector("#run-estimate").textContent = state
    ? `${waiting.toLocaleString()} organizations waiting in ${US_STATES[state]}. This run processes ${count.toLocaleString()}: about $${(count * COST_PER_ORGANIZATION).toFixed(2)} (estimate).`
    : "";
}

async function startRun(event) {
  event.preventDefault();
  const { state, org_limit } = readForm(event.target);
  const count = Math.min(Number(org_limit), pendingByState[state] ?? 0);
  const confirmed = await confirmAction(
    `Run extraction for ${US_STATES[state]}?`,
    `Processes up to ${count.toLocaleString()} organizations, about $${(count * COST_PER_ORGANIZATION).toFixed(2)}. It runs on GitHub; you can close this page.`,
    "Start run",
    { danger: false },
  );
  if (!confirmed) return;
  const { error } = await client.from("pipeline_runs").insert({ kind: "extract", state, org_limit: Number(org_limit) });
  if (error?.code === "23505") throw new Error("Another run is queued or running. Wait for it to finish, or cancel it below.");
  check({ error });
  showMessage(ui.message, `Run requested for <strong>${escapeText(US_STATES[state])}</strong>. Its progress shows under <em>Find websites and contacts</em>.`, "success");
  await loadRuns();
}

async function cancelRun(id) {
  const confirmed = await confirmAction(
    "Cancel this run?",
    "A queued run won't start. A run already working on GitHub keeps going until you also cancel it in the GitHub Actions tab (its log link); what it finished is kept.",
    "Cancel run",
  );
  if (!confirmed) return;
  check(await client.from("pipeline_runs").update({ status: "cancelled" }).eq("id", id));
  await loadRuns();
}

/* ---------------- Survey responses ---------------- */

let survey; // data/survey.json
let surveyQuestions = []; // Every question in survey order (no example card).
let surveyRows = [];
const CONNECTION_LABELS = { organization: "Organization", municipality: "Municipality", individual: "Individual" };

const questionByField = (field) => surveyQuestions.find((q) => q.map_field === field);
const answer = (row, field) => row.answers[questionByField(field)?.id] ?? "";
const asText = (value) => (Array.isArray(value) ? value.join(", ") : String(value ?? ""));

function respondentName(row) {
  return [answer(row, "respondent_first_name"), answer(row, "respondent_last_name")].filter(Boolean).join(" ") || "Unnamed respondent";
}

async function loadSurveyResponses() {
  let query = client.from("survey_responses").select("*").order("created_at", { ascending: false });
  if (!document.querySelector("#survey-show-all").checked) query = query.eq("review_status", "pending");
  surveyRows = check(await query);
  const pending = surveyRows.filter((row) => row.review_status === "pending").length;
  document.querySelector("#survey-count").textContent = pending ? `(${pending} waiting)` : "";
  document.querySelector("#survey-list").innerHTML = surveyRows.length
    ? surveyRows.map(surveyRowHtml).join("")
    : `<p class="form-help">${document.querySelector("#survey-show-all").checked ? "No survey responses yet." : "No verification surveys waiting for review."}</p>`;
}

function surveyRowHtml(row) {
  const organization = answer(row, "name");
  const place = row.connection === "organization"
    ? [answer(row, "city"), answer(row, "state")].filter(Boolean).join(", ")
    : "";
  const status = { pending: "waiting to verify", approved: "verified on the map", research: "research only" }[row.review_status];
  const answered = (q) => row.answers[q.id] !== undefined;
  const answers = surveyQuestions
    .filter(answered)
    .map((q) => `<div><dt>${escapeText(q.title)}</dt><dd>${escapeText(asText(row.answers[q.id]))}</dd></div>`)
    .join("");
  return `
    <div class="admin-row survey-row" data-response="${escapeText(row.id)}">
      <div class="admin-row-copy">
        <strong>${escapeText(organization || respondentName(row))}</strong>
        <span>${escapeText(CONNECTION_LABELS[row.connection])}${organization ? ` · ${escapeText(respondentName(row))}` : ""}${place ? ` · ${escapeText(place)}` : ""} · ${escapeText(row.created_at.slice(0, 10))} · ${escapeText(status)}</span>
      </div>
      <div class="button-row">
        ${row.review_status === "pending" ? `<button class="primary-button small" data-action="review" type="button">Review &amp; verify</button>` : ""}
        <button class="text-button danger" data-action="delete-response" type="button">Delete</button>
      </div>
      <details class="survey-answers">
        <summary>View all answers</summary>
        <dl>${answers}</dl>
      </details>
    </div>`;
}

/** Open the editor on the listing this response describes, filled in from its answers. */
async function reviewResponse(row) {
  const overrides = {
    name: answer(row, "name"),
    website_url: answer(row, "website_url"),
    address: answer(row, "address"),
    city: answer(row, "city"),
    state: stateCode(answer(row, "state")) ?? "",
    postal_code: answer(row, "postal_code"),
    ...filtersFromFocus([].concat(answer(row, "focus") || [])),
    gcc_verification: "Verified",
    ...(row.answers._location ?? {}),
  };
  // The listing it was opened from, else an existing listing with the same name and state.
  let id = row.organization_id;
  if (!id) {
    const matches = check(
      await client.from("organizations").select("id").ilike("name", overrides.name.replace(/[%_]/g, " ")).eq("state", overrides.state).limit(1),
    );
    id = matches[0]?.id ?? null;
  }
  // The survey has no organization-type question: keep the listing's own type,
  // and use the usual default only for a new organization.
  if (!id) overrides.gcc_organization_type = "Nonprofit / Grassroots";
  await openEditor(id, { overrides, fromResponse: row });
  showMessage(
    ui.message,
    id
      ? "Matched an existing listing. Check the values from the survey, then Save to verify it."
      : "No listing matched, so this adds a new organization. Check the values, then Save to add and verify it.",
  );
}

async function deleteResponse(row) {
  const confirmed = await confirmAction(
    `Delete the response from ${respondentName(row)}?`,
    "Its answers will be removed from the database and from future downloads. This cannot be undone.",
    "Delete",
  );
  if (!confirmed) return;
  check(await client.from("survey_responses").delete().eq("id", row.id));
  showMessage(ui.message, "Response deleted.", "success");
  await loadSurveyResponses();
}

/** All responses as a CSV with one column per question, like the old Google Sheet. */
async function downloadResponses() {
  const rows = check(await client.from("survey_responses").select("*").order("created_at"));
  const seen = new Map();
  const headers = surveyQuestions.map((q) => {
    // Google Sheets numbers repeated question titles ("… 2"); this keeps the same columns.
    const count = (seen.get(q.title) ?? 0) + 1;
    seen.set(q.title, count);
    return count > 1 ? `${q.title} ${count}` : q.title;
  });
  const cell = (value) => `"${asText(value).replace(/"/g, '""')}"`;
  const lines = [
    ["Timestamp", "Connection", "Review status", "Map listing", ...headers].map(cell).join(","),
    ...rows.map((row) =>
      [row.created_at, CONNECTION_LABELS[row.connection], row.review_status, row.applied_organization_id ?? row.organization_id ?? "",
        ...surveyQuestions.map((q) => row.answers[q.id] ?? "")].map(cell).join(","),
    ),
  ];
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([`﻿${lines.join("\n")}\n`], { type: "text/csv;charset=utf-8" }));
  link.download = `survey-responses-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
  showMessage(ui.message, `Downloaded ${rows.length} responses.`, "success");
}

async function search(event) {
  if (event) {
    event.preventDefault();
    lastQuery = readForm(ui.searchForm).query.replace(/[%_,()]/g, " ");
  }
  const query = lastQuery;
  const rows = check(
    await client
      .from("organizations")
      .select("id, name, city, state, verification, review_status")
      .ilike("name", `%${query}%`)
      .order("name")
      .limit(25),
  );
  ui.searchResults.innerHTML = rows.length
    ? rows
        .map(
          (row) => `
          <div class="admin-row" data-id="${escapeText(row.id)}">
            <div class="admin-row-copy"><strong>${escapeText(row.name)}</strong>
              <span>${escapeText([row.city, row.state].filter(Boolean).join(", "))} · ${escapeText(row.verification ?? "Not Verified")}${row.review_status === "approved" ? "" : ` · ${escapeText(row.review_status)}`}</span></div>
            <button class="text-button" data-action="edit" type="button">Edit</button>
          </div>`,
        )
        .join("")
    : `<p class="form-help">No organization matches.</p>`;
}

async function uploadCsv() {
  const file = ui.csvInput.files[0];
  if (!file) return;
  ui.csvInput.disabled = true;
  try {
    const rows = await parseCsv(file);
    if (!rows.length) throw new Error("The file has no rows.");
    const { ready, problems } = await prepareCsvRows(rows, filters, {
      admin: true,
      source: "GCC admin",
      note: "Added by the GCC admin from a CSV upload.",
      onProgress: (text) => showMessage(ui.csvMessage, escapeText(text)),
    });
    const date = new Date().toISOString().slice(0, 10);
    ready.forEach((p) => p.gcc_verification === "Verified" && (p.verification_source = `Verified by the GCC admin on ${date}.`));
    if (ready.length) {
      check(
        await client
          .from("organizations")
          .upsert(ready.map((p) => ({ id: p.id, properties: p, review_status: "approved", updated_via: "admin" }))),
      );
    }
    const issues = problems.length ? `<ul>${problems.map((p) => `<li>${escapeText(p)}</li>`).join("")}</ul>` : "";
    showMessage(ui.csvMessage, `${ready.length} of ${rows.length} organizations saved and live on the map (except any without a map pin, listed below).${issues}`, ready.length ? "success" : "error");
    await refreshLists();
  } catch (error) {
    showMessage(ui.csvMessage, escapeText(error.message), "error");
  } finally {
    ui.csvInput.value = "";
    ui.csvInput.disabled = false;
  }
}

async function showSignedIn(session) {
  if (!session) {
    ui.area.hidden = true;
    ui.signIn.hidden = false;
    return;
  }
  ui.signIn.hidden = true;
  ui.email.textContent = session.user.email;
  const isAdmin = check(await client.rpc("is_admin"));
  if (!isAdmin) {
    ui.area.hidden = true;
    showMessage(ui.message, `${escapeText(session.user.email)} is not an admin. <button class="text-button" type="button" onclick="client.auth.signOut()">Sign out</button>`, "error");
    return;
  }
  ui.message.hidden = true;
  ui.area.hidden = false;
  await refreshLists();
}

async function startAdmin() {
  const config = supabaseConfig();
  if (!config) throw new Error("Supabase is not configured yet. Run python -m scripts.sync_supabase after adding the keys to .env.");
  client = window.supabase.createClient(config.url, config.anonKey);
  filters = await loadFilterSchema();
  survey = await (await fetch("data/survey.json")).json();
  surveyQuestions = survey.sections.flatMap((section) => section.questions).filter((q) => q.type !== "example");
  document.querySelector("#csv-template").href = csvTemplateUrl({ admin: true });
  renderRules(filters, { admin: true });

  ui.signInForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const { email } = readForm(ui.signInForm);
    const { error } = await client.auth.signInWithOtp({ email, options: { emailRedirectTo: location.origin + location.pathname } });
    if (error) return fail(error);
    showMessage(ui.message, `A sign-in link was sent to ${escapeText(email)}. Open it on this device.`, "success");
  });
  ui.signOut.addEventListener("click", () => client.auth.signOut());

  ui.pendingList.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = button.closest("[data-id]").dataset.id;
    try {
      if (button.dataset.action === "edit") return await openEditor(id);
      if (button.dataset.action === "approve") await setReviewStatus(id, "approved");
      else if (!(await deleteOrganization(id, button.closest("[data-id]").querySelector("strong").textContent))) return;
      await refreshLists();
    } catch (error) {
      fail(error);
    }
  });
  ui.searchResults.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action=edit]");
    if (button) openEditor(button.closest("[data-id]").dataset.id).catch(fail);
  });
  ui.searchForm.addEventListener("submit", (event) => search(event).catch(fail));
  ui.newOrganization.addEventListener("click", () => openEditor(null).catch(fail));
  ui.editorForm.addEventListener("submit", (event) => saveEditor(event).catch(fail));
  ui.locate.addEventListener("click", async () => {
    const values = readForm(ui.editorForm);
    const location = await locateInto(values);
    const text = location
      ? `${locationNote(location, values) || "Address located."} Save to keep the new pin.`
      : "The address was not found, and there is no ZIP code to fall back on. Enter latitude and longitude to place it.";
    showMessage(ui.message, escapeText(text), location ? "success" : "error");
  });
  ui.remove.addEventListener("click", async () => {
    try {
      if (!(await deleteOrganization(editing.id, editing.properties.name))) return;
      closeEditor();
      await refreshLists();
    } catch (error) {
      fail(error);
    }
  });
  ui.cancelEdit.addEventListener("click", closeEditor);
  document.querySelector("#survey-list").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const row = surveyRows.find((r) => r.id === button.closest("[data-response]").dataset.response);
    try {
      if (button.dataset.action === "review") await reviewResponse(row);
      else await deleteResponse(row);
    } catch (error) {
      fail(error);
    }
  });
  document.querySelector("#survey-show-all").addEventListener("change", () => loadSurveyResponses().catch(fail));
  document.querySelector("#survey-download").addEventListener("click", () => downloadResponses().catch(fail));
  ui.csvInput.addEventListener("change", uploadCsv);
  const runForm = document.querySelector("#run-form");
  runForm.addEventListener("submit", (event) => startRun(event).catch(fail));
  runForm.addEventListener("input", updateEstimate);
  document.querySelector("#run-list").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action=cancel-run]");
    if (button) cancelRun(Number(button.closest("[data-run]").dataset.run)).catch(fail);
  });

  client.auth.onAuthStateChange((_event, session) => {
    // Supabase warns against awaiting its own calls inside this callback.
    setTimeout(() => showSignedIn(session).catch(fail));
  });
}

startAdmin().catch(fail);

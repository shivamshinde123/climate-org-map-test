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
  ui.pendingCount.textContent = rows.length ? `(${rows.length})` : "";
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
    : `<p class="form-help">Nothing waiting.</p>`;
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
async function deleteOrganization(id, name) {
  if (!confirm(`Delete ${name}? This cannot be undone.`)) return false;
  if (id.startsWith("added_")) check(await client.from("organizations").delete().eq("id", id));
  else check(await client.from("organizations").update({ review_status: "removed", updated_via: "admin" }).eq("id", id));
  showMessage(ui.message, `Deleted <strong>${escapeText(name)}</strong>.`, "success");
  return true;
}

async function openEditor(id) {
  if (id) {
    const row = check(await client.from("organizations").select("id, properties").eq("id", id).single());
    editing = { id: row.id, properties: row.properties };
    ui.editorTitle.textContent = `Edit ${row.properties.name}`;
  } else {
    editing = { id: null, properties: null };
    ui.editorTitle.textContent = "Add a new organization";
  }
  renderOrganizationFields(ui.editorFields, filters, { admin: true });
  if (editing.properties) fillForm(ui.editorForm, editing.properties);
  ui.editorForm.dataset.precision = "";
  ui.remove.hidden = !editing.id;
  ui.editor.hidden = false;
  ui.editor.scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeEditor() {
  editing = null;
  ui.editor.hidden = true;
}

async function locateInto(values) {
  const location = await geocodeAddress(values);
  if (!location) return false;
  Object.assign(values, location, { location_precision: "census_address_range" });
  ui.editorForm.elements.latitude.value = location.latitude;
  ui.editorForm.elements.longitude.value = location.longitude;
  ui.editorForm.dataset.precision = "census_address_range";
  return true;
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
  if (addressChanged && !coordinatesEdited && !ui.editorForm.dataset.precision && !(await locateInto(values)) && values.address) {
    showMessage(ui.message, "The address was not found, so the map pin was not moved. Enter latitude and longitude to place it.", "error");
  }
  const properties = await buildProperties(values, filters, base ? { base } : { source: "GCC admin", note: "Added by the GCC admin." });
  if (values.gcc_verification === "Verified" && base?.gcc_verification !== "Verified") {
    properties.verification_source = `Verified by the GCC admin on ${new Date().toISOString().slice(0, 10)}.`;
  }
  const row = { properties, review_status: "approved", updated_via: "admin" };
  if (editing.id) check(await client.from("organizations").update(row).eq("id", editing.id));
  else check(await client.from("organizations").insert({ id: properties.id, ...row }));
  showMessage(ui.message, `Saved <strong>${escapeText(properties.name)}</strong>. It is live on the map.`, "success");
  closeEditor();
  await loadPending();
}

async function search(event) {
  event.preventDefault();
  const query = readForm(ui.searchForm).query.replace(/[%_,()]/g, " ");
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
    showMessage(ui.csvMessage, `${ready.length} of ${rows.length} organizations saved and live on the map.${issues}`, ready.length ? "success" : "error");
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
  await loadPending();
}

async function startAdmin() {
  const config = supabaseConfig();
  if (!config) throw new Error("Supabase is not configured yet. Run python -m scripts.sync_supabase after adding the keys to .env.");
  client = window.supabase.createClient(config.url, config.anonKey);
  filters = await loadFilterSchema();
  document.querySelector("#csv-template").href = csvTemplateUrl({ admin: true });

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
      await loadPending();
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
    const found = await locateInto(readForm(ui.editorForm));
    showMessage(ui.message, found ? "Address located; save to keep the new pin." : "The address was not found.", found ? "success" : "error");
  });
  ui.remove.addEventListener("click", async () => {
    try {
      if (!(await deleteOrganization(editing.id, editing.properties.name))) return;
      closeEditor();
      ui.searchResults.innerHTML = "";
      await loadPending();
    } catch (error) {
      fail(error);
    }
  });
  ui.cancelEdit.addEventListener("click", closeEditor);
  ui.csvInput.addEventListener("change", uploadCsv);

  client.auth.onAuthStateChange((_event, session) => {
    // Supabase warns against awaiting its own calls inside this callback.
    setTimeout(() => showSignedIn(session).catch(fail));
  });
}

startAdmin().catch(fail);

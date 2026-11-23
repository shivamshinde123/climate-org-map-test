/**
 * Shared code for the "Add your organization" page (add.html) and the admin
 * page (admin.html): the organization fields, validation, Census geocoding,
 * CSV parsing, and conversion into the same properties object the map uses.
 * On add.html it also runs the public form and CSV upload.
 */

const FORM_SCHEMA_URL = "data/map-schema.json";
const CSV_ROW_LIMIT = 200;

// Text fields every organization has; filter fields come from map-schema.json.
const TEXT_FIELDS = [
  { key: "name", label: "Organization name", required: true },
  { key: "website_url", label: "Website", placeholder: "example.org" },
  { key: "address", label: "Street address", placeholder: "123 Main St" },
  { key: "city", label: "Town / City", required: true },
  { key: "state", label: "State", required: true, placeholder: "MA", maxlength: 2 },
  { key: "postal_code", label: "ZIP code", maxlength: 10 },
];

// CSV header for each filter field (the map stores them under gcc_* names).
const CSV_FILTER_HEADERS = {
  gcc_organization_type: "organization_type",
  gcc_audience_focus: "audience_focus",
  gcc_resilience: "resilience",
  gcc_activity: "activity",
  gcc_action_category: "action_category",
  gcc_climate_category: "climate_category",
  gcc_reach: "reach",
  gcc_verification: "verification",
};

// Older property names the pipeline still writes next to the gcc_* ones.
const LEGACY_FIELDS = {
  gcc_organization_type: "organization_type",
  gcc_audience_focus: "audience_focus",
  gcc_resilience: "adaptation_vs_mitigation",
  gcc_activity: "advocacy_vs_action",
  gcc_action_category: "action_category",
  gcc_climate_category: "climate_categories",
  gcc_reach: "reach",
};

function supabaseConfig() {
  const config = window.SUPABASE_CONFIG ?? {};
  return config.url && config.anonKey ? config : null;
}

async function loadFilterSchema() {
  const response = await fetch(FORM_SCHEMA_URL);
  if (!response.ok) throw new Error(`Schema request failed with ${response.status}`);
  return (await response.json()).filters;
}

function escapeText(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c]);
}

/** Render the text inputs and one select per filter into `container`. */
function renderOrganizationFields(container, filters, { admin = false } = {}) {
  const text = TEXT_FIELDS.map(
    (field) => `
      <label class="field">
        <span>${field.label}${field.required ? " *" : ""}</span>
        <input name="${field.key}" type="text" ${field.required ? "required" : ""}
          ${field.placeholder ? `placeholder="${field.placeholder}"` : ""} ${field.maxlength ? `maxlength="${field.maxlength}"` : ""} />
      </label>`,
  ).join("");
  const selects = filters
    .filter((filter) => admin || filter.field !== "gcc_verification")
    .map((filter) => {
      const fallback = filter.field === "gcc_verification" ? "Not Verified" : "Unknown";
      const options = filter.options
        .map((option) => `<option ${option === fallback ? "selected" : ""}>${escapeText(option)}</option>`)
        .join("");
      return `
        <label class="field">
          <span>${escapeText(filter.label)}</span>
          <select name="${filter.field}">${options}</select>
        </label>`;
    })
    .join("");
  const coordinates = admin
    ? `
      <label class="field"><span>Latitude</span><input name="latitude" type="number" step="any" /></label>
      <label class="field"><span>Longitude</span><input name="longitude" type="number" step="any" /></label>`
    : "";
  container.innerHTML = text + selects + coordinates;
}

function readForm(form) {
  return Object.fromEntries([...new FormData(form).entries()].map(([key, value]) => [key, String(value).trim()]));
}

function fillForm(form, properties) {
  [...form.elements].forEach((element) => {
    if (element.name && properties[element.name] !== undefined && properties[element.name] !== null) {
      element.value = properties[element.name];
    }
  });
}

/**
 * Check one organization's values. Filter values are matched to the schema
 * without regard to case; blank ones become "Unknown". Returns errors and the
 * cleaned values.
 */
function validateOrganization(values, filters, { admin = false } = {}) {
  const errors = [];
  const clean = { ...values };
  TEXT_FIELDS.forEach((field) => {
    clean[field.key] = String(values[field.key] ?? "").trim();
    if (field.required && !clean[field.key]) errors.push(`${field.label} is required`);
  });
  clean.state = clean.state.toUpperCase();
  if (clean.state && !/^[A-Z]{2}$/.test(clean.state)) errors.push("State must be a two-letter code such as MA");
  if (clean.website_url && !/^https?:\/\//i.test(clean.website_url)) clean.website_url = `https://${clean.website_url}`;
  if (clean.website_url) {
    try {
      new URL(clean.website_url);
    } catch {
      errors.push("Website is not a valid address");
    }
  }
  filters.forEach((filter) => {
    if (filter.field === "gcc_verification" && !admin) {
      clean[filter.field] = "Not Verified";
      return;
    }
    const raw = String(values[filter.field] ?? "").trim();
    const fallback = filter.field === "gcc_verification" ? "Not Verified" : "Unknown";
    const match = raw ? filter.options.find((option) => option.toLowerCase() === raw.toLowerCase()) : fallback;
    if (!match) errors.push(`${filter.label} "${raw}" is not one of: ${filter.options.join(", ")}`);
    clean[filter.field] = match ?? fallback;
  });
  return { errors, values: clean };
}

/** Look up a street address with the Census geocoder (JSONP: it sends no CORS headers). */
function geocodeAddress({ address, city, state, postal_code }) {
  if (!address) return Promise.resolve(null);
  const oneLine = [address, city, [state, postal_code].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  return new Promise((resolve) => {
    const callback = `censusGeocode${Date.now()}${Math.random().toString(36).slice(2)}`;
    const script = document.createElement("script");
    const finish = (result) => {
      clearTimeout(timer);
      delete window[callback];
      script.remove();
      resolve(result);
    };
    const timer = setTimeout(() => finish(null), 15000);
    window[callback] = (data) => {
      const match = data?.result?.addressMatches?.[0];
      finish(match ? { latitude: match.coordinates.y, longitude: match.coordinates.x } : null);
    };
    script.onerror = () => finish(null);
    script.src = `https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?${new URLSearchParams({
      address: oneLine,
      benchmark: "Public_AR_Current",
      format: "jsonp",
      callback,
    })}`;
    document.head.append(script);
  });
}

let zipCentroids; // Loaded on first need (~900 KB): ZIP -> [latitude, longitude].

/**
 * Find map coordinates: the street address first, then the ZIP code's center
 * (as the pipeline does) when the Census geocoder cannot match the address.
 * Returns { latitude, longitude, location_precision } or null.
 */
async function locateOrganization(values) {
  const exact = await geocodeAddress(values);
  if (exact) return { ...exact, location_precision: "census_address_range" };
  // ponytail: ZIP center only, no city-center fallback; add data/city centroids if many ZIP-less rows appear.
  const zip = String(values.postal_code ?? "").trim().slice(0, 5);
  if (!/^\d{5}$/.test(zip)) return null;
  zipCentroids ??= fetch("data/zip-centroids.json").then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  const center = (await zipCentroids)[zip];
  return center ? { latitude: center[0], longitude: center[1], location_precision: "zip_level_fallback" } : null;
}

/** Plain-language note about where a located organization was pinned. */
function locationNote(location, values) {
  if (!location) return "No map location could be found, so it has no pin yet.";
  if (location.location_precision === "zip_level_fallback") {
    return `The street address was not found, so it is pinned at the center of ZIP ${values.postal_code.slice(0, 5)}.`;
  }
  return "";
}

/** Stable id from name and state, so the same organization cannot be added twice. */
async function organizationId(name, state) {
  const bytes = new TextEncoder().encode(`${name}|${state}`.toLowerCase());
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return `added_${[...digest].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16)}`;
}

/**
 * Build the map properties for a new organization, or merge edits into an
 * existing one (`base`), keeping every field the form does not cover.
 */
async function buildProperties(values, filters, { base = null, source, note } = {}) {
  const properties = base
    ? { ...base }
    : {
        id: await organizationId(values.name, values.state),
        source_url: "", email: "", phone: "", summary: "",
        ntee_code: "", ntee_label: "", irs_category: "",
        source, notes: note ?? "",
      };
  if (!base) properties.source_id = properties.id;
  TEXT_FIELDS.forEach((field) => (properties[field.key] = values[field.key]));
  filters.forEach((filter) => {
    properties[filter.field] = values[filter.field];
    if (LEGACY_FIELDS[filter.field]) properties[LEGACY_FIELDS[filter.field]] = values[filter.field];
  });
  properties.status = values.gcc_verification;
  properties.validated = values.gcc_verification === "Verified";
  const latitude = Number.parseFloat(values.latitude);
  const longitude = Number.parseFloat(values.longitude);
  if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
    properties.latitude = latitude;
    properties.longitude = longitude;
    properties.location_precision = values.location_precision ?? properties.location_precision ?? "manual";
  } else if (!base) {
    properties.latitude = null;
    properties.longitude = null;
    properties.location_precision = "unavailable";
  }
  return properties;
}

/** Turn an uploaded CSV header row into form names (CSV uses friendly filter names). */
function csvRowToValues(row) {
  const values = {};
  Object.entries(row).forEach(([header, value]) => (values[header.trim().toLowerCase()] = value));
  Object.entries(CSV_FILTER_HEADERS).forEach(([field, header]) => (values[field] = values[header] ?? values[field] ?? ""));
  return values;
}

function parseCsv(file) {
  return new Promise((resolve, reject) => {
    window.Papa.parse(file, {
      header: true,
      skipEmptyLines: "greedy",
      complete: (result) => resolve(result.data),
      error: reject,
    });
  });
}

// One example organization, used for the CSV template and the admin rules.
const CSV_EXAMPLE = {
  name: "Example Climate Group", website_url: "example.org", address: "123 Main St", city: "Boston",
  state: "MA", postal_code: "02130", organization_type: "Nonprofit / Grassroots", audience_focus: "Residents",
  resilience: "Both", activity: "Action", action_category: "Community Engagement",
  climate_category: "Energy Efficiency", reach: "Town / City", verification: "Not Verified",
};

function csvHeaders({ admin = false } = {}) {
  const filterHeaders = Object.values(CSV_FILTER_HEADERS).filter((header) => admin || header !== "verification");
  return [...TEXT_FIELDS.map((field) => field.key), ...filterHeaders];
}

function csvExampleText({ admin = false } = {}) {
  const headers = csvHeaders({ admin });
  return [headers, headers.map((header) => CSV_EXAMPLE[header])]
    .map((row) => row.map((cell) => `"${cell}"`).join(","))
    .join("\n");
}

function csvTemplateUrl({ admin = false } = {}) {
  return `data:text/csv;charset=utf-8,${encodeURIComponent(`${csvExampleText({ admin })}\n`)}`;
}

/**
 * Validate, geocode and build properties for every CSV row. `onProgress`
 * receives a status line. Returns { ready: [properties], problems: [text] }.
 */
async function prepareCsvRows(rows, filters, { admin = false, source, note, onProgress = () => {} } = {}) {
  const ready = [];
  const problems = [];
  const seen = new Set();
  for (const [index, row] of rows.entries()) {
    const line = index + 2; // Header is line 1.
    const { errors, values } = validateOrganization(csvRowToValues(row), filters, { admin });
    if (errors.length) {
      problems.push(`Row ${line}: ${errors.join("; ")}`);
      continue;
    }
    onProgress(`Locating row ${line} of ${rows.length + 1}…`);
    const location = await locateOrganization(values);
    if (location) Object.assign(values, location);
    const note = locationNote(location, values);
    if (note) problems.push(`Row ${line} (${values.name}): ${note}`);
    const properties = await buildProperties(values, filters, { source, note });
    if (seen.has(properties.id)) {
      problems.push(`Row ${line}: duplicate of an earlier row (same name and state); skipped`);
      continue;
    }
    seen.add(properties.id);
    ready.push(properties);
  }
  return { ready, problems };
}

function showMessage(element, html, kind = "info") {
  element.hidden = false;
  element.className = `notice notice-${kind}`;
  element.innerHTML = html;
}

/* ---------------- Public "Add your organization" page ---------------- */

async function submitPublic(config, properties) {
  const rows = (Array.isArray(properties) ? properties : [properties]).map((p) => ({
    id: p.id,
    properties: p,
    review_status: "pending",
    updated_via: "public_form",
  }));
  const response = await fetch(`${config.url}/rest/v1/organizations`, {
    method: "POST",
    headers: {
      apikey: config.anonKey,
      Authorization: `Bearer ${config.anonKey}`,
      "Content-Type": "application/json",
      Prefer: "return=minimal",
    },
    body: JSON.stringify(rows),
  });
  if (response.status === 409) throw new Error("This organization (same name and state) has already been submitted.");
  if (!response.ok) throw new Error(`The database refused the submission (${response.status}).`);
}

async function startAddPage() {
  const form = document.querySelector("#add-form");
  const message = document.querySelector("#add-message");
  const csvInput = document.querySelector("#csv-file");
  const csvMessage = document.querySelector("#csv-message");
  document.querySelector("#csv-template").href = csvTemplateUrl();
  const config = supabaseConfig();
  const filters = await loadFilterSchema();
  renderOrganizationFields(document.querySelector("#add-fields"), filters);
  if (!config) {
    showMessage(message, "Submissions are not open yet. Please check back soon.", "error");
    form.querySelector("button[type=submit]").disabled = true;
    csvInput.disabled = true;
    return;
  }
  const publicOptions = { source: "Public submission", note: "Submitted on the Add your organization page." };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    const { errors, values } = validateOrganization(readForm(form), filters);
    if (errors.length) return showMessage(message, errors.map(escapeText).join("<br>"), "error");
    button.disabled = true;
    showMessage(message, "Locating the address…");
    try {
      const location = await locateOrganization(values);
      if (location) Object.assign(values, location);
      await submitPublic(config, await buildProperties(values, filters, publicOptions));
      form.reset();
      const note = locationNote(location, values);
      showMessage(message, `Thank you. <strong>${escapeText(values.name)}</strong> was submitted and will appear on the map once it is reviewed.${note ? ` ${escapeText(note)}` : ""}`, "success");
    } catch (error) {
      showMessage(message, escapeText(error.message), "error");
    } finally {
      button.disabled = false;
    }
  });

  csvInput.addEventListener("change", async () => {
    const file = csvInput.files[0];
    if (!file) return;
    csvInput.disabled = true;
    try {
      const rows = await parseCsv(file);
      if (!rows.length) throw new Error("The file has no rows.");
      if (rows.length > CSV_ROW_LIMIT) throw new Error(`Please upload at most ${CSV_ROW_LIMIT} organizations at a time.`);
      const { ready, problems } = await prepareCsvRows(rows, filters, {
        ...publicOptions,
        onProgress: (text) => showMessage(csvMessage, escapeText(text)),
      });
      if (ready.length) await submitPublic(config, ready);
      const issues = problems.length ? `<ul>${problems.map((p) => `<li>${escapeText(p)}</li>`).join("")}</ul>` : "";
      showMessage(csvMessage, `${ready.length} of ${rows.length} organizations submitted for review.${issues}`, ready.length ? "success" : "error");
    } catch (error) {
      showMessage(csvMessage, escapeText(error.message), "error");
    } finally {
      csvInput.value = "";
      csvInput.disabled = false;
    }
  });
}

if (document.body.dataset.page === "add") {
  startAddPage().catch((error) => {
    console.error(error);
    showMessage(document.querySelector("#add-message"), "The form could not be loaded. Please try again later.", "error");
  });
}

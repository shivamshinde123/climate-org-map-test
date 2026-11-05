/**
 * Climate Org Mapping browser application.
 *
 * The page loads a generated GeoJSON dataset and the controlled filter schema,
 * canonicalizes legacy values, renders a searchable result list, and supplies
 * filtered points to MapLibre. OpenStreetMap provides only the raster basemap;
 * organization coordinates and attributes come from the local pipeline output.
 */

// The explicit version bypasses stale browser/proxy caches after data releases.
const ASSET_VERSION = "20261105-1";
const DATA_URL = `data/organizations.geojson?v=${ASSET_VERSION}`;
const SCHEMA_URL = `data/map-schema.json?v=${ASSET_VERSION}`;
const MAX_RESULTS = 80;
const VERIFICATION_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScmfNbX1kS9CqZ3oEc7ARCFda46mWpNpz1lN1QKC0KjmOz4KQ/viewform";

// Legacy lowercase values are normalized before counting or comparison. This
// avoids visually duplicated options such as "action" and "Action".
const CANONICAL_FILTER_VALUES = new Map([
  ["adaptation", "Adaptation"],
  ["both", "Both"],
  ["mitigation", "Mitigation"],
  ["action", "Action"],
  ["advocacy", "Advocacy"],
  ["unknown", "Unknown"],
]);

// Resolve static DOM references once. The HTML contract guarantees these nodes.
const elements = {
  shell: document.querySelector(".atlas-shell"),
  sidebarToggle: document.querySelector("#sidebar-toggle"),
  form: document.querySelector("#filters"),
  search: document.querySelector("#search"),
  state: document.querySelector("#state-filter"),
  ntee: document.querySelector("#ntee-filter"),
  visibleCount: document.querySelector("#visible-count"),
  totalCount: document.querySelector("#total-count"),
  results: document.querySelector("#results"),
  template: document.querySelector("#result-template"),
  filterSelects: [...document.querySelectorAll("select[data-field]")],
};

// Mutable application state is intentionally small: source features are kept
// separately from the current view, and MapLibre owns rendered map state.
let allFeatures = [];
let filteredFeatures = [];
let map;
let filterOptions = {};

function text(value) {
  // Null-safe string conversion used at every external-data boundary.
  return String(value ?? "");
}

function canonicalFilterValue(field, value) {
  // Discard old serialized-array reach values; they are not valid schema values.
  const cleaned = text(value).trim();
  if (!cleaned) return "";
  if (field === "gcc_reach" && (cleaned.startsWith("[") || cleaned === "[]")) return "";
  return CANONICAL_FILTER_VALUES.get(cleaned.toLocaleLowerCase()) ?? cleaned;
}

function uniqueCanonicalOptions(field, values) {
  // Deduplicate case-insensitively while preserving the schema's display order.
  const seen = new Set();
  return values
    .map((value) => canonicalFilterValue(field, value))
    .filter((value) => {
      const key = value.toLocaleLowerCase();
      if (!value || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function searchable(properties) {
  // Build a single normalized search document from user-recognizable identity.
  return [
    properties.name,
    properties.address,
    properties.city,
    properties.state,
    properties.postal_code,
    properties.source_id,
  ]
    .map(text)
    .join(" ")
    .toLocaleLowerCase();
}

function escapeHtml(value) {
  // Popup content is an HTML string, so every dataset value must be escaped.
  return text(value).replace(
    /[&<>'"]/g,
    (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;",
    })[character],
  );
}

function safeExternalUrl(value) {
  // Only ordinary web links may enter href attributes; reject script/data URLs.
  try {
    const url = new URL(text(value).trim());
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function formatNumber(value) {
  // Counts use locale separators without coupling filtering to presentation.
  return new Intl.NumberFormat("en-US").format(value);
}

function fillSelect(select, values, counts = null) {
  // Build options off-DOM to avoid repeated layout work on large schemas.
  const fragment = document.createDocumentFragment();
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    const count = counts?.get(value);
    option.textContent = count === undefined ? value : `${value} · ${formatNumber(count)}`;
    option.disabled = count === 0;
    fragment.append(option);
  });
  select.append(fragment);
}

function featureCollection(features) {
  // MapLibre sources require a complete GeoJSON object, not a feature array.
  return { type: "FeatureCollection", features };
}

function popupMarkup(properties) {
  // The popup deliberately exposes only the product-approved identity, schema,
  // website summary, and verification fields—not raw IRS/internal metadata.
  const street = text(properties.address).trim();
  const locality = [properties.city, properties.state].filter(Boolean).map(text).join(", ");
  const cityStatePostal = [locality, properties.postal_code].filter(Boolean).map(text).join(" ");
  const addressLines = [street, cityStatePostal]
    .filter(Boolean)
    .map((line) => escapeHtml(line))
    .join("<br>");
  const websiteUrl = safeExternalUrl(properties.website_url);
  const summary = text(properties.summary).trim();
  const email = text(properties.email).trim();
  const phone = text(properties.phone).trim();
  const phoneDigits = phone.replace(/[^\d+]/g, "");
  const contactUrl = safeExternalUrl(properties.contact_page_url);
  const contactRows = [
    /^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/.test(email)
      ? `<div><dt>Email:</dt><dd><a class="popup-link" href="mailto:${escapeHtml(email)}">${escapeHtml(email)}</a></dd></div>`
      : "",
    phoneDigits.length >= 7
      ? `<div><dt>Phone:</dt><dd><a class="popup-link" href="tel:${escapeHtml(phoneDigits)}">${escapeHtml(phone)}</a></dd></div>`
      : "",
    contactUrl
      ? `<div><dt>Contact:</dt><dd><a class="popup-link" href="${escapeHtml(contactUrl)}" target="_blank" rel="noopener noreferrer">Contact page</a></dd></div>`
      : "",
  ].join("");
  const websiteAndSummary = websiteUrl || summary || contactRows
    ? `
      <section class="popup-profile">
        ${websiteUrl ? `<a class="popup-link" href="${escapeHtml(websiteUrl)}" target="_blank" rel="noopener noreferrer">Website</a>` : ""}
        ${summary ? `<p class="popup-summary">${escapeHtml(summary)}</p>` : ""}
        ${contactRows ? `<dl class="popup-fields">${contactRows}</dl>` : ""}
      </section>
    `
    : "";
  return `
    <div class="popup-name">${escapeHtml(properties.name)}</div>
    <div class="popup-address">${addressLines || "Address unavailable"}</div>
    <dl class="popup-fields">
      <div><dt>Type:</dt><dd>${escapeHtml(properties.gcc_organization_type || "Unknown")}</dd></div>
      <div><dt>Audience:</dt><dd>${escapeHtml(properties.gcc_audience_focus || "Unknown")}</dd></div>
      <div><dt>Resilience:</dt><dd>${escapeHtml(properties.gcc_resilience || "Unknown")}</dd></div>
      <div><dt>Activity:</dt><dd>${escapeHtml(properties.gcc_activity || "Unknown")}</dd></div>
      <div><dt>Action:</dt><dd>${escapeHtml(properties.gcc_action_category || "Unknown")}</dd></div>
      <div><dt>Climate:</dt><dd>${escapeHtml(properties.gcc_climate_category || "Unknown")}</dd></div>
      <div><dt>Reach:</dt><dd>${escapeHtml(properties.gcc_reach || "Unknown")}</dd></div>
    </dl>
    ${websiteAndSummary}
    <a class="popup-link popup-verify" href="${VERIFICATION_FORM_URL}" target="_blank" rel="noopener noreferrer">Click to claim and verify</a>
  `;
}

function fitPopupInView(popup) {
  // Pan just enough that the whole card is inside the map, so a pin near an
  // edge doesn't push the name or contacts off-screen.
  const card = popup.getElement()?.getBoundingClientRect();
  if (!card) return;
  const frame = map.getContainer().getBoundingClientRect();
  const pad = 12;
  const dx = Math.min(0, frame.right - pad - card.right) || Math.max(0, frame.left + pad - card.left);
  const dy = Math.min(0, frame.bottom - pad - card.bottom) || Math.max(0, frame.top + pad - card.top);
  if (dx || dy) map.panBy([-dx, -dy], { duration: 250 });
}

function openFeaturePopup(feature) {
  // Make long popup content keyboard-scrollable and stop its scroll gestures
  // from zooming/panning the map underneath it. Focusing the card itself (not
  // its first link) keeps it from scrolling past the organization's name.
  const popup = new maplibregl.Popup({ offset: 12, maxWidth: "320px", focusAfterOpen: false })
    .setLngLat(feature.geometry.coordinates)
    .setHTML(popupMarkup(feature.properties))
    .addTo(map);
  const content = popup.getElement()?.querySelector(".maplibregl-popup-content");
  if (content) {
    content.tabIndex = 0;
    content.setAttribute("aria-label", `${text(feature.properties.name)} organization details`);
    // MapLibre appends the close button after the content; first in order lets
    // its sticky positioning hold it in the corner while the card scrolls.
    const close = content.querySelector(".maplibregl-popup-close-button");
    if (close) content.prepend(close);
    content.focus({ preventScroll: true });
  }
  ["wheel", "touchmove", "pointerdown"].forEach((eventName) => {
    content?.addEventListener(eventName, (event) => event.stopPropagation(), { passive: true });
  });
  if (map.isMoving()) map.once("moveend", () => fitPopupInView(popup));
  else fitPopupInView(popup);
  return popup;
}

function showFeature(feature) {
  // Result-list selection preserves a closer existing zoom while guaranteeing
  // enough detail to distinguish the selected point.
  const coordinates = feature.geometry.coordinates;
  map.flyTo({ center: coordinates, zoom: Math.max(map.getZoom(), 7), essential: true });
  openFeaturePopup(feature);
}

function renderResults() {
  // Limit sidebar DOM size while the map continues to display every match.
  elements.results.replaceChildren();
  const fragment = document.createDocumentFragment();

  filteredFeatures.slice(0, MAX_RESULTS).forEach((feature) => {
    const card = elements.template.content.firstElementChild.cloneNode(true);
    const properties = feature.properties;
    card.querySelector(".result-code").textContent = properties.ntee_code;
    card.querySelector(".result-name").textContent = properties.name;
    card.querySelector(".result-location").textContent =
      [properties.city, properties.state, properties.postal_code].filter(Boolean).join(", ") ||
      "Location unavailable";
    card.setAttribute("aria-label", `Show ${properties.name} on the map`);
    card.addEventListener("click", () => showFeature(feature));
    fragment.append(card);
  });

  if (filteredFeatures.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No organizations match this field note. Try clearing a filter.";
    fragment.append(empty);
  }

  elements.results.append(fragment);
}

function applyFilters() {
  // Facets combine with AND semantics; blank selections mean "all values".
  const query = elements.search.value.trim().toLocaleLowerCase();

  filteredFeatures = allFeatures.filter((feature) => {
    const properties = feature.properties;
    const matchesFacets = elements.filterSelects.every((select) => {
      const selected = select.value;
      return !selected || text(properties[select.dataset.field]) === selected;
    });
    return (!query || searchable(properties).includes(query)) && matchesFacets;
  });

  elements.visibleCount.textContent = formatNumber(filteredFeatures.length);
  renderResults();

  // Map initialization is asynchronous, so filtering may precede source setup.
  const source = map?.getSource("organizations");
  if (source) source.setData(featureCollection(filteredFeatures));
}

function initializeMap(data) {
  // MapLibre renders organization layers over OpenStreetMap raster tiles. The
  // muted raster styling keeps bright organization markers visually dominant.
  map = new maplibregl.Map({
    container: "map",
    center: [-98.5, 39.5],
    zoom: 3.25,
    minZoom: 2.4,
    style: {
      version: 8,
      sources: {
        basemap: {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          tileSize: 256,
          attribution: "© OpenStreetMap contributors",
        },
      },
      layers: [
        {
          id: "basemap",
          type: "raster",
          source: "basemap",
          paint: { "raster-saturation": -0.78, "raster-opacity": 0.72, "raster-contrast": -0.08 },
        },
      ],
    },
  });

  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

  map.on("load", () => {
    // Client-side clustering keeps the initial national view legible and avoids
    // drawing thousands of fully overlapping individual points.
    map.addSource("organizations", {
      type: "geojson",
      data,
      cluster: true,
      clusterMaxZoom: 11,
      clusterRadius: 46,
    });

    map.addLayer({
      id: "clusters",
      type: "circle",
      source: "organizations",
      filter: ["has", "point_count"],
      paint: {
        "circle-color": ["step", ["get", "point_count"], "#e8bd54", 100, "#6f8b62", 750, "#153d32"],
        "circle-radius": ["step", ["get", "point_count"], 15, 100, 21, 750, 28],
        "circle-stroke-width": 2,
        "circle-stroke-color": "#faf6eb",
      },
    });

    map.addLayer({
      id: "cluster-count",
      type: "symbol",
      source: "organizations",
      filter: ["has", "point_count"],
      layout: {
        "text-field": ["get", "point_count_abbreviated"],
        "text-font": ["Open Sans Bold"],
        "text-size": 11,
      },
      paint: { "text-color": "#faf6eb" },
    });

    map.addLayer({
      id: "unclustered-point",
      type: "circle",
      source: "organizations",
      filter: ["!", ["has", "point_count"]],
      paint: {
        "circle-color": "#f05a35",
        "circle-radius": 5,
        "circle-stroke-width": 1.5,
        "circle-stroke-color": "#faf6eb",
      },
    });

    map.on("click", "clusters", async (event) => {
      // Ask the source for the first zoom at which the selected cluster expands.
      const features = map.queryRenderedFeatures(event.point, { layers: ["clusters"] });
      const cluster = features[0];
      if (!cluster) return;
      const zoom = await map
        .getSource("organizations")
        .getClusterExpansionZoom(cluster.properties.cluster_id);
      map.easeTo({ center: cluster.geometry.coordinates, zoom });
    });

    map.on("click", "unclustered-point", (event) => {
      const feature = event.features?.[0];
      if (!feature) return;
      openFeaturePopup(feature);
    });

    ["clusters", "unclustered-point"].forEach((layer) => {
      map.on("mouseenter", layer, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; });
    });

  });
}

async function start() {
  // Data and schema are independent static assets and can be fetched in parallel.
  try {
    const [response, schemaResponse] = await Promise.all([
      fetch(DATA_URL),
      fetch(SCHEMA_URL),
    ]);
    if (!response.ok) throw new Error(`Dataset request failed with ${response.status}`);
    if (!schemaResponse.ok) throw new Error(`Schema request failed with ${schemaResponse.status}`);
    const [data, schema] = await Promise.all([response.json(), schemaResponse.json()]);
    // The schema controls order and allowed labels; observed values are appended
    // later as a compatibility safeguard for older generated datasets.
    filterOptions = Object.fromEntries(
      schema.filters.map((definition) => [
        definition.field,
        uniqueCanonicalOptions(definition.field, definition.options),
      ]),
    );
    // Records without a ZIP or city match carry null geometry and cannot be shown.
    allFeatures = (data.features ?? []).filter((feature) => feature.geometry);
    // Canonicalize records once at startup so filtering remains a cheap equality
    // comparison on every keystroke or select change.
    schema.filters.forEach(({ field }) => {
      allFeatures.forEach((feature) => {
        const current = feature.properties[field];
        if (current !== undefined) {
          feature.properties[field] = canonicalFilterValue(field, current);
        }
      });
    });
    filteredFeatures = allFeatures;

    // Populate each facet with live counts. Zero-count configured choices stay
    // visible (and disabled), documenting the complete controlled vocabulary.
    elements.filterSelects.forEach((select) => {
      const field = select.dataset.field;
      const dataValues = allFeatures
        .map((feature) => canonicalFilterValue(field, feature.properties[field]))
        .filter(Boolean);
      const configuredValues = filterOptions[field] ?? [];
      const values = uniqueCanonicalOptions(field, [...configuredValues, ...dataValues]);
      if (!configuredValues.length) values.sort();
      const counts = new Map(values.map((value) => [value, 0]));
      dataValues.forEach((value) => counts.set(value, (counts.get(value) ?? 0) + 1));
      fillSelect(select, values, counts);
    });
    elements.totalCount.textContent = `${formatNumber(allFeatures.length)} IRS candidates`;
    elements.visibleCount.textContent = formatNumber(allFeatures.length);
    renderResults();
    initializeMap(data);

    elements.form.addEventListener("input", applyFilters);
    elements.form.addEventListener("reset", () => window.setTimeout(applyFilters));
    elements.sidebarToggle.addEventListener("click", () => {
      // The layout transition changes the map container width; resize after the
      // CSS animation so MapLibre recomputes its canvas and interaction bounds.
      const collapsed = elements.shell.classList.toggle("sidebar-collapsed");
      elements.sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
      elements.sidebarToggle.setAttribute(
        "aria-label",
        collapsed ? "Show filters and results" : "Hide filters and results",
      );
      elements.sidebarToggle.querySelector("span").textContent = collapsed ? "›" : "‹";
      window.setTimeout(() => map?.resize(), 260);
    });
  } catch (error) {
    // Keep the shell usable and provide an actionable message when static assets
    // are absent, malformed, or served without a local HTTP server.
    console.error(error);
    elements.visibleCount.textContent = "0";
    elements.totalCount.textContent = "Dataset unavailable";
    elements.results.innerHTML = `
      <div class="empty-state">
        The atlas data could not be loaded. Run the IRS build script, then serve the app through a local web server.
      </div>`;
  }
}

start();


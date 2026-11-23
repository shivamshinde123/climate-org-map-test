/**
 * Climate Org Mapping browser application.
 *
 * The page loads a generated GeoJSON dataset and the controlled filter schema,
 * canonicalizes legacy values, renders a searchable result list, and supplies
 * filtered points to MapLibre. OpenStreetMap provides only the raster basemap;
 * organization coordinates and attributes come from the local pipeline output.
 */

// The explicit version bypasses stale browser/proxy caches after data releases.
const ASSET_VERSION = "20261123-17";
const DATA_URL = `data/organizations.geojson?v=${ASSET_VERSION}`;
const SCHEMA_URL = `data/map-schema.json?v=${ASSET_VERSION}`;
const MAX_RESULTS = 80;

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
  visibleCount: document.querySelector("#visible-count"),
  results: document.querySelector("#results"),
  template: document.querySelector("#result-template"),
  filterMenus: [...document.querySelectorAll(".multi[data-field]")],
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

function matchesValue(field, value, selected) {
  // A combined audience ("Residents / Businesses") also matches each of its parts.
  if (field !== "gcc_audience_focus") return value === selected;
  const parts = value.split(" / ");
  return selected.split(" / ").every((part) => parts.includes(part));
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

function fillMenu(menu, values, counts) {
  // One checkbox per value, built off-DOM; zero-count values stay visible but disabled.
  const fragment = document.createDocumentFragment();
  values.forEach((value) => {
    const option = document.createElement("label");
    option.className = "multi-option";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = value;
    box.disabled = counts.get(value) === 0;
    const name = document.createElement("span");
    name.textContent = value;
    const count = document.createElement("span");
    count.className = "multi-count";
    count.textContent = formatNumber(counts.get(value) ?? 0);
    option.append(box, name, count);
    fragment.append(option);
  });
  menu.querySelector(".multi-options").append(fragment);
}

function checkedValues(menu) {
  return [...menu.querySelectorAll("input:checked")].map((box) => box.value);
}

function updateMenuLabel(menu) {
  // "All …" when nothing is checked, the value itself for one, a count for more.
  const checked = checkedValues(menu);
  menu.querySelector("summary").textContent =
    checked.length === 0 ? menu.dataset.all : checked.length === 1 ? checked[0] : `${checked.length} selected`;
  menu.classList.toggle("has-selection", checked.length > 0);
}

async function applyLiveChanges(features) {
  // The static file is the pipeline snapshot; Supabase holds what changed since
  // (admin edits and approved submissions). Removed rows leave the map.
  const config = window.SUPABASE_CONFIG ?? {};
  if (!config.url || !config.anonKey) return features;
  try {
    const response = await fetch(
      `${config.url}/rest/v1/organizations?select=id,properties,review_status&updated_via=neq.pipeline&review_status=in.(approved,removed)`,
      { headers: { apikey: config.anonKey, Authorization: `Bearer ${config.anonKey}` } },
    );
    if (!response.ok) throw new Error(`Live changes request failed with ${response.status}`);
    const byId = new Map(features.map((feature) => [feature.properties.id, feature]));
    (await response.json()).forEach(({ id, properties, review_status }) => {
      if (review_status === "removed") return byId.delete(id);
      const { latitude, longitude } = properties;
      const geometry = Number.isFinite(latitude) && Number.isFinite(longitude)
        ? { type: "Point", coordinates: [longitude, latitude] }
        : null;
      byId.set(id, { type: "Feature", geometry, properties });
    });
    return [...byId.values()];
  } catch (error) {
    // The map still works from the snapshot if the database is unreachable.
    console.warn(error);
    return features;
  }
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
  const verified = properties.gcc_verification === "Verified";
  const websiteUrl = safeExternalUrl(properties.website_url);
  // Only shown when there is no website: for small groups it is often their only page.
  const facebookUrl = websiteUrl ? "" : safeExternalUrl(properties.facebook_url);
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
      ? `<div><dt>Contact:</dt><dd><a class="popup-link" href="${escapeHtml(contactUrl)}" target="_blank" rel="noopener noreferrer">Contact page →</a></dd></div>`
      : "",
  ].join("");
  const websiteAndSummary = websiteUrl || facebookUrl || summary || contactRows
    ? `
      <section class="popup-profile">
        ${websiteUrl ? `<a class="popup-link" href="${escapeHtml(websiteUrl)}" target="_blank" rel="noopener noreferrer">Website →</a>` : ""}
        ${facebookUrl ? `<a class="popup-link" href="${escapeHtml(facebookUrl)}" target="_blank" rel="noopener noreferrer">Facebook page →</a>` : ""}
        ${summary ? `<p class="popup-summary">${escapeHtml(summary)}</p>` : ""}
        ${contactRows ? `<dl class="popup-fields">${contactRows}</dl>` : ""}
      </section>
    `
    : "";
  return `
    ${verified ? `<span class="popup-verified">Verified organization</span>` : ""}
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
    ${verified ? "" : `<a class="popup-link popup-verify" href="${escapeHtml(verifySurveyUrl(properties))}" target="_blank" rel="noopener">Claim and verify this listing</a>`}
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
  // Filters combine with AND; within one filter any checked value matches.
  // A filter with nothing checked means "all values".
  const query = elements.search.value.trim().toLocaleLowerCase();
  elements.filterMenus.forEach(updateMenuLabel);
  const active = elements.filterMenus
    .map((menu) => [menu.dataset.field, checkedValues(menu)])
    .filter(([, checked]) => checked.length);

  filteredFeatures = allFeatures.filter((feature) => {
    const properties = feature.properties;
    const matchesFacets = active.every(([field, checked]) => {
      const value = canonicalFilterValue(field, properties[field]);
      return checked.some((selected) => matchesValue(field, value, selected));
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
      // Symbol layers (the cluster counts) need a glyph server for "Open Sans Bold".
      glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
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
          // Fully neutral basemap: the palette allows no blues, reds or purples.
          paint: { "raster-saturation": -1, "raster-opacity": 0.62, "raster-contrast": -0.12 },
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
        "circle-color": ["step", ["get", "point_count"], "#698e79", 100, "#1c3a13"],
        "circle-radius": ["step", ["get", "point_count"], 15, 100, 21, 750, 28],
        "circle-stroke-width": 2,
        "circle-stroke-color": "#fcfcf7",
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
      paint: { "text-color": "#fcfcf7" },
    });

    map.addLayer({
      id: "unclustered-point",
      type: "circle",
      source: "organizations",
      filter: ["!", ["has", "point_count"]],
      paint: {
        // Lime is reserved for small emphasis: single organizations.
        "circle-color": "#d3fa99",
        "circle-radius": 5.5,
        "circle-stroke-width": 1.5,
        "circle-stroke-color": "#1c3a13",
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
    data.features = await applyLiveChanges(data.features ?? []);
    allFeatures = data.features.filter((feature) => feature.geometry);
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
    elements.filterMenus.forEach((menu) => {
      const field = menu.dataset.field;
      const dataValues = allFeatures
        .map((feature) => canonicalFilterValue(field, feature.properties[field]))
        .filter(Boolean);
      const configuredValues = filterOptions[field] ?? [];
      const values = uniqueCanonicalOptions(field, [...configuredValues, ...dataValues]);
      if (!configuredValues.length) values.sort();
      const counts = new Map(values.map((value) => [value, dataValues.filter((data) => matchesValue(field, data, value)).length]));
      fillMenu(menu, values, counts);
    });
    elements.visibleCount.textContent = formatNumber(allFeatures.length);
    renderResults();
    initializeMap(data);

    elements.form.addEventListener("input", applyFilters);
    elements.form.addEventListener("reset", () => window.setTimeout(applyFilters));
    // Only one checkbox menu is open at a time; outside clicks and Escape close it.
    elements.filterMenus.forEach((menu) => {
      menu.addEventListener("toggle", () => {
        if (menu.open) elements.filterMenus.forEach((other) => other !== menu && (other.open = false));
      });
    });
    document.addEventListener("click", (event) => {
      elements.filterMenus.forEach((menu) => {
        if (menu.open && !menu.contains(event.target)) menu.open = false;
      });
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      const open = elements.filterMenus.find((menu) => menu.open);
      if (open) {
        open.open = false;
        open.querySelector("summary").focus();
      }
    });
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
    elements.results.innerHTML = `
      <div class="empty-state">
        The organization data could not be loaded. Please try again later.
      </div>`;
  }
}

start();


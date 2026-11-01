/**
 * Test suite for Modal Mover Bien de Ubicación in Frontend
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const htmlPath = path.join(__dirname, "../index.html");
const html = fs.readFileSync(htmlPath, "utf-8");

const cssPath = path.join(__dirname, "../css/components.css");
const css = fs.readFileSync(cssPath, "utf-8");

const renderJsPath = path.join(__dirname, "../js/render.js");
const renderJs = fs.readFileSync(renderJsPath, "utf-8");

test("HTML Structure: modal-mover-bien exists with all required controls", () => {
  assert.match(html, /<dialog[^>]*id="modal-mover-bien"/, "modal-mover-bien dialog must exist");
  assert.match(html, /id="modal-mover-title"[^>]*>Mover bien de ubicación<\/h2>/, "dialog title must exist");
  assert.match(html, /id="btn-cerrar-modal-mover"/, "close button must exist");
  assert.match(html, /id="mover-bien-nombre"/, "asset name element must exist");
  assert.match(html, /id="mover-bien-codigo"/, "asset internal code element must exist");
  assert.match(html, /id="mover-origen-display"/, "current location display must exist");
  assert.match(html, /id="btn-dest-mode-existing"/, "mode existing tab button must exist");
  assert.match(html, /id="btn-dest-mode-new"/, "mode new tab button must exist");
  assert.match(html, /id="mover-destino-select"/, "destination select dropdown must exist");
  assert.match(html, /id="mover-nuevo-destino-nombre"/, "new destination text input must exist");
  assert.match(html, /id="btn-cancelar-mover"/, "cancel button must exist");
  assert.match(html, /id="btn-confirmar-traslado"/, "submit transfer button must exist");
});

test("CSS: Styles for modal-dialog and readonly-location-box exist", () => {
  assert.match(css, /\.modal-dialog\s*\{/, "modal-dialog styles must exist");
  assert.match(css, /\.modal-dialog::backdrop\s*\{/, "modal-dialog::backdrop styles must exist");
  assert.match(css, /\.readonly-location-box\s*\{/, "readonly-location-box styles must exist");
  assert.match(css, /\.modal-asset-summary\s*\{/, "modal-asset-summary styles must exist");
});

test("Render: renderBienesView produces 'Mover' button in action column", () => {
  assert.match(renderJs, /btn-mover-bien/, "renderBienesView must include btn-mover-bien class");
  assert.match(renderJs, />Mover<\/button>/, "renderBienesView must display 'Mover' text on button");
});

test("Validation & Quick Location Flow: enforces min 3 chars in modal and supports quick creation from Nuevo bien", () => {
  const appJs = fs.readFileSync(path.join(__dirname, "../js/app.js"), "utf-8");

  // 1. Modal 'Mover bien' enforces at least 3 characters for inline new location name
  assert.match(html, /id="mover-nuevo-destino-nombre"[^>]*minlength="3"/);
  assert.match(appJs, /newName\.length < 3/);
  assert.match(appJs, /Ingresá el nombre de la nueva ubicación \(mínimo 3 caracteres\)/);
  assert.doesNotMatch(appJs, /newName\.length < 2/);

  // 2. Standalone location creation form and quick-access from 'Nuevo bien' exist and auto-select created location
  assert.match(appJs, /configureNuevaUbicacionReturnTarget\("Nuevo bien"\)/);
  assert.match(appJs, /selectCreatedLocationInAssetForm\(createdLoc\)/);
  assert.match(appJs, /Complete el nombre de la ubicación \(mínimo 3 caracteres\)/);
});

test("Behavioral: quick location creation from Nuevo bien preserves asset form data and auto-selects created location", async () => {
  const appJs = fs.readFileSync(path.join(__dirname, "../js/app.js"), "utf-8");

  const listeners = new Map();
  const elements = new Map();

  function makeEl(id, extra = {}) {
    const elListeners = new Map();
    const classSet = new Set(extra.classes || []);
    const attrs = new Map();
    const el = {
      id,
      value: extra.value || "",
      innerHTML: extra.innerHTML || "",
      textContent: extra.textContent || "",
      hidden: extra.hidden ?? false,
      disabled: false,
      required: false,
      style: { display: extra.display || "" },
      dataset: extra.dataset || {},
      options: extra.options || [],
      classList: {
        add: (c) => classSet.add(c),
        remove: (c) => classSet.delete(c),
        toggle: (c, force) => (force ? classSet.add(c) : classSet.delete(c)),
        contains: (c) => classSet.has(c),
      },
      setAttribute: (k, v) => attrs.set(k, String(v)),
      removeAttribute: (k) => attrs.delete(k),
      getAttribute: (k) => attrs.get(k) || null,
      addEventListener: (evt, cb) => {
        if (!elListeners.has(evt)) elListeners.set(evt, []);
        elListeners.get(evt).push(cb);
      },
      trigger: async (evt, eventObj = {}) => {
        const cbs = elListeners.get(evt) || [];
        for (const cb of cbs) {
          await cb({ preventDefault: () => {}, target: el, ...eventObj });
        }
      },
      focus: () => {},
      reset: function () {
        if (this.onReset) this.onReset();
      },
      closest: (sel) => (extra.closest ? extra.closest(sel) : null),
      matches: (sel) => sel.includes(`#${id}`),
      querySelector: (sel) => {
        if (sel.startsWith("#")) return elements.get(sel.slice(1)) || null;
        if (sel === "option[value='__NEW__']") return el.options.find(o => o.value === "__NEW__") || null;
        return null;
      },
      querySelectorAll: () => [],
      insertBefore: (newOpt, refOpt) => {
        const idx = el.options.indexOf(refOpt);
        if (idx >= 0) el.options.splice(idx, 0, newOpt);
        else el.options.push(newOpt);
      },
      appendChild: (newOpt) => el.options.push(newOpt),
    };
    elements.set(id, el);
    return el;
  }

  // Required baseline elements for app.js bootstrap
  makeEl("date-range", { value: "90" });
  makeEl("country-search");
  makeEl("global-search");
  makeEl("mobile-nav");
  makeEl("toast");
  makeEl("api-status");
  makeEl("brightness-toggle");
  makeEl("profile-menu");
  makeEl("export-button");
  makeEl("google-link-button");
  makeEl("page-title");
  makeEl("page-subtitle");
  makeEl("dashboard-heading-actions");

  const viewNuevoBien = makeEl("view-nuevo-bien", { dataset: { view: "Nuevo bien" }, hidden: false });
  const viewUbicaciones = makeEl("view-ubicaciones", { dataset: { view: "Ubicaciones" }, hidden: true });
  const viewNuevaUbicacion = makeEl("view-nueva-ubicacion", { dataset: { view: "Nueva ubicación" }, hidden: true });
  const viewGeneric = makeEl("view-generic", { dataset: { view: "placeholder" }, hidden: true });

  const assetCode = makeEl("asset-code", { value: "BIE-900" });
  const assetName = makeEl("asset-name", { value: "Motobomba Rosenbauer" });
  const assetLocation = makeEl("asset-location", {
    value: "",
    options: [
      { value: "", textContent: "Sin asignación fija (Depósito)" },
      { value: "__NEW__", textContent: "+ Nueva ubicación…" },
    ],
  });
  const btnQuickNuevaUbicacion = makeEl("btn-quick-nueva-ubicacion");

  const locName = makeEl("location-name", { value: "" });
  const locType = makeEl("location-type", { value: "FISICA" });
  const locContainerGroup = makeEl("group-location-container-asset", { hidden: true, display: "none" });
  const locContainerSelect = makeEl("location-container-asset", { value: "" });
  const locDesc = makeEl("location-description", { value: "Galpón trasero" });
  const btnSubmitUbicacion = makeEl("btn-submit-ubicacion");
  const btnCancelUbicacion = makeEl("btn-cancelar-crear-ubicacion", { dataset: { viewTarget: "Ubicaciones" } });
  const btnCancelUbicacionFooter = makeEl("btn-cancelar-ubicacion-footer", { dataset: { viewTarget: "Ubicaciones" } });

  const formCrearUbicacion = makeEl("form-crear-ubicacion", {
    onReset: () => {
      locName.value = "";
      locDesc.value = "";
    },
  });

  const genericSearchForm = makeEl("global-search-form");
  const mobileMenuBtn = makeEl("mobile-menu-btn");
  const profileBtn = makeEl("profile-btn");
  const logoutBtn = makeEl("logout-btn");

  const mockDoc = {
    documentElement: { dataset: { theme: "dark" } },
    createElement: (tag) => ({ tagName: tag.toUpperCase(), value: "", textContent: "" }),
    querySelector: (sel) => {
      if (sel.startsWith("#")) return elements.get(sel.slice(1)) || null;
      if (sel === ".global-search") return genericSearchForm;
      if (sel === ".mobile-menu") return mobileMenuBtn;
      if (sel === ".profile-button") return profileBtn;
      if (sel === ".logout-button") return logoutBtn;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel === ".view-content") return [viewNuevoBien, viewUbicaciones, viewNuevaUbicacion, viewGeneric];
      return [];
    },
    addEventListener: (evt, cb) => {
      if (!listeners.has(evt)) listeners.set(evt, []);
      listeners.get(evt).push(cb);
    },
  };

  let createdLocations = [];
  const mockFetch = async (url, opts = {}) => {
    if (url === "/inventory/locations" && opts.method === "POST") {
      const body = JSON.parse(opts.body);
      const created = { id: 42, name: body.name, location_type: body.location_type, description: body.description, active: true };
      createdLocations = [created];
      return { ok: true, json: async () => created };
    }
    if (url === "/health") return { ok: true, json: async () => ({ status: "ok" }) };
    if (url === "/inventory/categories") return { ok: true, json: async () => [{ id: 1, name: "Bombas" }] };
    if (url === "/inventory/assets/") return { ok: true, json: async () => [] };
    if (url === "/inventory/locations") return { ok: true, json: async () => createdLocations };
    if (url === "/inventory/movements") return { ok: true, json: async () => [] };
    return { ok: true, json: async () => ({}) };
  };

  const mockWindow = {
    location: { search: "", assign: () => {} },
    history: { replaceState: () => {} },
    setTimeout: () => 1,
    clearTimeout: () => {},
    DashboardData: { periods: { "90": { label: "90 días", multiplier: 1 } }, movements: [], statuses: [] },
    DashboardRenderer: { render: () => {}, renderMovements: () => {}, setRealData: () => {} },
    DashboardProfile: { mount: () => Promise.resolve({ role: "ADMINISTRADOR" }) },
  };

  const fn = new Function("window", "document", "fetch", "AbortController", "URLSearchParams", appJs);
  fn(mockWindow, mockDoc, mockFetch, class { abort() {} }, URLSearchParams);

  // 1. Simulate clicking '+ Nueva ubicación' quick access from 'Nuevo bien'
  const docClickHandlers = listeners.get("click") || [];
  for (const handler of docClickHandlers) {
    handler({
      preventDefault: () => {},
      target: {
        closest: (sel) => (sel === "#btn-quick-nueva-ubicacion" ? btnQuickNuevaUbicacion : null),
      },
    });
  }

  assert.equal(viewNuevaUbicacion.hidden, false, "Nueva ubicación view should open");
  assert.equal(viewNuevoBien.hidden, true, "Nuevo bien view should hide while creating location");
  assert.equal(btnCancelUbicacion.dataset.viewTarget, "Nuevo bien", "Return target should point back to Nuevo bien");

  // 2. Submitting < 3 chars should fail validation and stay on Nueva ubicación
  locName.value = "AB";
  await formCrearUbicacion.trigger("submit");
  assert.match(elements.get("toast").textContent, /mínimo 3 caracteres/);
  assert.equal(viewNuevaUbicacion.hidden, false);

  // 3. Submitting valid location creates it, returns to 'Nuevo bien', preserves asset inputs, and selects new location
  locName.value = "Destacamento Oeste";
  await formCrearUbicacion.trigger("submit");

  assert.equal(viewNuevoBien.hidden, false, "Must return to Nuevo bien view");
  assert.equal(viewNuevaUbicacion.hidden, true, "Nueva ubicación view must hide after submit");
  assert.equal(assetCode.value, "BIE-900", "Asset code input must be preserved");
  assert.equal(assetName.value, "Motobomba Rosenbauer", "Asset name input must be preserved");
  assert.equal(assetLocation.value, "42", "Newly created location must be automatically selected in #asset-location");
});

test("Behavioral: 'Ver bienes' opens location detail, handles errors, navigates to asset detail, and returns to Ubicaciones", async () => {
  const appJs = fs.readFileSync(path.join(__dirname, "../js/app.js"), "utf-8");
  const renderJs = fs.readFileSync(path.join(__dirname, "../js/render.js"), "utf-8");

  const listeners = new Map();
  const elements = new Map();

  function makeEl(id, extra = {}) {
    const elListeners = new Map();
    const classSet = new Set(extra.classes || []);
    const attrs = new Map();
    const el = {
      id,
      value: extra.value || "",
      innerHTML: extra.innerHTML || "",
      textContent: extra.textContent || "",
      hidden: extra.hidden ?? false,
      disabled: false,
      required: false,
      style: { display: extra.display || "", borderColor: "", background: "", color: "" },
      dataset: extra.dataset || {},
      options: extra.options || [],
      classList: {
        add: (c) => classSet.add(c),
        remove: (c) => classSet.delete(c),
        toggle: (c, force) => (force ? classSet.add(c) : classSet.delete(c)),
        contains: (c) => classSet.has(c),
      },
      setAttribute: (k, v) => attrs.set(k, String(v)),
      removeAttribute: (k) => attrs.delete(k),
      getAttribute: (k) => attrs.get(k) || null,
      addEventListener: (evt, cb) => {
        if (!elListeners.has(evt)) elListeners.set(evt, []);
        elListeners.get(evt).push(cb);
      },
      trigger: async (evt, eventObj = {}) => {
        const cbs = elListeners.get(evt) || [];
        for (const cb of cbs) {
          await cb({ preventDefault: () => {}, target: el, ...eventObj });
        }
      },
      focus: () => {},
      reset: () => {},
      closest: (sel) => (extra.closest ? extra.closest(sel) : null),
      matches: (sel) => sel.includes(`#${id}`),
      querySelector: (sel) => (sel.startsWith("#") ? elements.get(sel.slice(1)) || null : null),
      querySelectorAll: () => [],
    };
    elements.set(id, el);
    return el;
  }

  // Baseline DOM elements
  makeEl("date-range", { value: "90" });
  makeEl("country-search");
  makeEl("global-search");
  makeEl("mobile-nav");
  makeEl("toast");
  makeEl("api-status");
  makeEl("brightness-toggle");
  makeEl("profile-menu");
  makeEl("export-button");
  makeEl("google-link-button");
  makeEl("page-title");
  makeEl("page-subtitle");
  makeEl("dashboard-heading-actions");
  makeEl("kpi-grid");
  makeEl("chart-summary");
  makeEl("bar-chart");
  makeEl("channel-totals");
  makeEl("channel-list");
  makeEl("signal-strip");
  makeEl("country-table-body");
  makeEl("country-table-pagination");
  makeEl("assets-pagination-info");
  makeEl("btn-prev-assets");
  makeEl("btn-next-assets");
  makeEl("ubicaciones-table-body");
  makeEl("ubicaciones-count-all");
  makeEl("ubicaciones-count-fisica");
  makeEl("ubicaciones-count-vehiculo");

  // Location detail elements
  makeEl("ubicacion-detalle-kicker");
  makeEl("ubicacion-detalle-titulo");
  makeEl("ubicacion-detalle-tipo");
  makeEl("ubicacion-detalle-count");
  makeEl("ubicacion-detalle-descripcion");
  makeEl("ubicacion-bienes-search-input");
  makeEl("ubicacion-bienes-feedback", { hidden: true });
  makeEl("ubicacion-bienes-table-body");
  const btnVolverUbicaciones = makeEl("btn-volver-ubicaciones", { dataset: { viewTarget: "Ubicaciones" } });

  // Asset detail elements
  makeEl("bien-detalle-kicker");
  makeEl("bien-detalle-titulo");
  makeEl("bien-detalle-id");
  makeEl("bien-detalle-codigo");
  makeEl("bien-detalle-nombre");
  makeEl("bien-detalle-categoria");
  makeEl("bien-detalle-ubicacion");
  makeEl("bien-detalle-estado");
  makeEl("bien-detalle-feedback", { hidden: true });
  makeEl("btn-mover-desde-detalle");
  makeEl("bien-detalle-movimientos-tbody");
  const btnVolverDetalleBien = makeEl("btn-volver-detalle-bien", { dataset: { viewTarget: "Bienes" } });

  const viewUbicaciones = makeEl("view-ubicaciones", { dataset: { view: "Ubicaciones" }, hidden: false });
  const viewUbicacionBienes = makeEl("view-ubicacion-bienes", { dataset: { view: "Detalle de ubicación" }, hidden: true });
  const viewDetalleBien = makeEl("view-detalle-bien", { dataset: { view: "Detalle de bien" }, hidden: true });
  const viewGeneric = makeEl("view-generic", { dataset: { view: "placeholder" }, hidden: true });

  const genericSearchForm = makeEl("global-search-form");
  const mobileMenuBtn = makeEl("mobile-menu-btn");
  const profileBtn = makeEl("profile-btn");
  const logoutBtn = makeEl("logout-btn");

  const mockDoc = {
    documentElement: { dataset: { theme: "dark" } },
    createElement: (tag) => ({ tagName: tag.toUpperCase(), value: "", textContent: "" }),
    querySelector: (sel) => {
      if (sel.startsWith("#")) return elements.get(sel.slice(1)) || null;
      if (sel === ".global-search") return genericSearchForm;
      if (sel === ".mobile-menu") return mobileMenuBtn;
      if (sel === ".profile-button") return profileBtn;
      if (sel === ".logout-button") return logoutBtn;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel === ".view-content") return [viewUbicaciones, viewUbicacionBienes, viewDetalleBien, viewGeneric];
      return [];
    },
    addEventListener: (evt, cb) => {
      if (!listeners.has(evt)) listeners.set(evt, []);
      listeners.get(evt).push(cb);
    },
  };

  let fetchMode = "ok";
  const mockFetch = async (url) => {
    if (fetchMode === "forbidden" && url.startsWith("/inventory/locations/")) {
      return { status: 403, ok: false, json: async () => ({ detail: "Forbidden" }) };
    }
    if (fetchMode === "network_error" && url.startsWith("/inventory/locations/")) {
      throw new Error("Network failure");
    }
    if (url === "/inventory/locations/7") {
      return {
        status: 200,
        ok: true,
        json: async () => ({ id: 7, name: "Móvil R-04", location_type: "VEHICULO", description: "Unidad de rescate", active: true }),
      };
    }
    if (url === "/inventory/assets/") {
      return {
        status: 200,
        ok: true,
        json: async () => [
          { id: 201, internal_code: "RES-001", name: "Separador Hidráulico", category_id: 3, location_id: 7 },
          { id: 202, internal_code: "RES-002", name: "Tabla Espinal", category_id: 3, location_id: 1 },
        ],
      };
    }
    if (url === "/inventory/categories") {
      return { status: 200, ok: true, json: async () => [{ id: 3, name: "Rescate" }] };
    }
    if (url === "/inventory/assets/201") {
      return {
        status: 200,
        ok: true,
        json: async () => ({ id: 201, internal_code: "RES-001", name: "Separador Hidráulico", category_id: 3, location_id: 7 }),
      };
    }
    if (url === "/inventory/assets/201/transfers") {
      return {
        status: 200,
        ok: true,
        json: async () => [
          { id: 90, asset_id: 201, movement_type: "TRASLADO", origin_location_id: 1, destination_location_id: 7, occurred_at: "2026-10-25T12:00:00Z", reason: "Asignación a rescate" },
        ],
      };
    }
    if (url === "/health") return { status: 200, ok: true, json: async () => ({ status: "ok" }) };
    if (url === "/inventory/locations") {
      return {
        status: 200,
        ok: true,
        json: async () => [{ id: 7, name: "Móvil R-04", location_type: "VEHICULO", description: "Unidad de rescate", active: true }],
      };
    }
    return { status: 200, ok: true, json: async () => [] };
  };

  const mockWindow = {
    location: { search: "", assign: () => {} },
    history: { replaceState: () => {} },
    setTimeout: () => 1,
    clearTimeout: () => {},
    Intl,
    DashboardData: { periods: { "90": { label: "90 días", multiplier: 1 } }, kpis: [], categories: [], movements: [], statuses: [] },
    DashboardProfile: { mount: () => Promise.resolve({ role: "ADMINISTRADOR" }) },
  };

  new Function("window", "document", renderJs)(mockWindow, mockDoc);
  new Function("window", "document", "fetch", "AbortController", "URLSearchParams", appJs)(
    mockWindow,
    mockDoc,
    mockFetch,
    class { abort() {} },
    URLSearchParams
  );

  const docClickHandlers = listeners.get("click") || [];
  async function fireClick(matchSelector, targetObj) {
    for (const handler of docClickHandlers) {
      await handler({
        preventDefault: () => {},
        target: {
          closest: (sel) => (sel.includes(matchSelector) ? targetObj : null),
        },
      });
    }
  }

  // 1 & 2 & 3. Click 'Ver bienes' on location 7 -> opens Detalle de ubicación, loads only RES-001 (not RES-002)
  await fireClick("btn-ver-bienes-ubicacion", { dataset: { locId: "7" } });
  await new Promise(r => setTimeout(r, 20));

  assert.equal(viewUbicacionBienes.hidden, false, "Detalle de ubicación view must be visible");
  assert.equal(viewUbicaciones.hidden, true, "Ubicaciones list view must hide");
  assert.equal(elements.get("ubicacion-detalle-titulo").textContent, "Móvil R-04");
  assert.equal(elements.get("ubicacion-detalle-count").textContent, "1 bien asignado");
  assert.match(elements.get("ubicacion-bienes-table-body").innerHTML, /RES-001/);
  assert.match(elements.get("ubicacion-bienes-table-body").innerHTML, /Separador Hidráulico/);
  assert.doesNotMatch(elements.get("ubicacion-bienes-table-body").innerHTML, /RES-002/);

  // 8. Click 'Detalles' on asset 201 inside location 7 -> opens Detalle de bien and sets return target to Detalle de ubicación
  await fireClick("btn-ver-detalle-bien", {
    dataset: { assetId: "201" },
    closest: (sel) => (sel === "#view-ubicacion-bienes" ? viewUbicacionBienes : null),
  });
  await new Promise(r => setTimeout(r, 20));

  assert.equal(viewDetalleBien.hidden, false, "Detalle de bien view must open");
  assert.equal(viewUbicacionBienes.hidden, true);
  assert.equal(elements.get("bien-detalle-titulo").textContent, "Separador Hidráulico");
  assert.equal(elements.get("bien-detalle-codigo").textContent, "RES-001");
  assert.equal(btnVolverDetalleBien.dataset.viewTarget, "Detalle de ubicación");

  // Return from asset detail back to location detail
  await fireClick("#btn-volver-detalle-bien", btnVolverDetalleBien);
  assert.equal(viewUbicacionBienes.hidden, false, "Must return to Detalle de ubicación");
  assert.equal(viewDetalleBien.hidden, true);

  // 7. Click 'Volver a Ubicaciones' -> returns to Ubicaciones
  await fireClick("#btn-volver-ubicaciones", btnVolverUbicaciones);
  assert.equal(viewUbicaciones.hidden, false, "Must return to Ubicaciones list view");
  assert.equal(viewUbicacionBienes.hidden, true);

  // 6. Error handling: 403 Forbidden displays clear permission error message
  fetchMode = "forbidden";
  await fireClick("btn-ver-bienes-ubicacion", { dataset: { locId: "7" } });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(elements.get("ubicacion-bienes-feedback").hidden, false);
  assert.match(elements.get("ubicacion-bienes-feedback").textContent, /No tenés permisos para consultar los bienes de esta ubicación/);

  // 6b. Error handling: Network error displays clear connection error message
  fetchMode = "network_error";
  await fireClick("btn-ver-bienes-ubicacion", { dataset: { locId: "7" } });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(elements.get("ubicacion-bienes-feedback").hidden, false);
  assert.match(elements.get("ubicacion-bienes-feedback").textContent, /Error de conexión al consultar los bienes de la ubicación/);
});

test("Behavioral: 'Ver bienes' on Categorías opens category detail, preserves contextual return from Detalle del bien, and handles errors", async () => {
  const appJs = fs.readFileSync(path.join(__dirname, "../js/app.js"), "utf-8");
  const renderJs = fs.readFileSync(path.join(__dirname, "../js/render.js"), "utf-8");

  const listeners = new Map();
  const elements = new Map();

  function makeEl(id, extra = {}) {
    const elListeners = new Map();
    const classSet = new Set(extra.classes || []);
    const attrs = new Map();
    const el = {
      id,
      value: extra.value || "",
      innerHTML: extra.innerHTML || "",
      textContent: extra.textContent || "",
      hidden: extra.hidden ?? false,
      disabled: false,
      required: false,
      style: { display: extra.display || "", borderColor: "", background: "", color: "" },
      dataset: extra.dataset || {},
      options: extra.options || [],
      classList: {
        add: (c) => classSet.add(c),
        remove: (c) => classSet.delete(c),
        toggle: (c, force) => (force ? classSet.add(c) : classSet.delete(c)),
        contains: (c) => classSet.has(c),
      },
      setAttribute: (k, v) => attrs.set(k, String(v)),
      removeAttribute: (k) => attrs.delete(k),
      getAttribute: (k) => attrs.get(k) || null,
      addEventListener: (evt, cb) => {
        if (!elListeners.has(evt)) elListeners.set(evt, []);
        elListeners.get(evt).push(cb);
      },
      trigger: async (evt, eventObj = {}) => {
        const cbs = elListeners.get(evt) || [];
        for (const cb of cbs) {
          await cb({ preventDefault: () => {}, target: el, ...eventObj });
        }
      },
      focus: () => {},
      reset: () => {},
      closest: (sel) => (extra.closest ? extra.closest(sel) : null),
      matches: (sel) => sel.includes(`#${id}`),
      querySelector: (sel) => (sel.startsWith("#") ? elements.get(sel.slice(1)) || null : null),
      querySelectorAll: () => [],
    };
    elements.set(id, el);
    return el;
  }

  // Baseline DOM elements
  makeEl("date-range", { value: "90" });
  makeEl("country-search");
  makeEl("global-search");
  makeEl("mobile-nav");
  makeEl("toast");
  makeEl("api-status");
  makeEl("brightness-toggle");
  makeEl("profile-menu");
  makeEl("export-button");
  makeEl("google-link-button");
  makeEl("page-title");
  makeEl("page-subtitle");
  makeEl("dashboard-heading-actions");
  makeEl("kpi-grid");
  makeEl("chart-summary");
  makeEl("bar-chart");
  makeEl("channel-totals");
  makeEl("channel-list");
  makeEl("signal-strip");
  makeEl("country-table-body");
  makeEl("country-table-pagination");
  makeEl("assets-pagination-info");
  makeEl("btn-prev-assets");
  makeEl("btn-next-assets");
  makeEl("categorias-table-body");
  makeEl("ubicaciones-table-body");

  // Category detail elements
  makeEl("categoria-detalle-kicker");
  makeEl("categoria-detalle-titulo");
  makeEl("categoria-detalle-estado");
  makeEl("categoria-detalle-count");
  makeEl("categoria-detalle-descripcion");
  makeEl("categoria-bienes-search-input");
  makeEl("categoria-bienes-feedback", { hidden: true });
  makeEl("categoria-bienes-table-body");
  const btnVolverCategorias = makeEl("btn-volver-categorias", { dataset: { viewTarget: "Categorías" } });

  // Location detail elements (to verify coexistence with Ubicaciones flow)
  makeEl("ubicacion-detalle-kicker");
  makeEl("ubicacion-detalle-titulo");
  makeEl("ubicacion-detalle-tipo");
  makeEl("ubicacion-detalle-count");
  makeEl("ubicacion-detalle-descripcion");
  makeEl("ubicacion-bienes-search-input");
  makeEl("ubicacion-bienes-feedback", { hidden: true });
  makeEl("ubicacion-bienes-table-body");

  // Asset detail elements
  makeEl("bien-detalle-kicker");
  makeEl("bien-detalle-titulo");
  makeEl("bien-detalle-id");
  makeEl("bien-detalle-codigo");
  makeEl("bien-detalle-nombre");
  makeEl("bien-detalle-categoria");
  makeEl("bien-detalle-ubicacion");
  makeEl("bien-detalle-estado");
  makeEl("bien-detalle-feedback", { hidden: true });
  makeEl("btn-mover-desde-detalle");
  makeEl("bien-detalle-movimientos-tbody");
  const btnVolverDetalleBien = makeEl("btn-volver-detalle-bien", { dataset: { viewTarget: "Bienes" } });

  const viewCategorias = makeEl("view-categorias", { dataset: { view: "Categorías" }, hidden: false });
  const viewCategoriaBienes = makeEl("view-categoria-bienes", { dataset: { view: "Detalle de categoría" }, hidden: true });
  const viewUbicacionBienes = makeEl("view-ubicacion-bienes", { dataset: { view: "Detalle de ubicación" }, hidden: true });
  const viewDetalleBien = makeEl("view-detalle-bien", { dataset: { view: "Detalle de bien" }, hidden: true });
  const viewGeneric = makeEl("view-generic", { dataset: { view: "placeholder" }, hidden: true });

  const genericSearchForm = makeEl("global-search-form");
  const mobileMenuBtn = makeEl("mobile-menu-btn");
  const profileBtn = makeEl("profile-btn");
  const logoutBtn = makeEl("logout-btn");

  const mockDoc = {
    documentElement: { dataset: { theme: "dark" } },
    createElement: (tag) => ({ tagName: tag.toUpperCase(), value: "", textContent: "" }),
    querySelector: (sel) => {
      if (sel.startsWith("#")) return elements.get(sel.slice(1)) || null;
      if (sel === ".global-search") return genericSearchForm;
      if (sel === ".mobile-menu") return mobileMenuBtn;
      if (sel === ".profile-button") return profileBtn;
      if (sel === ".logout-button") return logoutBtn;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel === ".view-content") return [viewCategorias, viewCategoriaBienes, viewUbicacionBienes, viewDetalleBien, viewGeneric];
      return [];
    },
    addEventListener: (evt, cb) => {
      if (!listeners.has(evt)) listeners.set(evt, []);
      listeners.get(evt).push(cb);
    },
  };

  let fetchMode = "ok";
  const mockFetch = async (url) => {
    if (fetchMode === "unauthorized" && url === "/inventory/categories") {
      return { status: 401, ok: false, json: async () => ({ detail: "Unauthorized" }) };
    }
    if (fetchMode === "forbidden" && url === "/inventory/categories") {
      return { status: 403, ok: false, json: async () => ({ detail: "Forbidden" }) };
    }
    if (fetchMode === "network_error" && url === "/inventory/categories") {
      throw new Error("Network failure");
    }
    if (url === "/inventory/categories") {
      return {
        status: 200,
        ok: true,
        json: async () => [
          { id: 3, name: "Rescate" },
          { id: 4, name: "Comunicaciones" },
        ],
      };
    }
    if (url === "/inventory/assets/") {
      return {
        status: 200,
        ok: true,
        json: async () => [
          { id: 201, internal_code: "RES-001", name: "Separador Hidráulico", category_id: 3, location_id: 7 },
          { id: 202, internal_code: "COM-010", name: "Handy Motorola P25", category_id: 4, location_id: 1 },
        ],
      };
    }
    if (url === "/inventory/locations") {
      return {
        status: 200,
        ok: true,
        json: async () => [
          { id: 1, name: "Cuartel Central", location_type: "FISICA", active: true },
          { id: 7, name: "Móvil R-04", location_type: "VEHICULO", active: true },
        ],
      };
    }
    if (url === "/inventory/assets/201") {
      return {
        status: 200,
        ok: true,
        json: async () => ({ id: 201, internal_code: "RES-001", name: "Separador Hidráulico", category_id: 3, location_id: 7 }),
      };
    }
    if (url === "/inventory/assets/201/transfers") {
      return {
        status: 200,
        ok: true,
        json: async () => [],
      };
    }
    return { status: 200, ok: true, json: async () => [] };
  };

  const mockWindow = {
    location: { search: "", assign: () => {} },
    history: { replaceState: () => {} },
    setTimeout: () => 1,
    clearTimeout: () => {},
    Intl,
    DashboardData: { periods: { "90": { label: "90 días", multiplier: 1 } }, kpis: [], categories: [], movements: [], statuses: [] },
    DashboardProfile: { mount: () => Promise.resolve({ role: "ADMINISTRADOR" }) },
  };

  new Function("window", "document", renderJs)(mockWindow, mockDoc);
  new Function("window", "document", "fetch", "AbortController", "URLSearchParams", appJs)(
    mockWindow,
    mockDoc,
    mockFetch,
    class { abort() {} },
    URLSearchParams
  );

  const docClickHandlers = listeners.get("click") || [];
  async function fireClick(matchSelector, targetObj) {
    for (const handler of docClickHandlers) {
      await handler({
        preventDefault: () => {},
        target: {
          closest: (sel) => (sel.includes(matchSelector) ? targetObj : null),
        },
      });
    }
  }

  // 1, 2 & 3. Click 'Ver bienes' on category 3 ("Rescate") -> opens Detalle de categoría, shows RES-001 and excludes COM-010
  await fireClick("btn-ver-bienes-categoria", { dataset: { catId: "3" } });
  await new Promise(r => setTimeout(r, 20));

  assert.equal(viewCategoriaBienes.hidden, false, "Detalle de categoría view must be visible");
  assert.equal(viewCategorias.hidden, true, "Categorías list view must hide");
  assert.equal(elements.get("categoria-detalle-titulo").textContent, "Rescate");
  assert.equal(elements.get("categoria-detalle-count").textContent, "1 bien asociado");
  assert.match(elements.get("categoria-bienes-table-body").innerHTML, /RES-001/);
  assert.match(elements.get("categoria-bienes-table-body").innerHTML, /Separador Hidráulico/);
  assert.match(elements.get("categoria-bienes-table-body").innerHTML, /Móvil R-04/);
  assert.doesNotMatch(elements.get("categoria-bienes-table-body").innerHTML, /COM-010/);

  // 7. Click 'Detalles' on asset 201 inside category 3 -> opens Detalle de bien and sets return target to Detalle de categoría
  await fireClick("btn-ver-detalle-bien", {
    dataset: { assetId: "201" },
    closest: (sel) => (sel === "#view-categoria-bienes" ? viewCategoriaBienes : null),
  });
  await new Promise(r => setTimeout(r, 20));

  assert.equal(viewDetalleBien.hidden, false, "Detalle de bien view must open");
  assert.equal(viewCategoriaBienes.hidden, true);
  assert.equal(elements.get("bien-detalle-titulo").textContent, "Separador Hidráulico");
  assert.equal(btnVolverDetalleBien.dataset.viewTarget, "Detalle de categoría");
  assert.match(btnVolverDetalleBien.innerHTML, /Volver a la categoría/);

  // Return from asset detail back to category detail (NOT Ubicaciones or Bienes)
  await fireClick("#btn-volver-detalle-bien", btnVolverDetalleBien);
  assert.equal(viewCategoriaBienes.hidden, false, "Must return to Detalle de categoría");
  assert.equal(viewUbicacionBienes.hidden, true, "Must NOT open Detalle de ubicación");
  assert.equal(viewDetalleBien.hidden, true);

  // 6. Click 'Volver a Categorías' -> returns to Categorías
  await fireClick("#btn-volver-categorias", btnVolverCategorias);
  assert.equal(viewCategorias.hidden, false, "Must return to Categorías list view");
  assert.equal(viewCategoriaBienes.hidden, true);

  // 9a. Error handling: 404 non-existent category ID (e.g. catId 999)
  await fireClick("btn-ver-bienes-categoria", { dataset: { catId: "999" } });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(elements.get("categoria-bienes-feedback").hidden, false);
  assert.match(elements.get("categoria-bienes-feedback").textContent, /La categoría seleccionada no existe o no fue encontrada/);

  // 9b. Error handling: 401 Unauthorized
  fetchMode = "unauthorized";
  await fireClick("btn-ver-bienes-categoria", { dataset: { catId: "3" } });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(elements.get("categoria-bienes-feedback").hidden, false);
  assert.match(elements.get("categoria-bienes-feedback").textContent, /Sesión expirada o no autenticada/);

  // 9c. Error handling: 403 Forbidden
  fetchMode = "forbidden";
  await fireClick("btn-ver-bienes-categoria", { dataset: { catId: "3" } });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(elements.get("categoria-bienes-feedback").hidden, false);
  assert.match(elements.get("categoria-bienes-feedback").textContent, /No tenés permisos para consultar los bienes de esta categoría/);

  // 9d. Error handling: Network failure
  fetchMode = "network_error";
  await fireClick("btn-ver-bienes-categoria", { dataset: { catId: "3" } });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(elements.get("categoria-bienes-feedback").hidden, false);
  assert.match(elements.get("categoria-bienes-feedback").textContent, /Error de conexión al consultar los bienes de la categoría/);
});

test("Behavioral: Vehículos view supports 'Ver dotación', 'Ficha del móvil', contextual return to Vehículos, and error states without breaking Ubicaciones", async () => {
  const appJs = fs.readFileSync(path.join(__dirname, "../js/app.js"), "utf-8");
  const renderJs = fs.readFileSync(path.join(__dirname, "../js/render.js"), "utf-8");

  const listeners = new Map();
  const elements = new Map();

  function makeEl(id, extra = {}) {
    const elListeners = new Map();
    const classSet = new Set(extra.classes || []);
    const attrs = new Map();
    const el = {
      id,
      value: extra.value || "",
      innerHTML: extra.innerHTML || "",
      textContent: extra.textContent || "",
      hidden: extra.hidden ?? false,
      disabled: false,
      required: false,
      style: { display: extra.display || "", borderColor: "", background: "", color: "" },
      dataset: extra.dataset || {},
      options: extra.options || [],
      classList: {
        add: (c) => classSet.add(c),
        remove: (c) => classSet.delete(c),
        toggle: (c, force) => (force ? classSet.add(c) : classSet.delete(c)),
        contains: (c) => classSet.has(c),
      },
      setAttribute: (k, v) => attrs.set(k, String(v)),
      removeAttribute: (k) => attrs.delete(k),
      getAttribute: (k) => attrs.get(k) || null,
      addEventListener: (evt, cb) => {
        if (!elListeners.has(evt)) elListeners.set(evt, []);
        elListeners.get(evt).push(cb);
      },
      trigger: async (evt, eventObj = {}) => {
        const cbs = elListeners.get(evt) || [];
        for (const cb of cbs) {
          await cb({ preventDefault: () => {}, target: el, ...eventObj });
        }
      },
      focus: () => {},
      reset: () => {},
      closest: (sel) => (extra.closest ? extra.closest(sel) : null),
      matches: (sel) => sel.includes(`#${id}`),
      querySelector: (sel) => (sel.startsWith("#") ? elements.get(sel.slice(1)) || null : null),
      querySelectorAll: () => [],
    };
    elements.set(id, el);
    return el;
  }

  // Baseline DOM elements
  makeEl("date-range", { value: "90" });
  makeEl("country-search");
  makeEl("global-search");
  makeEl("mobile-nav");
  makeEl("toast");
  makeEl("api-status");
  makeEl("brightness-toggle");
  makeEl("profile-menu");
  makeEl("export-button");
  makeEl("google-link-button");
  makeEl("page-title");
  makeEl("page-subtitle");
  makeEl("dashboard-heading-actions");
  makeEl("kpi-grid");
  makeEl("chart-summary");
  makeEl("bar-chart");
  makeEl("channel-totals");
  makeEl("channel-list");
  makeEl("signal-strip");
  makeEl("country-table-body");
  makeEl("country-table-pagination");
  makeEl("assets-pagination-info");
  makeEl("btn-prev-assets");
  makeEl("btn-next-assets");
  makeEl("ubicaciones-table-body");

  // Vehículos elements
  makeEl("vehiculos-count-total");
  makeEl("vehiculos-count-equipamiento");
  makeEl("vehiculos-search-input");
  makeEl("vehiculos-feedback", { hidden: true });
  makeEl("vehiculos-table-body");

  // Location detail elements
  makeEl("ubicacion-detalle-kicker");
  makeEl("ubicacion-detalle-titulo");
  makeEl("ubicacion-detalle-tipo");
  makeEl("ubicacion-detalle-count");
  makeEl("ubicacion-detalle-descripcion");
  makeEl("ubicacion-bienes-search-input");
  makeEl("ubicacion-bienes-feedback", { hidden: true });
  makeEl("ubicacion-bienes-table-body");
  const btnVolverUbicaciones = makeEl("btn-volver-ubicaciones", { dataset: { viewTarget: "Ubicaciones" } });

  // Asset detail elements
  makeEl("bien-detalle-kicker");
  makeEl("bien-detalle-titulo");
  makeEl("bien-detalle-id");
  makeEl("bien-detalle-codigo");
  makeEl("bien-detalle-nombre");
  makeEl("bien-detalle-categoria");
  makeEl("bien-detalle-ubicacion");
  makeEl("bien-detalle-estado");
  makeEl("bien-detalle-feedback", { hidden: true });
  makeEl("btn-mover-desde-detalle");
  makeEl("bien-detalle-movimientos-tbody");
  const btnVolverDetalleBien = makeEl("btn-volver-detalle-bien", { dataset: { viewTarget: "Bienes" } });

  const navBtnVehiculos = makeEl("nav-btn-vehiculos", {
    dataset: { view: "Vehículos" },
    closest: (sel) => (sel === "nav" ? {} : null),
  });
  const viewVehiculos = makeEl("view-vehiculos", { dataset: { view: "Vehículos" }, hidden: true });
  const viewUbicaciones = makeEl("view-ubicaciones", { dataset: { view: "Ubicaciones" }, hidden: false });
  const viewUbicacionBienes = makeEl("view-ubicacion-bienes", { dataset: { view: "Detalle de ubicación" }, hidden: true });
  const viewDetalleBien = makeEl("view-detalle-bien", { dataset: { view: "Detalle de bien" }, hidden: true });
  const viewGeneric = makeEl("view-generic", { dataset: { view: "placeholder" }, hidden: true });

  const genericSearchForm = makeEl("global-search-form");
  const mobileMenuBtn = makeEl("mobile-menu-btn");
  const profileBtn = makeEl("profile-btn");
  const logoutBtn = makeEl("logout-btn");

  const mockDoc = {
    documentElement: { dataset: { theme: "dark" } },
    createElement: (tag) => ({ tagName: tag.toUpperCase(), value: "", textContent: "" }),
    querySelector: (sel) => {
      if (sel.startsWith("#")) return elements.get(sel.slice(1)) || null;
      if (sel === ".global-search") return genericSearchForm;
      if (sel === ".mobile-menu") return mobileMenuBtn;
      if (sel === ".profile-button") return profileBtn;
      if (sel === ".logout-button") return logoutBtn;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel === ".view-content") return [viewVehiculos, viewUbicaciones, viewUbicacionBienes, viewDetalleBien, viewGeneric];
      if (sel === "[data-view]") return [navBtnVehiculos];
      return [];
    },
    addEventListener: (evt, cb) => {
      if (!listeners.has(evt)) listeners.set(evt, []);
      listeners.get(evt).push(cb);
    },
  };

  let fetchMode = "ok";
  const mockFetch = async (url) => {
    if (fetchMode === "forbidden" && url === "/inventory/locations") {
      return { status: 403, ok: false, json: async () => ({ detail: "Forbidden" }) };
    }
    if (fetchMode === "network_error" && url === "/inventory/locations") {
      throw new Error("Network failure");
    }
    if (url === "/inventory/locations") {
      return {
        status: 200,
        ok: true,
        json: async () => [
          { id: 1, name: "Cuartel Central", location_type: "FISICA", active: true },
          { id: 7, name: "Móvil R-04", location_type: "VEHICULO", container_asset_id: 500, description: "Unidad de rescate", active: true },
        ],
      };
    }
    if (url === "/inventory/locations/7") {
      return {
        status: 200,
        ok: true,
        json: async () => ({ id: 7, name: "Móvil R-04", location_type: "VEHICULO", container_asset_id: 500, description: "Unidad de rescate", active: true }),
      };
    }
    if (url === "/inventory/assets/") {
      return {
        status: 200,
        ok: true,
        json: async () => [
          { id: 500, internal_code: "MOV-R04", name: "Camioneta Ford Ranger Rescate", category_id: 2, location_id: 1 },
          { id: 505, internal_code: "CAM-005", name: "Camioneta Amarok Apoyo", category_id: 2, location_id: 1 },
          { id: 201, internal_code: "RES-001", name: "Separador Hidráulico", category_id: 3, location_id: 7 },
        ],
      };
    }
    if (url === "/inventory/categories") {
      return {
        status: 200,
        ok: true,
        json: async () => [
          { id: 2, name: "Vehículo" },
          { id: 3, name: "Rescate" },
        ],
      };
    }
    if (url === "/inventory/assets/500") {
      return {
        status: 200,
        ok: true,
        json: async () => ({ id: 500, internal_code: "MOV-R04", name: "Camioneta Ford Ranger Rescate", category_id: 2, location_id: 1 }),
      };
    }
    if (url === "/inventory/assets/500/transfers") {
      return { status: 200, ok: true, json: async () => [] };
    }
    if (url === "/inventory/assets/505") {
      return {
        status: 200,
        ok: true,
        json: async () => ({ id: 505, internal_code: "CAM-005", name: "Camioneta Amarok Apoyo", category_id: 2, location_id: 1 }),
      };
    }
    if (url === "/inventory/assets/505/transfers") {
      return { status: 200, ok: true, json: async () => [] };
    }
    return { status: 200, ok: true, json: async () => [] };
  };

  const mockWindow = {
    location: { search: "", assign: () => {} },
    history: { replaceState: () => {} },
    setTimeout: () => 1,
    clearTimeout: () => {},
    Intl,
    DashboardData: { periods: { "90": { label: "90 días", multiplier: 1 } }, kpis: [], categories: [], movements: [], statuses: [] },
    DashboardProfile: { mount: () => Promise.resolve({ role: "ADMINISTRADOR" }) },
  };

  new Function("window", "document", renderJs)(mockWindow, mockDoc);
  new Function("window", "document", "fetch", "AbortController", "URLSearchParams", appJs)(
    mockWindow,
    mockDoc,
    mockFetch,
    class { abort() {} },
    URLSearchParams
  );

  const docClickHandlers = listeners.get("click") || [];
  async function fireClick(matchSelector, targetObj) {
    for (const handler of docClickHandlers) {
      await handler({
        preventDefault: () => {},
        target: {
          closest: (sel) => (sel.includes(matchSelector) ? targetObj : null),
        },
      });
    }
  }

  // 1. Navigate to Vehículos view
  await navBtnVehiculos.trigger("click");
  await new Promise(r => setTimeout(r, 20));
  assert.equal(viewVehiculos.hidden, false, "Vehículos view must be visible");
  assert.equal(viewGeneric.hidden, true, "Generic placeholder must remain hidden");
  assert.match(elements.get("vehiculos-table-body").innerHTML, /Móvil R-04/);
  assert.match(elements.get("vehiculos-table-body").innerHTML, /MOV-R04/);
  assert.match(elements.get("vehiculos-table-body").innerHTML, /Camioneta Ford Ranger Rescate/);
  assert.match(elements.get("vehiculos-table-body").innerHTML, /Cuartel Central/);

  // 2. Click 'Ver dotación' (.btn-ver-dotacion-vehiculo) -> opens Detalle de ubicación with return target = "Vehículos"
  await fireClick("btn-ver-dotacion-vehiculo", { dataset: { locId: "7" } });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(viewUbicacionBienes.hidden, false, "Detalle de ubicación must open for vehicle equipment");
  assert.equal(viewVehiculos.hidden, true);
  assert.equal(btnVolverUbicaciones.dataset.viewTarget, "Vehículos");
  assert.match(btnVolverUbicaciones.innerHTML, /Volver a Vehículos/);
  assert.match(elements.get("ubicacion-bienes-table-body").innerHTML, /Separador Hidráulico/);

  // Return from 'Ver dotación' back to 'Vehículos'
  await fireClick("#btn-volver-ubicaciones", btnVolverUbicaciones);
  await new Promise(r => setTimeout(r, 20));
  assert.equal(viewVehiculos.hidden, false, "Must return to Vehículos view");
  assert.equal(viewUbicaciones.hidden, true, "Must NOT return to Ubicaciones view");

  // 3. Click 'Ficha del móvil' (.btn-ver-ficha-vehiculo) -> opens Detalle de bien for container asset 500 with return target = "Vehículos"
  await fireClick("btn-ver-ficha-vehiculo", { dataset: { assetId: "500" } });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(viewDetalleBien.hidden, false, "Detalle de bien must open for container asset");
  assert.equal(viewVehiculos.hidden, true);
  assert.equal(elements.get("bien-detalle-titulo").textContent, "Camioneta Ford Ranger Rescate");
  assert.equal(btnVolverDetalleBien.dataset.viewTarget, "Vehículos");
  assert.match(btnVolverDetalleBien.innerHTML, /Volver a Vehículos/);

  // Return from 'Ficha del móvil' back to 'Vehículos'
  await fireClick("#btn-volver-detalle-bien", btnVolverDetalleBien);
  await new Promise(r => setTimeout(r, 20));
  assert.equal(viewVehiculos.hidden, false, "Must return to Vehículos view from container asset detail");
  assert.equal(viewDetalleBien.hidden, true);

  // 3b. Patrimonial camioneta without mobile location (505) is shown with user-oriented status and parking location, and opens its ficha returning to Vehículos
  assert.match(elements.get("vehiculos-table-body").innerHTML, /Camioneta Amarok Apoyo/);
  assert.doesNotMatch(elements.get("vehiculos-table-body").innerHTML, /Ubicación móvil no configurada/);
  assert.doesNotMatch(elements.get("vehiculos-table-body").innerHTML, /Sin ubicación móvil/);
  await fireClick("btn-ver-ficha-vehiculo", { dataset: { assetId: "505" } });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(viewDetalleBien.hidden, false, "Detalle de bien must open for patrimonial vehicle without mobile location");
  assert.equal(elements.get("bien-detalle-titulo").textContent, "Camioneta Amarok Apoyo");
  assert.equal(btnVolverDetalleBien.dataset.viewTarget, "Vehículos");
  await fireClick("#btn-volver-detalle-bien", btnVolverDetalleBien);
  await new Promise(r => setTimeout(r, 20));
  assert.equal(viewVehiculos.hidden, false, "Must return to Vehículos view after inspecting patrimonial vehicle");

  // 4. Regression check: opening 'Ver bienes' from Ubicaciones (.btn-ver-bienes-ubicacion) sets return target back to "Ubicaciones"
  await fireClick("btn-ver-bienes-ubicacion", {
    dataset: { locId: "7" },
    closest: () => null,
  });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(btnVolverUbicaciones.dataset.viewTarget, "Ubicaciones");
  await fireClick("#btn-volver-ubicaciones", btnVolverUbicaciones);
  assert.equal(viewUbicaciones.hidden, false, "Must return to Ubicaciones when opened from Ubicaciones");

  // 5. Error states in Vehículos view (403 Forbidden and Network error)
  fetchMode = "forbidden";
  await navBtnVehiculos.trigger("click");
  await new Promise(r => setTimeout(r, 20));
  assert.equal(elements.get("vehiculos-feedback").hidden, false);
  assert.match(elements.get("vehiculos-feedback").textContent, /No tenés permisos para consultar el parque automotor/);

  fetchMode = "network_error";
  await navBtnVehiculos.trigger("click");
  await new Promise(r => setTimeout(r, 20));
  assert.equal(elements.get("vehiculos-feedback").hidden, false);
  assert.match(elements.get("vehiculos-feedback").textContent, /Error de conexión al consultar el parque automotor/);
});

test("Behavioral: Registering or transferring an asset into an unconfigured vehicle is transparent, avoids premature POST /inventory/locations, sends destination_vehicle_asset_id, and enables Ver dotación", async () => {
  const appJs = fs.readFileSync(path.join(__dirname, "../js/app.js"), "utf-8");
  const renderJs = fs.readFileSync(path.join(__dirname, "../js/render.js"), "utf-8");

  const listeners = new Map();
  const elements = new Map();

  function makeEl(id, extra = {}) {
    const elListeners = new Map();
    const classSet = new Set(extra.classes || []);
    const attrs = new Map();
    const el = {
      id,
      value: extra.value || "",
      innerHTML: extra.innerHTML || "",
      textContent: extra.textContent || "",
      hidden: extra.hidden ?? false,
      disabled: false,
      required: false,
      style: { display: extra.display || "", borderColor: "", background: "", color: "" },
      dataset: extra.dataset || {},
      options: extra.options || [],
      appendChild: (opt) => {
        el.options.push(opt);
      },
      classList: {
        add: (c) => classSet.add(c),
        remove: (c) => classSet.delete(c),
        toggle: (c, force) => (force ? classSet.add(c) : classSet.delete(c)),
        contains: (c) => classSet.has(c),
      },
      setAttribute: (k, v) => attrs.set(k, String(v)),
      removeAttribute: (k) => attrs.delete(k),
      getAttribute: (k) => attrs.get(k) || null,
      addEventListener: (evt, cb) => {
        if (!elListeners.has(evt)) elListeners.set(evt, []);
        elListeners.get(evt).push(cb);
      },
      trigger: async (evt, eventObj = {}) => {
        const cbs = elListeners.get(evt) || [];
        for (const cb of cbs) {
          await cb({ preventDefault: () => {}, target: el, ...eventObj });
        }
      },
      focus: () => {},
      reset: () => {},
      closest: (sel) => (extra.closest ? extra.closest(sel) : null),
      matches: (sel) => sel.includes(`#${id}`),
      querySelector: (sel) => (sel.startsWith("#") ? elements.get(sel.slice(1)) || null : null),
      querySelectorAll: () => [],
    };
    elements.set(id, el);
    return el;
  }

  // Baseline DOM elements
  makeEl("date-range", { value: "90" });
  makeEl("country-search");
  makeEl("global-search");
  makeEl("mobile-nav");
  makeEl("toast");
  makeEl("api-status");
  makeEl("brightness-toggle");
  makeEl("profile-menu");
  makeEl("export-button");
  makeEl("google-link-button");
  makeEl("page-title");
  makeEl("page-subtitle");
  makeEl("dashboard-heading-actions");
  makeEl("kpi-grid");
  makeEl("chart-summary");
  makeEl("bar-chart");
  makeEl("channel-totals");
  makeEl("channel-list");
  makeEl("signal-strip");
  makeEl("country-table-body");
  makeEl("country-table-pagination");
  makeEl("assets-pagination-info");
  makeEl("btn-prev-assets");
  makeEl("btn-next-assets");
  makeEl("ubicaciones-table-body");
  makeEl("vehiculos-table-body");
  makeEl("vehiculos-feedback", { hidden: true });
  makeEl("vehiculos-search-input");
  makeEl("vehiculos-count-total");
  makeEl("vehiculos-count-equipped");
  makeEl("vehiculos-count-assets");

  // Nuevo bien form elements
  const assetCode = makeEl("asset-code", { value: "RAD-777" });
  const assetName = makeEl("asset-name", { value: "Handy VHF Base" });
  const assetCategory = makeEl("asset-category", { value: "3", options: [{ value: "" }] });
  const assetLocation = makeEl("asset-location", { value: "", options: [{ value: "" }] });
  const assetLocationNotice = makeEl("asset-location-vehicle-notice", { hidden: true });
  const assetQuantity = makeEl("asset-quantity", { value: "1" });
  const assetStatus = makeEl("asset-status", { value: "ACTIVO" });
  const assetObs = makeEl("asset-observations", { value: "" });
  makeEl("btn-submit-bien");
  const formCrearBien = makeEl("form-crear-bien");

  // Mover bien modal elements
  makeEl("modal-mover-bien", { hidden: true, display: "none" });
  makeEl("mover-asset-id", { value: "" });
  makeEl("mover-bien-nombre");
  makeEl("mover-bien-codigo");
  makeEl("mover-origen-display");
  const moverDestinoSelect = makeEl("mover-destino-select", { value: "", options: [{ value: "" }] });
  const moverDestinoNotice = makeEl("mover-destino-vehicle-notice", { hidden: true });
  makeEl("mover-nuevo-destino-nombre", { value: "" });
  const moverMotivo = makeEl("mover-motivo", { value: "" });
  makeEl("mover-observaciones", { value: "" });
  makeEl("btn-dest-mode-existing");
  makeEl("btn-dest-mode-new");
  makeEl("panel-select-destino", { hidden: false });
  makeEl("panel-new-destino", { hidden: true });
  makeEl("btn-cancel-new-destino");
  makeEl("btn-cerrar-modal-mover");
  makeEl("btn-cancelar-mover");
  makeEl("btn-confirmar-traslado");
  const formMoverBien = makeEl("form-mover-bien");

  const viewBienes = makeEl("view-bienes", { dataset: { view: "Bienes" }, hidden: false });
  const viewNuevoBien = makeEl("view-nuevo-bien", { dataset: { view: "Nuevo bien" }, hidden: true });
  const viewVehiculos = makeEl("view-vehiculos", { dataset: { view: "Vehículos" }, hidden: true });
  const viewGeneric = makeEl("view-generic", { dataset: { view: "placeholder" }, hidden: true });

  const genericSearchForm = makeEl("global-search-form");
  const mobileMenuBtn = makeEl("mobile-menu-btn");
  const profileBtn = makeEl("profile-btn");
  const logoutBtn = makeEl("logout-btn");

  const mockDoc = {
    documentElement: { dataset: { theme: "dark" } },
    createElement: (tag) => ({ tagName: tag.toUpperCase(), value: "", textContent: "" }),
    querySelector: (sel) => {
      if (sel.startsWith("#")) return elements.get(sel.slice(1)) || null;
      if (sel === ".global-search") return genericSearchForm;
      if (sel === ".mobile-menu") return mobileMenuBtn;
      if (sel === ".profile-button") return profileBtn;
      if (sel === ".logout-button") return logoutBtn;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel === ".view-content") return [viewBienes, viewNuevoBien, viewVehiculos, viewGeneric];
      return [];
    },
    addEventListener: (evt, cb) => {
      if (!listeners.has(evt)) listeners.set(evt, []);
      listeners.get(evt).push(cb);
    },
  };

  let locationsState = [
    { id: 1, name: "Playón delantero", location_type: "FISICA", container_asset_id: null, active: true },
  ];
  let assetsState = [
    { id: 505, internal_code: "HGJ-875", name: "Camioneta HGJ-875", category_id: 2, location_id: 1, status: "ACTIVO" },
    { id: 601, internal_code: "BOT-001", name: "Botiquín Trauma", category_id: 3, location_id: 1, status: "ACTIVO" },
  ];
  let postLocationsCalls = 0;
  let capturedCreatePayload = null;
  let capturedTransferPayload = null;

  const mockFetch = async (url, opts = {}) => {
    if (url === "/health") return { ok: true, status: 200, json: async () => ({ status: "ok" }) };
    if (url === "/inventory/locations" && opts.method === "POST") {
      postLocationsCalls += 1;
      return { ok: true, status: 201, json: async () => ({}) };
    }
    if (url === "/inventory/locations") {
      return { ok: true, status: 200, json: async () => locationsState };
    }
    if (url === "/inventory/categories") {
      return {
        ok: true,
        status: 200,
        json: async () => [
          { id: 2, name: "Vehículo" },
          { id: 3, name: "Comunicaciones" },
        ],
      };
    }
    if ((url === "/inventory/assets" || url === "/inventory/assets/") && opts.method === "POST") {
      capturedCreatePayload = JSON.parse(opts.body);
      // Backend atomically creates the mobile Location(id=99) for vehicle 505 and registers the asset in it
      if (capturedCreatePayload.destination_vehicle_asset_id === 505) {
        if (!locationsState.some((l) => l.container_asset_id === 505)) {
          locationsState.push({
            id: 99,
            name: "Camioneta HGJ-875",
            location_type: "VEHICULO",
            container_asset_id: 505,
            active: true,
          });
        }
        const createdAsset = {
          id: 777,
          internal_code: capturedCreatePayload.internal_code,
          name: capturedCreatePayload.name,
          category_id: capturedCreatePayload.category_id,
          location_id: 99,
          status: "ACTIVO",
        };
        assetsState.push(createdAsset);
        return { ok: true, status: 201, json: async () => createdAsset };
      }
    }
    if (url === "/inventory/assets/601/transfers" && opts.method === "POST") {
      capturedTransferPayload = JSON.parse(opts.body);
      return {
        ok: true,
        status: 201,
        json: async () => ({
          id: 1,
          asset_id: 601,
          origin_location_id: 1,
          destination_location_id: 99,
        }),
      };
    }
    if (url === "/inventory/assets/") {
      return { ok: true, status: 200, json: async () => assetsState };
    }
    if (url === "/inventory/movements") {
      return { ok: true, status: 200, json: async () => [] };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };

  const mockWindow = {
    location: { search: "", assign: () => {} },
    history: { replaceState: () => {} },
    setTimeout: () => 1,
    clearTimeout: () => {},
    Intl,
    DashboardData: { periods: { "90": { label: "90 días", multiplier: 1 } }, kpis: [], categories: [], movements: [], statuses: [] },
    DashboardProfile: { mount: () => Promise.resolve({ role: "ADMINISTRADOR" }) },
  };

  new Function("window", "document", renderJs)(mockWindow, mockDoc);
  new Function("window", "document", "fetch", "AbortController", "URLSearchParams", appJs)(
    mockWindow,
    mockDoc,
    mockFetch,
    class { abort() {} },
    URLSearchParams
  );

  await new Promise((r) => setTimeout(r, 25));

  // 1. Check that #asset-location contains Playón delantero and nested Camioneta HGJ-875 (value="veh:505")
  assert.match(assetLocation.innerHTML, /<option value="1"[^>]*>Playón delantero<\/option>/, "Physical location Playón delantero must be present");
  assert.match(assetLocation.innerHTML, /<option value="veh:505"[^>]*>  - Camioneta HGJ-875 \(HGJ-875\) — Playón delantero<\/option>/, "Unconfigured vehicle Camioneta HGJ-875 must be selectable as veh:505 nested under Playón delantero");
  const idxPlayon = assetLocation.innerHTML.indexOf('value="1"');
  const idxCamioneta = assetLocation.innerHTML.indexOf('value="veh:505"');
  assert.ok(idxPlayon !== -1 && idxCamioneta > idxPlayon, "Vehicle must be nested immediately after its physical parking location");

  // 2. Selecting veh:505 is completely transparent (no internal container notice) and does NOT call POST /inventory/locations
  const indexHtml = fs.readFileSync(path.join(__dirname, "../index.html"), "utf-8");
  assert.doesNotMatch(indexHtml, /Al guardar, se habilitará automáticamente este vehículo para contener bienes/);
  assetLocation.value = "veh:505";
  await assetLocation.trigger("change");
  assert.equal(postLocationsCalls, 0, "Selecting a vehicle must NOT create a location before saving");

  // 3. Also test Mover bien modal before saving: open modal for asset 601, select veh:505, and verify submit payload
  const docClickHandlers = listeners.get("click") || [];
  for (const handler of docClickHandlers) {
    await handler({
      preventDefault: () => {},
      target: {
        closest: (sel) =>
          sel.includes("btn-mover-bien")
            ? {
                dataset: {
                  assetId: "601",
                  assetCode: "BOT-001",
                  assetName: "Botiquín Trauma",
                  assetLocationId: "1",
                  assetLocation: "Playón delantero",
                },
              }
            : null,
      },
    });
  }
  assert.match(moverDestinoSelect.innerHTML, /value="veh:505"/);
  moverDestinoSelect.value = "veh:505";
  moverMotivo.value = "Asignación a móvil";
  await moverDestinoSelect.trigger("change");
  await formMoverBien.trigger("submit");
  await new Promise((r) => setTimeout(r, 20));
  assert.deepEqual(capturedTransferPayload, {
    destination_vehicle_asset_id: 505,
    reason: "Asignación a móvil",
    observations: null,
  });

  // 4. Submit Nuevo bien with veh:505 -> sends destination_vehicle_asset_id: 505, refreshes, and enables Ver dotación in Vehículos
  assetCode.value = "RAD-777";
  assetName.value = "Handy VHF Base";
  assetCategory.value = "3";
  assetLocation.value = "veh:505";
  await formCrearBien.trigger("submit");
  await new Promise((r) => setTimeout(r, 25));

  assert.equal(capturedCreatePayload.destination_vehicle_asset_id, 505);
  assert.equal(capturedCreatePayload.location_id, null);
  assert.equal(postLocationsCalls, 0, "Frontend must never call POST /inventory/locations directly for auto-vehicle");

  // Verify Vehículos table now shows 1 bien and enables 'Ver dotación' without duplicating Camioneta HGJ-875
  mockWindow.DashboardRenderer.renderVehiculosView();
  const vehHtml = elements.get("vehiculos-table-body").innerHTML;
  assert.match(vehHtml, /btn-ver-dotacion-vehiculo/);
  assert.match(vehHtml, /<strong>1<\/strong> <small class="table-muted">bien a bordo<\/small>/);
  assert.doesNotMatch(vehHtml, /Ubicación móvil no configurada/);
});

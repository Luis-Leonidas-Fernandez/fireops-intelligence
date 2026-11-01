const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const htmlPath = path.resolve(__dirname, "../index.html");
const renderJsPath = path.resolve(__dirname, "../js/render.js");

test("HTML Structure: preserves map-panel and alert card intact", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  // Verify map panel and its SVG elements are preserved exactly as requested
  assert.match(html, /class="panel map-panel"/);
  assert.match(html, /<svg viewBox="0 0 800 360"/);
  assert.match(html, /id="mapGradient"/);
  assert.match(html, /class="map-stage"/);
  assert.match(html, /class="map-callout"/);
  assert.match(html, /Alerta prioritaria/);
  assert.match(html, /Revisión próxima · 7 bienes/);
});

test("DashboardRenderer: renderRealData populates cards with backend data", () => {
  const renderJsContent = fs.readFileSync(renderJsPath, "utf8");

  // Mock DOM
  function createDOM() {
    const elements = new Map();
    function makeEl(id, className = "") {
      const el = {
        id,
        className,
        innerHTML: "",
        textContent: "",
        hidden: false,
        closest: (sel) => {
          if (sel === ".panel") return { querySelector: () => ({ textContent: "" }) };
          return null;
        },
      };
      elements.set(id, el);
      return el;
    }

    makeEl("kpi-grid");
    makeEl("chart-summary");
    makeEl("bar-chart");
    makeEl("channel-totals");
    makeEl("channel-list");
    makeEl("signal-strip");
    makeEl("country-table-body");
    makeEl("date-range");
    makeEl("country-search");
    makeEl("country-table-pagination");
    makeEl("assets-pagination-info");
    makeEl("btn-prev-assets");
    makeEl("btn-next-assets");

    return {
      querySelector: (sel) => {
        if (sel.startsWith("#")) {
          return elements.get(sel.slice(1)) || null;
        }
        return null;
      },
    };
  }

  const mockDoc = createDOM();

  const mockWindow = {
    DashboardData: {
      periods: { "90": { multiplier: 1 } },
      kpis: [],
      categories: [],
      statuses: [],
      movements: [],
    },
    Intl,
  };

  const fn = new Function("window", "document", renderJsContent);
  fn(mockWindow, mockDoc);

  assert.equal(typeof mockWindow.DashboardRenderer.setRealData, "function");

  // Sample real data from backend
  const sampleRealData = {
    categories: [
      { id: 1, name: "Material Hídrico" },
      { id: 2, name: "Herramientas de Corte" },
    ],
    locations: [
      { id: 1, name: "Móvil B-12", type: "VEHICULO" },
      { id: 2, name: "Cuartel Central", type: "FISICA" },
    ],
    assets: [
      { id: 101, internal_code: "BIE-001", name: "Manguera 38mm", category_id: 1, location_id: 1 },
      { id: 102, internal_code: "BIE-002", name: "Motosierra MS382", category_id: 2, location_id: 2 },
      { id: 103, internal_code: "BIE-003", name: "Lanza regulable", category_id: 1, location_id: null },
    ],
  };

  mockWindow.DashboardRenderer.setRealData(sampleRealData);

  // 1. Verify KPIs reflect real counts (3 total, 2 assigned, 1 in storage, 2 categories)
  const kpiHtml = mockDoc.querySelector("#kpi-grid").innerHTML;
  assert.match(kpiHtml, /Bienes en total/);
  assert.match(kpiHtml, />3</); // 3 total assets
  assert.match(kpiHtml, /Asignados en servicio/);
  assert.match(kpiHtml, />2</); // 2 assigned
  assert.match(kpiHtml, /En depósito/);
  assert.match(kpiHtml, />1</); // 1 in storage
  assert.match(kpiHtml, /Categorías activas/);

  // 2. Verify Bar Chart reflects real category names in title and abbreviated in label
  const barChartHtml = mockDoc.querySelector("#bar-chart").innerHTML;
  assert.match(barChartHtml, /Material Hídrico/);
  assert.match(barChartHtml, /Herramientas de Corte/);
  assert.match(barChartHtml, />Mat\. Hídrico<\/span>/);
  assert.match(barChartHtml, />Herramientas<\/span>/);

  // 3. Verify Channel Totals reflect percentages and correct restored colors
  const channelTotalsHtml = mockDoc.querySelector("#channel-totals").innerHTML;
  assert.match(channelTotalsHtml, /66\.7%/);
  assert.match(channelTotalsHtml, /33\.3%/);
  assert.match(channelTotalsHtml, /#E53935/);
  assert.match(channelTotalsHtml, /#ef741d/);
  assert.match(channelTotalsHtml, /#f6c548/);

  // Verify signal-strip colors match En servicio (#E53935) and Depósito (#ef741d)
  const signalStripHtml = mockDoc.querySelector("#signal-strip").innerHTML;
  assert.match(signalStripHtml, /#E53935/);
  assert.match(signalStripHtml, /#ef741d/);

  // 4. Verify Table Body reflects real assets
  const tableBodyHtml = mockDoc.querySelector("#country-table-body").innerHTML;
  assert.match(tableBodyHtml, /Manguera 38mm/);
  assert.match(tableBodyHtml, /BIE-001/);
  assert.match(tableBodyHtml, /Móvil B-12/);
  assert.match(tableBodyHtml, /Motosierra MS382/);
  assert.match(tableBodyHtml, /BIE-002/);
  assert.match(tableBodyHtml, /Cuartel Central/);
  assert.match(tableBodyHtml, /Lanza regulable/);
  assert.match(tableBodyHtml, /BIE-003/);
  assert.match(tableBodyHtml, /Depósito Central/);
});

test("CSS: Bar chart labels are semi-vertical and organized", () => {
  const cssPath = path.resolve(__dirname, "../css/components.css");
  const css = fs.readFileSync(cssPath, "utf8");

  // Verify semi-vertical rotated labels with expanded room for direct names
  assert.match(css, /\.bar-label\s*\{[^}]*rotate\(-35deg\)/);
  assert.match(css, /\.bar-chart\s*\{[^}]*padding:[^}]*56px/);
  assert.match(css, /\.bar-label\s*\{[^}]*max-width:\s*170px/);
});

test("DashboardRenderer: pagination limits table to exactly 6 elements with next/prev navigation", () => {
  const renderJsContent = fs.readFileSync(renderJsPath, "utf8");

  function createMockDOM() {
    const elements = new Map();
    function makeEl(id) {
      const el = {
        id,
        innerHTML: "",
        textContent: "",
        hidden: false,
        disabled: false,
        closest: (sel) => {
          if (sel === ".panel") return { querySelector: () => ({ textContent: "" }) };
          return null;
        },
      };
      elements.set(id, el);
      return el;
    }

    makeEl("kpi-grid");
    makeEl("chart-summary");
    makeEl("bar-chart");
    makeEl("channel-totals");
    makeEl("channel-list");
    makeEl("signal-strip");
    makeEl("country-table-body");
    makeEl("date-range");
    makeEl("country-search");
    makeEl("country-table-pagination");
    makeEl("assets-pagination-info");
    makeEl("btn-prev-assets");
    makeEl("btn-next-assets");

    return {
      querySelector: (sel) => {
        if (sel.startsWith("#")) {
          return elements.get(sel.slice(1)) || null;
        }
        return null;
      },
    };
  }

  const mockDoc = createMockDOM();
  const mockWindow = {
    DashboardData: { periods: { "90": { multiplier: 1 } }, kpis: [], categories: [], statuses: [], movements: [] },
    Intl,
  };

  const fn = new Function("window", "document", renderJsContent);
  fn(mockWindow, mockDoc);

  // Create 15 sample assets to test 3 pages (6 + 6 + 3)
  const assets15 = Array.from({ length: 15 }, (_, i) => ({
    id: i + 1,
    internal_code: `BIE-${String(i + 1).padStart(3, "0")}`,
    name: `Activo Prueba ${i + 1}`,
    category_id: 1,
    location_id: i % 2 === 0 ? 1 : null,
  }));

  const realData = {
    categories: [{ id: 1, name: "Herramientas" }],
    locations: [{ id: 1, name: "Móvil 1" }],
    assets: assets15,
  };

  mockWindow.DashboardRenderer.setRealData(realData);

  const tableBody = mockDoc.querySelector("#country-table-body");
  const infoEl = mockDoc.querySelector("#assets-pagination-info");
  const prevBtn = mockDoc.querySelector("#btn-prev-assets");
  const nextBtn = mockDoc.querySelector("#btn-next-assets");

  // Page 1: Exactly 6 rows rendered
  const rowsP1 = tableBody.innerHTML.match(/<tr/g);
  assert.equal(rowsP1.length, 6);
  assert.match(tableBody.innerHTML, /BIE-001/);
  assert.match(tableBody.innerHTML, /BIE-006/);
  assert.doesNotMatch(tableBody.innerHTML, /BIE-007/);
  assert.match(infoEl.textContent, /Mostrando 1–6 de 15/);
  assert.equal(prevBtn.disabled, true);
  assert.equal(nextBtn.disabled, false);

  // Page 2: Advance to next 6
  mockWindow.DashboardRenderer.nextAssetsPage();
  const rowsP2 = tableBody.innerHTML.match(/<tr/g);
  assert.equal(rowsP2.length, 6);
  assert.match(tableBody.innerHTML, /BIE-007/);
  assert.match(tableBody.innerHTML, /BIE-012/);
  assert.doesNotMatch(tableBody.innerHTML, /BIE-006/);
  assert.doesNotMatch(tableBody.innerHTML, /BIE-013/);
  assert.match(infoEl.textContent, /Mostrando 7–12 de 15/);
  assert.equal(prevBtn.disabled, false);
  assert.equal(nextBtn.disabled, false);

  // Page 3: Advance to next 3 (final page)
  mockWindow.DashboardRenderer.nextAssetsPage();
  const rowsP3 = tableBody.innerHTML.match(/<tr/g);
  assert.equal(rowsP3.length, 3);
  assert.match(tableBody.innerHTML, /BIE-013/);
  assert.match(tableBody.innerHTML, /BIE-015/);
  assert.match(infoEl.textContent, /Mostrando 13–15 de 15/);
  assert.equal(prevBtn.disabled, false);
  assert.equal(nextBtn.disabled, true);

  // Return to Page 2 using prevAssetsPage()
  mockWindow.DashboardRenderer.prevAssetsPage();
  assert.equal(mockWindow.DashboardRenderer.getAssetsPage(), 2);
  assert.match(tableBody.innerHTML, /BIE-007/);
  assert.equal(nextBtn.disabled, false);

  // Filter reset: switching filter resets page to 1
  mockWindow.DashboardRenderer.setRealFilter("storage");
  assert.equal(mockWindow.DashboardRenderer.getAssetsPage(), 1);
});

test("DashboardRenderer: category labels show full name by default and only abbreviate if very long", () => {
  const renderJsContent = fs.readFileSync(renderJsPath, "utf8");

  function createMockDOM() {
    const elements = new Map();
    function makeEl(id) {
      const el = {
        id,
        innerHTML: "",
        textContent: "",
        hidden: false,
        disabled: false,
        closest: (sel) => {
          if (sel === ".panel") return { querySelector: () => ({ textContent: "" }) };
          return null;
        },
      };
      elements.set(id, el);
      return el;
    }

    makeEl("kpi-grid");
    makeEl("chart-summary");
    makeEl("bar-chart");
    makeEl("channel-totals");
    makeEl("channel-list");
    makeEl("signal-strip");
    makeEl("country-table-body");
    makeEl("date-range");
    makeEl("country-search");
    makeEl("country-table-pagination");
    makeEl("assets-pagination-info");
    makeEl("btn-prev-assets");
    makeEl("btn-next-assets");

    return {
      querySelector: (sel) => {
        if (sel.startsWith("#")) {
          return elements.get(sel.slice(1)) || null;
        }
        return null;
      },
    };
  }

  const mockDoc = createMockDOM();
  const mockWindow = {
    DashboardData: {
      periods: { "90": { multiplier: 1 } },
      kpis: [],
      categories: [
        { label: "Extinción", inService: 10, maintenance: 2, retired: 1 },
        { label: "Herramientas", inService: 8, maintenance: 1, retired: 0 },
        { label: "Comunicaciones", inService: 5, maintenance: 0, retired: 0 },
        { label: "Iluminación", inService: 4, maintenance: 1, retired: 0 },
      ],
      statuses: [],
      movements: [],
    },
    Intl,
  };

  const fn = new Function("window", "document", renderJsContent);
  fn(mockWindow, mockDoc);

  // 1. Initial demo render: full names displayed because they are not excessively long
  mockWindow.DashboardRenderer.render("90");
  const initialBarHtml = mockDoc.querySelector("#bar-chart").innerHTML;
  assert.match(initialBarHtml, />Herramientas<\/span>/);
  assert.match(initialBarHtml, />Comunicaciones<\/span>/);
  assert.match(initialBarHtml, />Iluminación<\/span>/);
  assert.match(initialBarHtml, />Extinción<\/span>/);

  // 2. Real data render: direct category names appear without artificial truncation
  const sampleReal = {
    categories: [
      { id: 1, name: "Mangueras" }, // Short (9 chars) -> full name
      { id: 2, name: "Herramientas" }, // Medium (12 chars) -> full name
      { id: 3, name: "Materiales Peligrosos (HAZMAT)" }, // Standard fire service acronym -> "HAZMAT"
      { id: 4, name: "Protección Personal (EPP)" }, // Standard fire service acronym -> "EPP"
      { id: 5, name: "Categoria-test-9f118ea0" }, // Dynamic direct category name -> "Categoria-test-9f118ea0"
      { id: 6, name: "Categoria-3cbdc1e7" }, // Dynamic direct category name -> "Categoria-3cbdc1e7"
    ],
    locations: [{ id: 1, name: "Cuartel Central" }],
    assets: [
      { id: 1, internal_code: "B-1", name: "Bien 1", category_id: 1, location_id: 1 },
      { id: 2, internal_code: "B-2", name: "Bien 2", category_id: 2, location_id: 1 },
      { id: 3, internal_code: "B-3", name: "Bien 3", category_id: 3, location_id: 1 },
      { id: 4, internal_code: "B-4", name: "Bien 4", category_id: 4, location_id: 1 },
      { id: 5, internal_code: "B-5", name: "Bien 5", category_id: 5, location_id: 1 },
      { id: 6, internal_code: "B-6", name: "Bien 6", category_id: 6, location_id: 1 },
    ],
  };

  mockWindow.DashboardRenderer.setRealData(sampleReal);
  const realBarHtml = mockDoc.querySelector("#bar-chart").innerHTML;
  assert.match(realBarHtml, />Mangueras<\/span>/);
  assert.match(realBarHtml, />Herramientas<\/span>/);
  assert.match(realBarHtml, />HAZMAT<\/span>/);
  assert.match(realBarHtml, />EPP<\/span>/);
  // Very long dynamic category names are shortened with three dots (...)
  assert.match(realBarHtml, />Categoria-te\.\.\.<\/span>/);
  assert.match(realBarHtml, />Categoria-3c\.\.\.<\/span>/);
  // Full category names remain preserved in title attributes
  assert.match(realBarHtml, /title="Categoria-test-9f118ea0/);
  assert.match(realBarHtml, /title="Categoria-3cbdc1e7/);
});

test("DashboardRenderer: renderUbicacionesView renders real locations, counts, search, and filters", () => {
  const renderJsContent = fs.readFileSync(renderJsPath, "utf8");

  function createMockDOM() {
    const elements = new Map();
    function makeEl(id) {
      const el = {
        id,
        innerHTML: "",
        textContent: "",
        hidden: false,
        disabled: false,
        closest: (sel) => {
          if (sel === ".panel") return { querySelector: () => ({ textContent: "" }) };
          return null;
        },
      };
      elements.set(id, el);
      return el;
    }

    makeEl("kpi-grid");
    makeEl("chart-summary");
    makeEl("bar-chart");
    makeEl("channel-totals");
    makeEl("channel-list");
    makeEl("signal-strip");
    makeEl("country-table-body");
    makeEl("date-range");
    makeEl("country-search");
    makeEl("country-table-pagination");
    makeEl("assets-pagination-info");
    makeEl("btn-prev-assets");
    makeEl("btn-next-assets");
    makeEl("ubicaciones-table-body");
    makeEl("ubicaciones-count-all");
    makeEl("ubicaciones-count-fisica");
    makeEl("ubicaciones-count-vehiculo");

    return {
      querySelector: (sel) => {
        if (sel.startsWith("#")) {
          return elements.get(sel.slice(1)) || null;
        }
        return null;
      },
    };
  }

  const mockDoc = createMockDOM();
  const mockWindow = {
    DashboardData: { periods: { "90": { multiplier: 1 } }, kpis: [], categories: [], statuses: [], movements: [] },
    Intl,
  };

  const fn = new Function("window", "document", renderJsContent);
  fn(mockWindow, mockDoc);

  const realData = {
    categories: [{ id: 1, name: "Equipos" }],
    locations: [
      { id: 1, name: "Cuartel Central", location_type: "FISICA", description: "Hangar principal", active: true },
      { id: 2, name: "Autobomba B-12", location_type: "VEHICULO", container_asset_id: 10, description: "Patente AF-321", active: true },
      { id: 3, name: "Destacamento Sur", location_type: "FISICA", description: "Base operativa sur", active: true },
    ],
    assets: [
      { id: 10, internal_code: "VEH-012", name: "Camión Autobomba", category_id: 1, location_id: 1 },
      { id: 11, internal_code: "BIE-001", name: "Manguera 45mm", category_id: 1, location_id: 2 },
      { id: 12, internal_code: "BIE-002", name: "Lanza", category_id: 1, location_id: 2 },
    ],
  };

  mockWindow.DashboardRenderer.setRealData(realData);

  const tbody = mockDoc.querySelector("#ubicaciones-table-body");
  assert.equal(mockDoc.querySelector("#ubicaciones-count-all").textContent, 3);
  assert.equal(mockDoc.querySelector("#ubicaciones-count-fisica").textContent, 2);
  assert.equal(mockDoc.querySelector("#ubicaciones-count-vehiculo").textContent, 1);

  assert.match(tbody.innerHTML, /Cuartel Central/);
  assert.match(tbody.innerHTML, /Autobomba B-12/);
  assert.match(tbody.innerHTML, /Destacamento Sur/);
  assert.match(tbody.innerHTML, /Camión Autobomba/);

  // Filter by VEHICULO
  mockWindow.DashboardRenderer.setUbicacionesFilter("VEHICULO");
  assert.match(tbody.innerHTML, /Autobomba B-12/);
  assert.doesNotMatch(tbody.innerHTML, /Cuartel Central/);
  assert.doesNotMatch(tbody.innerHTML, /Destacamento Sur/);

  // Filter by FISICA
  mockWindow.DashboardRenderer.setUbicacionesFilter("FISICA");
  assert.match(tbody.innerHTML, /Cuartel Central/);
  assert.match(tbody.innerHTML, /Destacamento Sur/);
  assert.doesNotMatch(tbody.innerHTML, /Autobomba B-12/);

  // Reset filter and search by query
  mockWindow.DashboardRenderer.setUbicacionesFilter("all");
  mockWindow.DashboardRenderer.setUbicacionesQuery("Hangar");
  assert.match(tbody.innerHTML, /Cuartel Central/);
  assert.doesNotMatch(tbody.innerHTML, /Destacamento Sur/);
});

test("DashboardRenderer: renderUbicacionBienesView filters strictly by current location_id, supports search, and shows empty state", () => {
  const renderJsContent = fs.readFileSync(renderJsPath, "utf8");

  function createMockDOM() {
    const elements = new Map();
    function makeEl(id) {
      const el = {
        id,
        innerHTML: "",
        textContent: "",
        hidden: false,
        disabled: false,
        dataset: {},
        closest: (sel) => {
          if (sel === ".panel") return { querySelector: () => ({ textContent: "" }) };
          return null;
        },
      };
      elements.set(id, el);
      return el;
    }

    makeEl("kpi-grid");
    makeEl("chart-summary");
    makeEl("bar-chart");
    makeEl("channel-totals");
    makeEl("channel-list");
    makeEl("signal-strip");
    makeEl("country-table-body");
    makeEl("date-range");
    makeEl("country-search");
    makeEl("country-table-pagination");
    makeEl("assets-pagination-info");
    makeEl("btn-prev-assets");
    makeEl("btn-next-assets");
    makeEl("ubicacion-bienes-table-body");
    makeEl("ubicacion-detalle-titulo");
    makeEl("ubicacion-detalle-kicker");
    makeEl("ubicacion-detalle-tipo");
    makeEl("ubicacion-detalle-count");
    makeEl("ubicacion-detalle-descripcion");
    makeEl("bien-detalle-titulo");
    makeEl("bien-detalle-kicker");
    makeEl("bien-detalle-id");
    makeEl("bien-detalle-codigo");
    makeEl("bien-detalle-nombre");
    makeEl("bien-detalle-categoria");
    makeEl("bien-detalle-ubicacion");
    makeEl("bien-detalle-estado");
    makeEl("btn-mover-desde-detalle");
    makeEl("bien-detalle-movimientos-tbody");

    return {
      querySelector: (sel) => {
        if (sel.startsWith("#")) {
          return elements.get(sel.slice(1)) || null;
        }
        return null;
      },
    };
  }

  const mockDoc = createMockDOM();
  const mockWindow = {
    DashboardData: { periods: { "90": { multiplier: 1 } }, kpis: [], categories: [], statuses: [], movements: [] },
    Intl,
  };

  const fn = new Function("window", "document", renderJsContent);
  fn(mockWindow, mockDoc);

  const realData = {
    categories: [
      { id: 1, name: "Material Hídrico" },
      { id: 2, name: "Rescate Vehicular" },
    ],
    locations: [
      { id: 1, name: "Cuartel Central", location_type: "FISICA", description: "Av. San Martín 450", active: true },
      { id: 2, name: "Autobomba B-12", location_type: "VEHICULO", container_asset_id: 10, description: "Unidad pesada", active: true },
      { id: 3, name: "Depósito Auxiliar Vacío", location_type: "FISICA", description: "Sin stock", active: true },
    ],
    assets: [
      { id: 101, internal_code: "BIE-101", name: "Manguera 45mm", category_id: 1, location_id: 2 },
      { id: 102, internal_code: "BIE-102", name: "Cizalla Hidráulica Holmatro", category_id: 2, location_id: 2 },
      // BIE-103 was historically at location 2 (see movements below), but its current location_id is 1
      { id: 103, internal_code: "BIE-103", name: "Generador Honda", category_id: 1, location_id: 1 },
      { id: 104, internal_code: "BIE-104", name: "Equipo ERA Scott", category_id: 2, location_id: null },
    ],
    movements: [
      {
        id: 500,
        asset_id: 103,
        asset_code: "BIE-103",
        asset_name: "Generador Honda",
        movement_type: "TRASLADO",
        origin_location_id: 2,
        origin_location_name: "Autobomba B-12",
        destination_location_id: 1,
        destination_location_name: "Cuartel Central",
        occurred_at: "2026-10-20T10:00:00Z",
        reason: "Mantenimiento en cuartel",
      },
    ],
  };

  mockWindow.DashboardRenderer.setRealData(realData);

  // 1, 2 & 3. Open location 2 ("Autobomba B-12"): shows only BIE-101 and BIE-102, NOT BIE-103 (historical) or BIE-104 (storage)
  mockWindow.DashboardRenderer.renderUbicacionBienesView(realData, 2, "");
  assert.equal(mockDoc.querySelector("#ubicacion-detalle-titulo").textContent, "Autobomba B-12");
  assert.equal(mockDoc.querySelector("#ubicacion-detalle-count").textContent, "2 bienes asignados");

  const locTbody = mockDoc.querySelector("#ubicacion-bienes-table-body");
  assert.match(locTbody.innerHTML, /BIE-101/);
  assert.match(locTbody.innerHTML, /Manguera 45mm/);
  assert.match(locTbody.innerHTML, /Material Hídrico/);
  assert.match(locTbody.innerHTML, /BIE-102/);
  assert.match(locTbody.innerHTML, /Cizalla Hidráulica Holmatro/);
  assert.doesNotMatch(locTbody.innerHTML, /BIE-103/, "Historical asset currently in another location must NOT appear");
  assert.doesNotMatch(locTbody.innerHTML, /BIE-104/, "Unassigned storage asset must NOT appear");

  // 5. Search inside location 2
  mockWindow.DashboardRenderer.setUbicacionBienesQuery("Holmatro");
  assert.match(locTbody.innerHTML, /BIE-102/);
  assert.doesNotMatch(locTbody.innerHTML, /BIE-101/);

  // Search with no match inside location 2
  mockWindow.DashboardRenderer.setUbicacionBienesQuery("InexistenteXYZ");
  assert.match(locTbody.innerHTML, /No se encontraron bienes en esta ubicación que coincidan con la búsqueda/);

  // 4. Empty location (location 3) shows empty state message
  mockWindow.DashboardRenderer.renderUbicacionBienesView(realData, 3, "");
  assert.equal(mockDoc.querySelector("#ubicacion-detalle-titulo").textContent, "Depósito Auxiliar Vacío");
  assert.equal(mockDoc.querySelector("#ubicacion-detalle-count").textContent, "0 bienes asignados");
  assert.match(locTbody.innerHTML, /No hay bienes asignados actualmente a esta ubicación/);

  // 8. Asset detail view rendering (renderDetalleBienView)
  mockWindow.DashboardRenderer.renderDetalleBienView(realData, 103);
  assert.equal(mockDoc.querySelector("#bien-detalle-titulo").textContent, "Generador Honda");
  assert.equal(mockDoc.querySelector("#bien-detalle-codigo").textContent, "BIE-103");
  assert.equal(mockDoc.querySelector("#bien-detalle-categoria").textContent, "Material Hídrico");
  assert.equal(mockDoc.querySelector("#bien-detalle-ubicacion").textContent, "Cuartel Central");
  assert.match(mockDoc.querySelector("#bien-detalle-movimientos-tbody").innerHTML, /Mantenimiento en cuartel/);
});

test("DashboardRenderer: renderCategoriaBienesView filters strictly by category_id, supports search, and shows empty state", () => {
  const renderJsContent = fs.readFileSync(renderJsPath, "utf8");

  function createMockDOM() {
    const elements = new Map();
    function makeEl(id) {
      const el = {
        id,
        innerHTML: "",
        textContent: "",
        hidden: false,
        disabled: false,
        dataset: {},
        closest: (sel) => {
          if (sel === ".panel") return { querySelector: () => ({ textContent: "" }) };
          return null;
        },
      };
      elements.set(id, el);
      return el;
    }

    makeEl("kpi-grid");
    makeEl("chart-summary");
    makeEl("bar-chart");
    makeEl("channel-totals");
    makeEl("channel-list");
    makeEl("signal-strip");
    makeEl("country-table-body");
    makeEl("date-range");
    makeEl("country-search");
    makeEl("country-table-pagination");
    makeEl("assets-pagination-info");
    makeEl("btn-prev-assets");
    makeEl("btn-next-assets");
    makeEl("categoria-bienes-table-body");
    makeEl("categoria-detalle-titulo");
    makeEl("categoria-detalle-kicker");
    makeEl("categoria-detalle-estado");
    makeEl("categoria-detalle-count");
    makeEl("categoria-detalle-descripcion");

    return {
      querySelector: (sel) => {
        if (sel.startsWith("#")) {
          return elements.get(sel.slice(1)) || null;
        }
        return null;
      },
    };
  }

  const mockDoc = createMockDOM();
  const mockWindow = {
    DashboardData: { periods: { "90": { multiplier: 1 } }, kpis: [], categories: [], statuses: [], movements: [] },
    Intl,
  };

  const fn = new Function("window", "document", renderJsContent);
  fn(mockWindow, mockDoc);

  const realData = {
    categories: [
      { id: 1, name: "Material Hídrico" },
      { id: 2, name: "Rescate Vehicular" },
      { id: 3, name: "Comunicaciones tácticas" },
    ],
    locations: [
      { id: 1, name: "Cuartel Central", location_type: "FISICA", active: true },
      { id: 2, name: "Autobomba B-12", location_type: "VEHICULO", active: true },
    ],
    assets: [
      { id: 101, internal_code: "BIE-101", name: "Manguera 45mm", category_id: 1, location_id: 2 },
      { id: 103, internal_code: "BIE-103", name: "Generador Honda", category_id: 1, location_id: null },
      { id: 102, internal_code: "BIE-102", name: "Cizalla Hidráulica Holmatro", category_id: 2, location_id: 1 },
    ],
    movements: [],
  };

  mockWindow.DashboardRenderer.setRealData(realData);

  // 1, 2 & 3. Open category 1 ("Material Hídrico"): shows ONLY BIE-101 and BIE-103, NOT BIE-102 (category 2)
  mockWindow.DashboardRenderer.renderCategoriaBienesView(realData, 1, "");
  assert.equal(mockDoc.querySelector("#categoria-detalle-titulo").textContent, "Material Hídrico");
  assert.equal(mockDoc.querySelector("#categoria-detalle-count").textContent, "2 bienes asociados");
  assert.equal(mockDoc.querySelector("#categoria-detalle-estado").textContent, "Activa");

  const catTbody = mockDoc.querySelector("#categoria-bienes-table-body");
  assert.match(catTbody.innerHTML, /BIE-101/);
  assert.match(catTbody.innerHTML, /Manguera 45mm/);
  assert.match(catTbody.innerHTML, /Autobomba B-12/);
  assert.match(catTbody.innerHTML, /BIE-103/);
  assert.match(catTbody.innerHTML, /Generador Honda/);
  assert.match(catTbody.innerHTML, /Sin asignación fija \(Depósito\)/);
  assert.doesNotMatch(catTbody.innerHTML, /BIE-102/, "Assets from other categories must NOT appear");

  // 5. Search inside category 1 by code, name or ID
  mockWindow.DashboardRenderer.setCategoriaBienesQuery("Honda");
  assert.match(catTbody.innerHTML, /BIE-103/);
  assert.doesNotMatch(catTbody.innerHTML, /BIE-101/);

  mockWindow.DashboardRenderer.setCategoriaBienesQuery("101");
  assert.match(catTbody.innerHTML, /BIE-101/);
  assert.doesNotMatch(catTbody.innerHTML, /BIE-103/);

  // Search with no match inside category 1
  mockWindow.DashboardRenderer.setCategoriaBienesQuery("InexistenteXYZ");
  assert.match(catTbody.innerHTML, /No se encontraron bienes en esta categoría que coincidan con la búsqueda/);

  // 4. Empty category (category 3) shows empty state message and "Sin bienes" badge
  mockWindow.DashboardRenderer.renderCategoriaBienesView(realData, 3, "");
  assert.equal(mockDoc.querySelector("#categoria-detalle-titulo").textContent, "Comunicaciones tácticas");
  assert.equal(mockDoc.querySelector("#categoria-detalle-count").textContent, "0 bienes asociados");
  assert.equal(mockDoc.querySelector("#categoria-detalle-estado").textContent, "Sin bienes");
  assert.match(catTbody.innerHTML, /No hay bienes asociados actualmente a esta categoría/);
});

test("DashboardRenderer: renderVehiculosView identifies vehicles via VEHICULO + container_asset_id, shows equipped/unequipped states, supports search, and updates after transfers", () => {
  const renderJsContent = fs.readFileSync(renderJsPath, "utf8");

  function createMockDOM() {
    const elements = new Map();
    function makeEl(id) {
      const el = {
        id,
        innerHTML: "",
        textContent: "",
        hidden: false,
        disabled: false,
        dataset: {},
        closest: (sel) => {
          if (sel === ".panel") return { querySelector: () => ({ textContent: "" }) };
          return null;
        },
      };
      elements.set(id, el);
      return el;
    }

    makeEl("kpi-grid");
    makeEl("chart-summary");
    makeEl("bar-chart");
    makeEl("channel-totals");
    makeEl("channel-list");
    makeEl("signal-strip");
    makeEl("country-table-body");
    makeEl("date-range");
    makeEl("country-search");
    makeEl("country-table-pagination");
    makeEl("assets-pagination-info");
    makeEl("btn-prev-assets");
    makeEl("btn-next-assets");
    makeEl("vehiculos-table-body");
    makeEl("vehiculos-count-total");
    makeEl("vehiculos-count-equipamiento");

    return {
      querySelector: (sel) => {
        if (sel.startsWith("#")) {
          return elements.get(sel.slice(1)) || null;
        }
        return null;
      },
    };
  }

  const mockDoc = createMockDOM();
  const mockWindow = {
    DashboardData: { periods: { "90": { multiplier: 1 } }, kpis: [], categories: [], statuses: [], movements: [] },
    Intl,
  };

  const fn = new Function("window", "document", renderJsContent);
  fn(mockWindow, mockDoc);

  const realData = {
    categories: [
      { id: 1, name: "Unidades Pesadas" },
      { id: 2, name: "Vehículo" }, // Exact category "Vehículo" (singular with accent)
      { id: 3, name: "Rescate Vehicular" }, // Partial match category -> must NOT be treated as vehicle category
    ],
    locations: [
      { id: 1, name: "Cuartel Central", location_type: "FISICA", active: true },
      { id: 2, name: "Destacamento Norte", location_type: "FISICA", active: true },
      { id: 10, name: "Autobomba B-01", location_type: "VEHICULO", container_asset_id: 501, description: "Primera dotación", active: true },
      { id: 11, name: "Cisterna C-04", location_type: "VEHICULO", container_asset_id: 502, description: "Apoyo hídrico", active: true },
    ],
    assets: [
      // Caso B (with category "Vehículo" AND VEHICULO location): must appear ONCE without duplicates
      { id: 501, internal_code: "MOV-001", name: "Scania P360 Autobomba", category_id: 2, location_id: 1 },
      // Caso B (with another category AND VEHICULO location, 0 assets on board)
      { id: 502, internal_code: "MOV-004", name: "Camión Cisterna Iveco", category_id: 1, location_id: null },
      // Caso A & C: Camioneta registered ONLY as patrimonial asset in category "Vehículo" (no VEHICULO location yet)
      { id: 503, internal_code: "CAM-012", name: "Camioneta Toyota Hilux Logística", category_id: 2, location_id: 1 },
      // Regular asset in partial-match category "Rescate Vehicular" WITHOUT a VEHICULO location -> must NOT appear
      { id: 599, internal_code: "RES-099", name: "Cizalla Hidráulica", category_id: 3, location_id: 1 },
      // 2 assets boarded inside Autobomba B-01 (location_id: 10)
      { id: 601, internal_code: "RES-101", name: "Separador Hidráulico", category_id: 3, location_id: 10 },
      { id: 602, internal_code: "RES-102", name: "Equipo ERA MSA", category_id: 3, location_id: 10 },
    ],
    movements: [],
  };

  mockWindow.DashboardRenderer.setRealData(realData);

  const vehTbody = mockDoc.querySelector("#vehiculos-table-body");
  // 3 vehicles total: Autobomba B-01 (501), Cisterna C-04 (502), and Camioneta Toyota Hilux (503). No duplicate for 501!
  assert.equal(mockDoc.querySelector("#vehiculos-count-total").textContent, "3 unidades registradas");
  assert.equal(mockDoc.querySelector("#vehiculos-count-equipamiento").textContent, "2 bienes a bordo");

  const rows = vehTbody.innerHTML.match(/<tr/g) || [];
  assert.equal(rows.length, 3, "Must render exactly 3 rows without duplicating asset 501");

  // Caso B with equipment: Autobomba B-01 (2 assets on board, stationed at Cuartel Central)
  assert.match(vehTbody.innerHTML, /Autobomba B-01/);
  assert.match(vehTbody.innerHTML, /MOV-001/);
  assert.match(vehTbody.innerHTML, /Scania P360 Autobomba/);
  assert.match(vehTbody.innerHTML, /Cuartel Central/);
  assert.match(vehTbody.innerHTML, /<strong>2<\/strong>\s*<small class="table-muted">bienes a bordo<\/small>/);

  // Caso B without equipment: Cisterna C-04 (0 assets on board, Depósito)
  assert.match(vehTbody.innerHTML, /Cisterna C-04/);
  assert.match(vehTbody.innerHTML, /MOV-004/);
  assert.match(vehTbody.innerHTML, /Sin asignación fija \(Depósito\)/);
  assert.match(vehTbody.innerHTML, /<strong>0<\/strong>\s*<small class="table-muted">bienes a bordo<\/small>/);

  // Caso A & Caso C: Camioneta registered only as patrimonial asset in category "Vehículo"
  assert.match(vehTbody.innerHTML, /CAM-012/);
  assert.match(vehTbody.innerHTML, /Camioneta Toyota Hilux Logística/);
  assert.match(vehTbody.innerHTML, /En servicio/);
  assert.doesNotMatch(vehTbody.innerHTML, /Ubicación móvil no configurada/);
  assert.doesNotMatch(vehTbody.innerHTML, /Sin dotación móvil/);
  assert.doesNotMatch(vehTbody.innerHTML, /Sin ubicación móvil/);
  assert.match(vehTbody.innerHTML, /data-asset-id="503">Ficha del móvil<\/button>/);

  // Does NOT include assets from partial-match category "Rescate Vehicular"
  assert.doesNotMatch(vehTbody.innerHTML, /RES-099/);
  assert.doesNotMatch(vehTbody.innerHTML, /Cizalla Hidráulica/);

  // Search by code or name (finds patrimonial camioneta too)
  mockWindow.DashboardRenderer.setVehiculosQuery("Hilux");
  assert.match(vehTbody.innerHTML, /CAM-012/);
  assert.doesNotMatch(vehTbody.innerHTML, /Autobomba B-01/);

  mockWindow.DashboardRenderer.setVehiculosQuery("MOV-004");
  assert.match(vehTbody.innerHTML, /Cisterna C-04/);
  assert.doesNotMatch(vehTbody.innerHTML, /Autobomba B-01/);

  mockWindow.DashboardRenderer.setVehiculosQuery("InexistenteXYZ");
  assert.match(vehTbody.innerHTML, /No se encontraron vehículos que coincidan con la búsqueda/);

  mockWindow.DashboardRenderer.setVehiculosQuery("");

  // Simulate post-transfer update: move RES-101 from Autobomba B-01 (loc 10) to Cisterna C-04 (loc 11), and park Cisterna C-04 at Destacamento Norte (loc 2)
  const updatedData = {
    ...realData,
    assets: [
      { id: 501, internal_code: "MOV-001", name: "Scania P360 Autobomba", category_id: 2, location_id: 1 },
      { id: 502, internal_code: "MOV-004", name: "Camión Cisterna Iveco", category_id: 1, location_id: 2 },
      { id: 503, internal_code: "CAM-012", name: "Camioneta Toyota Hilux Logística", category_id: 2, location_id: 1 },
      { id: 601, internal_code: "RES-101", name: "Separador Hidráulico", category_id: 3, location_id: 11 },
      { id: 602, internal_code: "RES-102", name: "Equipo ERA MSA", category_id: 3, location_id: 10 },
    ],
  };
  mockWindow.DashboardRenderer.setRealData(updatedData);
  assert.match(vehTbody.innerHTML, /Destacamento Norte/);
  assert.match(vehTbody.innerHTML, /<strong>1<\/strong>\s*<small class="table-muted">bien a bordo<\/small>/);

  // Empty state when neither VEHICULO locations nor assets in "Vehículo"/"Vehículos" exist
  mockWindow.DashboardRenderer.renderVehiculosView({
    categories: [{ id: 3, name: "Rescate Vehicular" }],
    locations: [{ id: 1, name: "Cuartel Central", location_type: "FISICA", active: true }],
    assets: [{ id: 599, internal_code: "RES-099", name: "Cizalla Hidráulica", category_id: 3, location_id: 1 }],
  }, "");
  assert.equal(mockDoc.querySelector("#vehiculos-count-total").textContent, "0 unidades registradas");
  assert.match(vehTbody.innerHTML, /No hay vehículos operativos registrados actualmente/);
});

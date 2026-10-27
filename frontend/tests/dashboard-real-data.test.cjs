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

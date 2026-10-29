const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const htmlPath = path.resolve(__dirname, "../index.html");
const appJsPath = path.resolve(__dirname, "../js/app.js");

test("HTML Structure: contains all required views and navigation items", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  // Verify navigation buttons exist for each requested view
  assert.match(html, /data-view="Inventario general"/);
  assert.match(html, /data-view="Bienes"/);
  assert.match(html, /data-view="Categorías"/);
  assert.match(html, /data-view="Ubicaciones"/);
  assert.match(html, /data-view="Invitaciones"/);

  // Verify view container elements exist with class view-content
  assert.match(html, /id="view-inventario-general"[^>]*class="[^"]*view-content/);
  assert.match(html, /id="view-bienes"[^>]*class="[^"]*view-content/);
  assert.match(html, /id="view-nuevo-bien"[^>]*class="[^"]*view-content/);
  assert.match(html, /id="view-categorias"[^>]*class="[^"]*view-content/);
  assert.match(html, /id="view-nueva-categoria"[^>]*class="[^"]*view-content/);
  assert.match(html, /id="view-ubicaciones"[^>]*class="[^"]*view-content/);
  assert.match(html, /id="view-invitaciones"[^>]*class="[^"]*view-content/);

  // Verify 'Nuevo bien' button and creation form exist
  assert.match(html, /id="btn-nuevo-bien"/);
  assert.match(html, /id="form-crear-bien"/);
  assert.match(html, /Registrar Nuevo Bien/);

  // Verify 'Nueva categoría' button and creation form exist
  assert.match(html, /id="btn-nueva-categoria"/);
  assert.match(html, /id="form-crear-categoria"/);
  assert.match(html, /Registrar Nueva Categoría/);

  // Verify dashboard heading actions has ID for dynamic toggling
  assert.match(html, /id="dashboard-heading-actions"/);

  // Verify tables and semantic structure exist inside each view
  assert.match(html, /Parque de Bienes y Materiales/);
  assert.match(html, /Categorías de Inventario/);
  assert.match(html, /Ubicaciones y Destinos/);
  assert.match(html, /Gestión de accesos/);

  // Verify Unified Access Management tabs & panels exist and zero fictitious rows/buttons remain
  assert.match(html, /id="tab-access-requests"/);
  assert.match(html, /id="tab-access-invitations"/);
  assert.match(html, /id="panel-access-requests"/);
  assert.match(html, /id="panel-access-invitations"/);
  assert.match(html, /id="access-requests-tbody"/);
  assert.match(html, /id="access-invitations-tbody"/);
  assert.doesNotMatch(html, /j\.martinez@bomberos\.gob\.ar/);
  assert.doesNotMatch(html, /r\.sosa@bomberos\.gob\.ar/);
  assert.doesNotMatch(html, /m\.alvarez@bomberos\.gob\.ar/);
  assert.doesNotMatch(html, /d\.fernandez@bomberos\.gob\.ar/);
  assert.doesNotMatch(html, /Nueva invitación/);
  assert.doesNotMatch(html, />Revocar</);
});

test("View Switching Simulation: toggling views hides dashboard cards and displays only target view", () => {
  // Mock element builder
  function createElement(id, dataset = {}, hidden = false) {
    const classList = new Set();
    const attrs = new Map();
    return {
      id,
      dataset,
      hidden,
      textContent: "",
      classList: {
        add: (c) => classList.add(c),
        remove: (c) => classList.delete(c),
        toggle: (c, force) => (force ? classList.add(c) : classList.delete(c)),
        contains: (c) => classList.has(c),
      },
      setAttribute: (k, v) => attrs.set(k, String(v)),
      removeAttribute: (k) => attrs.delete(k),
      getAttribute: (k) => attrs.get(k) || null,
      querySelector: () => null,
      closest: () => null,
    };
  }

  const pageTitle = createElement("page-title");
  const pageSubtitle = createElement("page-subtitle");
  const headingActions = createElement("dashboard-heading-actions", {}, false);

  const viewInventory = createElement("view-inventario-general", { view: "Inventario general" }, false);
  const viewBienes = createElement("view-bienes", { view: "Bienes" }, true);
  const viewNuevoBien = createElement("view-nuevo-bien", { view: "Nuevo bien" }, true);
  const viewCategorias = createElement("view-categorias", { view: "Categorías" }, true);
  const viewNuevaCategoria = createElement("view-nueva-categoria", { view: "Nueva categoría" }, true);
  const viewUbicaciones = createElement("view-ubicaciones", { view: "Ubicaciones" }, true);
  const viewInvitaciones = createElement("view-invitaciones", { view: "Invitaciones" }, true);
  const viewGeneric = createElement("view-generic", { view: "placeholder" }, true);

  const viewContainers = [
    viewInventory,
    viewBienes,
    viewNuevoBien,
    viewCategorias,
    viewNuevaCategoria,
    viewUbicaciones,
    viewInvitaciones,
    viewGeneric,
  ];

  const VIEW_SUBTITLES = {
    "Inventario general": "Vista operativa de bienes, estados y movimientos del inventario.",
    "Bienes": "Gestión integral de equipamiento, herramientas y materiales operativos.",
    "Nuevo bien": "Alta de equipamiento, herramientas y materiales operativos.",
    "Categorías": "Clasificación y catálogo de bienes del cuerpo de bomberos.",
    "Nueva categoría": "Alta y registro de nueva categoría en el catálogo operativo.",
    "Ubicaciones": "Destinos operativos, cuarteles, depósitos y móviles asignados.",
    "Invitaciones": "Control y emisión de invitaciones de acceso para personal autorizado.",
  };

  function simulateSetActiveView(view) {
    pageTitle.textContent = view;
    pageSubtitle.textContent = VIEW_SUBTITLES[view] || `${view}: vista ilustrativa.`;
    headingActions.hidden = (view !== "Inventario general");

    let matchedSpecific = false;
    viewContainers.forEach((container) => {
      const targetView = container.dataset.view;
      if (targetView === view) {
        container.hidden = false;
        matchedSpecific = true;
      } else if (container.id !== "view-generic") {
        container.hidden = true;
      }
    });

    if (viewGeneric) {
      if (!matchedSpecific && view !== "Inventario general") {
        viewGeneric.hidden = false;
      } else {
        viewGeneric.hidden = true;
      }
    }
  }

  // 1. Initial State: Inventario general is active
  assert.equal(viewInventory.hidden, false);
  assert.equal(viewBienes.hidden, true);
  assert.equal(headingActions.hidden, false);

  // 2. Click Bienes -> Dashboard cards must disappear, Bienes view appears
  simulateSetActiveView("Bienes");
  assert.equal(viewInventory.hidden, true, "Inventario general cards must be hidden");
  assert.equal(viewBienes.hidden, false, "Bienes view must be visible");
  assert.equal(viewNuevoBien.hidden, true, "Nuevo bien view initially hidden");
  assert.equal(viewCategorias.hidden, true);
  assert.equal(viewUbicaciones.hidden, true);
  assert.equal(viewInvitaciones.hidden, true);
  assert.equal(headingActions.hidden, true, "Heading actions should hide outside Inventario general");
  assert.equal(pageTitle.textContent, "Bienes");
  assert.equal(pageSubtitle.textContent, VIEW_SUBTITLES["Bienes"]);

  // 2b. Click '+ Nuevo bien' while on Bienes view -> Navigates to create asset view
  simulateSetActiveView("Nuevo bien");
  assert.equal(viewInventory.hidden, true, "Inventario general cards must remain hidden");
  assert.equal(viewBienes.hidden, true, "Bienes view must hide when creating a new bien");
  assert.equal(viewNuevoBien.hidden, false, "Nuevo bien form view must become visible");
  assert.equal(viewCategorias.hidden, true);
  assert.equal(viewUbicaciones.hidden, true);
  assert.equal(viewInvitaciones.hidden, true);
  assert.equal(headingActions.hidden, true);
  assert.equal(pageTitle.textContent, "Nuevo bien");
  assert.equal(pageSubtitle.textContent, VIEW_SUBTITLES["Nuevo bien"]);

  // 2c. Return/Cancel back to Bienes
  simulateSetActiveView("Bienes");
  assert.equal(viewBienes.hidden, false, "Bienes view must reappear after returning");
  assert.equal(viewNuevoBien.hidden, true, "Nuevo bien form must be hidden");

  // 3. Click Categorías -> Only Categorías appears
  simulateSetActiveView("Categorías");
  assert.equal(viewInventory.hidden, true);
  assert.equal(viewBienes.hidden, true);
  assert.equal(viewCategorias.hidden, false);
  assert.equal(viewNuevaCategoria.hidden, true, "Nueva categoría form initially hidden");
  assert.equal(pageTitle.textContent, "Categorías");
  assert.equal(pageSubtitle.textContent, VIEW_SUBTITLES["Categorías"]);

  // 3b. Click '+ Nueva categoría' while on Categorías view -> Navigates to create category view
  simulateSetActiveView("Nueva categoría");
  assert.equal(viewInventory.hidden, true, "Dashboard cards must remain hidden");
  assert.equal(viewCategorias.hidden, true, "Categorías list view must hide when creating new category");
  assert.equal(viewNuevaCategoria.hidden, false, "Nueva categoría form must become visible");
  assert.equal(headingActions.hidden, true);
  assert.equal(pageTitle.textContent, "Nueva categoría");
  assert.equal(pageSubtitle.textContent, VIEW_SUBTITLES["Nueva categoría"]);

  // 3c. Return/Cancel back to Categorías
  simulateSetActiveView("Categorías");
  assert.equal(viewCategorias.hidden, false, "Categorías view must reappear after returning");
  assert.equal(viewNuevaCategoria.hidden, true, "Nueva categoría form must be hidden");

  // 4. Click Ubicaciones -> Only Ubicaciones appears
  simulateSetActiveView("Ubicaciones");
  assert.equal(viewInventory.hidden, true);
  assert.equal(viewCategorias.hidden, true);
  assert.equal(viewUbicaciones.hidden, false);
  assert.equal(pageTitle.textContent, "Ubicaciones");
  assert.equal(pageSubtitle.textContent, VIEW_SUBTITLES["Ubicaciones"]);

  // 5. Click Invitaciones -> Only Invitaciones appears
  simulateSetActiveView("Invitaciones");
  assert.equal(viewInventory.hidden, true);
  assert.equal(viewUbicaciones.hidden, true);
  assert.equal(viewInvitaciones.hidden, false);
  assert.equal(pageTitle.textContent, "Invitaciones");
  assert.equal(pageSubtitle.textContent, VIEW_SUBTITLES["Invitaciones"]);

  // 6. Return to Inventario general -> Dashboard cards reappear!
  simulateSetActiveView("Inventario general");
  assert.equal(viewInventory.hidden, false, "Dashboard cards must reappear");
  assert.equal(viewBienes.hidden, true);
  assert.equal(viewCategorias.hidden, true);
  assert.equal(viewUbicaciones.hidden, true);
  assert.equal(viewInvitaciones.hidden, true);
  assert.equal(headingActions.hidden, false);
  assert.equal(pageTitle.textContent, "Inventario general");
  assert.equal(pageSubtitle.textContent, VIEW_SUBTITLES["Inventario general"]);
});

test("Mobile Responsiveness & Symmetry: verifies CSS constraints for 400px viewports", () => {
  const layoutCss = fs.readFileSync(path.resolve(__dirname, "../css/layout.css"), "utf8");
  const componentsCss = fs.readFileSync(path.resolve(__dirname, "../css/components.css"), "utf8");
  const tokensCss = fs.readFileSync(path.resolve(__dirname, "../css/tokens.css"), "utf8");

  // Verify overflow-x protection prevents asymmetrical document widening
  assert.match(layoutCss, /html,\s*body\s*\{[^}]*overflow-x:\s*hidden/);

  // Verify .table-scroll is relative, box-sizing, and constrained
  assert.match(componentsCss, /\.table-scroll\s*\{[^}]*position:\s*relative/);
  assert.match(componentsCss, /\.table-scroll\s*\{[^}]*overflow-x:\s*auto/);
  assert.match(componentsCss, /\.table-scroll\s*\{[^}]*max-width:\s*100%/);

  // Verify sr-only does not leak into document width
  assert.match(tokensCss, /\.sr-only\s*\{[^}]*left:\s*0/);
  assert.match(tokensCss, /\.sr-only\s*\{[^}]*top:\s*0/);

  // Verify .table-tabs scroll horizontally without blowing viewport
  assert.match(componentsCss, /\.table-tabs\s*\{[^}]*overflow-x:\s*auto/);

  // Verify mobile panel header aligns stretch / column on mobile breakpoint
  assert.match(layoutCss, /\.panel-header\s*\{[^}]*flex-direction:\s*column/);

  // Verify symmetrical padding in layout media queries
  assert.match(layoutCss, /padding:\s*18px\s*14px\s*28px/);
});

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const { createNavigationController, MODULE_PERMISSIONS } = require(
  path.resolve(__dirname, "../js/navigation.js")
);

// Minimal mock DOM node for testing UI elements in Node
function createMockElement(tag, attributes = {}) {
  const attrs = new Map(Object.entries(attributes));
  const classListSet = new Set(
    attributes.class ? attributes.class.split(" ").filter(Boolean) : []
  );

  return {
    tagName: tag.toUpperCase(),
    dataset: attributes.dataset || {},
    classList: {
      add: (cls) => classListSet.add(cls),
      remove: (cls) => classListSet.delete(cls),
      contains: (cls) => classListSet.has(cls),
      toggle: (cls, force) => {
        if (force === undefined) {
          classListSet.has(cls) ? classListSet.delete(cls) : classListSet.add(cls);
        } else if (force) {
          classListSet.add(cls);
        } else {
          classListSet.delete(cls);
        }
      },
    },
    getAttribute: (name) => attrs.get(name) || null,
    setAttribute: (name, val) => attrs.set(name, String(val)),
    removeAttribute: (name) => attrs.delete(name),
    hasAttribute: (name) => attrs.has(name),
    textContent: "",
    title: "",
    children: [],
    appendChild(child) {
      this.children.push(child);
      return child;
    },
  };
}

function createMockDocument() {
  const elementsById = new Map();
  const body = createMockElement("body");

  return {
    body,
    getElementById: (id) => elementsById.get(id) || null,
    createElement: (tag) => {
      const el = createMockElement(tag);
      return el;
    },
    registerElementById: (id, el) => {
      el.id = id;
      elementsById.set(id, el);
    },
    querySelectorAll: () => [],
  };
}

test("Navigation: verifies role capability matrix", () => {
  const nav = createNavigationController();

  // BOMBERO (operador de guardia sin privilegios de gestión de activos o solicitudes)
  assert.equal(nav.canAccessModule("Inventario general", "BOMBERO"), true);
  assert.equal(nav.canAccessModule("Bienes", "BOMBERO"), false);
  assert.equal(nav.canAccessModule("Categorías", "BOMBERO"), false);
  assert.equal(nav.canAccessModule("Nueva categoría", "BOMBERO"), false);
  assert.equal(nav.canAccessModule("Invitaciones", "BOMBERO"), false);
  assert.equal(nav.canAccessModule("Solicitudes", "BOMBERO"), false);
  assert.equal(nav.canAccessModule("Reemisiones", "BOMBERO"), false);
  assert.equal(nav.canAccessModule("Auditoría", "BOMBERO"), false);

  // SUPERVISOR (gestión de inventario, sin gestión de accesos, solicitudes, invitaciones, reemisión ni auditoría)
  assert.equal(nav.canAccessModule("Inventario general", "SUPERVISOR"), true);
  assert.equal(nav.canAccessModule("Bienes", "SUPERVISOR"), true);
  assert.equal(nav.canAccessModule("Categorías", "SUPERVISOR"), true);
  assert.equal(nav.canAccessModule("Nueva categoría", "SUPERVISOR"), true);
  assert.equal(nav.canAccessModule("Ubicaciones", "SUPERVISOR"), true);
  assert.equal(nav.canAccessModule("Invitaciones", "SUPERVISOR"), false);
  assert.equal(nav.canAccessModule("Gestión de accesos", "SUPERVISOR"), false);
  assert.equal(nav.canAccessModule("Solicitudes", "SUPERVISOR"), false);
  assert.equal(nav.canAccessModule("Reemisiones", "SUPERVISOR"), false);
  assert.equal(nav.canAccessModule("Auditoría", "SUPERVISOR"), false);

  // ADMINISTRADOR (acceso total a inventario, gestión de accesos, revisión, reemisión y auditoría)
  assert.equal(nav.canAccessModule("Inventario general", "ADMINISTRADOR"), true);
  assert.equal(nav.canAccessModule("Bienes", "ADMINISTRADOR"), true);
  assert.equal(nav.canAccessModule("Nueva categoría", "ADMINISTRADOR"), true);
  assert.equal(nav.canAccessModule("Invitaciones", "ADMINISTRADOR"), true);
  assert.equal(nav.canAccessModule("Gestión de accesos", "ADMINISTRADOR"), true);
  assert.equal(nav.canAccessModule("Solicitudes", "ADMINISTRADOR"), true);
  assert.equal(nav.canAccessModule("Reemisiones", "ADMINISTRADOR"), true);
  assert.equal(nav.canAccessModule("Auditoría", "ADMINISTRADOR"), true);
});

test("Navigation: updates DOM attributes for active and restricted states", () => {
  const btnOverview = createMockElement("button", {
    dataset: { view: "Inventario general" },
  });
  const btnBienes = createMockElement("button", {
    dataset: { view: "Bienes" },
  });
  const btnAuditoria = createMockElement("button", {
    dataset: { view: "Auditoría" },
  });

  const buttons = [btnOverview, btnBienes, btnAuditoria];

  // Configure controller for a BOMBERO
  const nav = createNavigationController({
    initialRole: "BOMBERO",
    initialView: "Inventario general",
  });

  nav.updateNavElements(buttons);

  // Overview is active and authorized
  assert.equal(btnOverview.getAttribute("aria-current"), "page");
  assert.equal(btnOverview.classList.contains("is-active"), true);
  assert.equal(btnOverview.hasAttribute("aria-disabled"), false);
  assert.equal(btnOverview.classList.contains("is-restricted"), false);

  // Bienes is unauthorized for BOMBERO
  assert.equal(btnBienes.getAttribute("aria-disabled"), "true");
  assert.equal(btnBienes.classList.contains("is-restricted"), true);
  assert.match(btnBienes.title, /restringido/);

  // Auditoria is unauthorized for BOMBERO
  assert.equal(btnAuditoria.getAttribute("aria-disabled"), "true");
  assert.equal(btnAuditoria.classList.contains("is-restricted"), true);

  // Upgrade user role to ADMINISTRADOR
  nav.setRole("ADMINISTRADOR");
  nav.updateNavElements(buttons);

  // All buttons now authorized
  assert.equal(btnBienes.hasAttribute("aria-disabled"), false);
  assert.equal(btnBienes.classList.contains("is-restricted"), false);
  assert.equal(btnAuditoria.hasAttribute("aria-disabled"), false);
  assert.equal(btnAuditoria.classList.contains("is-restricted"), false);
});

test("Navigation: selectView allows authorized navigation and rejects unauthorized", () => {
  const nav = createNavigationController({
    initialRole: "SUPERVISOR",
    initialView: "Inventario general",
  });

  // Navigate to authorized module
  const allowed = nav.selectView("Bienes");
  assert.equal(allowed, true);
  assert.equal(nav.getActiveView(), "Bienes");

  // Attempt navigation to restricted module
  const denied = nav.selectView("Reemisiones");
  assert.equal(denied, false);
  // View should remain at previous authorized selection
  assert.equal(nav.getActiveView(), "Bienes");
});

test("Navigation: announces messages via ARIA live regions", async () => {
  const doc = createMockDocument();
  const politeEl = createMockElement("div", {
    id: "accessible-polite-announcer",
  });
  const assertiveEl = createMockElement("div", {
    id: "accessible-assertive-announcer",
  });
  doc.registerElementById("accessible-polite-announcer", politeEl);
  doc.registerElementById("accessible-assertive-announcer", assertiveEl);

  const nav = createNavigationController({ document: doc });

  nav.announce("Conexión restaurada", "polite");
  // Wait for the internal setTimeout (50ms)
  await new Promise((r) => setTimeout(r, 70));
  assert.equal(politeEl.textContent, "Conexión restaurada");

  nav.announce("Alerta crítica de presión", "assertive");
  await new Promise((r) => setTimeout(r, 70));
  assert.equal(assertiveEl.textContent, "Alerta crítica de presión");
});

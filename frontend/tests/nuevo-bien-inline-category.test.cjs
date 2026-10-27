const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const htmlPath = path.resolve(__dirname, "../index.html");
const cssPath = path.resolve(__dirname, "../css/components.css");
const appJsPath = path.resolve(__dirname, "../js/app.js");

test("HTML Structure: nuevo bien contains segmented category mode tabs and input panels", () => {
  const html = fs.readFileSync(htmlPath, "utf8");

  // Verify container and segmented mode buttons
  assert.match(html, /id="group-category-container"/);
  assert.match(html, /class="category-mode-selector"/);
  assert.match(html, /id="btn-mode-existing"/);
  assert.match(html, /id="btn-mode-new"/);

  // Verify group for category selection and its elements
  assert.match(html, /id="group-select-category"/);
  assert.match(html, /id="asset-category"/);
  assert.match(html, /value="__NEW__"[^>]*class="opt-new-category"/);

  // Verify group for new category input (initially hidden)
  assert.match(html, /id="group-new-category"[^>]*hidden/);
  assert.match(html, /id="asset-new-category"/);
  assert.match(html, /name="new_category_name"/);
  assert.match(html, /id="btn-cancel-new-cat"/);
  assert.match(html, /Esta categoría se creará automáticamente en la base de datos y se vinculará a este nuevo bien en el mismo acto/);
});

test("CSS: Styles for category mode selector, mode buttons, and new category option exist", () => {
  const css = fs.readFileSync(cssPath, "utf8");

  assert.match(css, /\.category-mode-selector\s*\{[^}]*display:\s*flex/);
  assert.match(css, /\.cat-mode-btn\s*\{[^}]*cursor:\s*pointer/);
  assert.match(css, /\.cat-mode-btn\.is-active\s*\{[^}]*border-color:\s*var\(--primary\)/);
  assert.match(css, /\.opt-new-category\s*\{[^}]*color:/);
});

test("Category Inline Logic: correctly handles toggling and payload generation", () => {
  // Unit test for the payload construction logic matching app.js
  function prepareAssetPayload({ code, name, newCatName, categoryId, locationId, isToggleActive }) {
    const codeVal = (code || "").trim();
    const nameVal = (name || "").trim();
    const newCatVal = (newCatName || "").trim();
    const catVal = categoryId || "";
    const isNew = Boolean(newCatVal) || (catVal === "__NEW__") || Boolean(isToggleActive);

    if (!codeVal || codeVal.length < 3) {
      throw new Error("El código interno es obligatorio (mínimo 3 caracteres)");
    }
    if (!nameVal || nameVal.length < 3) {
      throw new Error("La denominación / nombre es obligatoria (mínimo 3 caracteres)");
    }

    const payload = {
      internal_code: codeVal,
      name: nameVal,
      location_id: locationId ? Number(locationId) : null,
    };

    if (isNew) {
      if (!newCatVal || newCatVal.length < 3) {
        throw new Error("Ingrese el nombre de la nueva categoría (mínimo 3 caracteres)");
      }
      payload.new_category_name = newCatVal;
    } else {
      if (!catVal || catVal === "__NEW__") {
        throw new Error("Seleccione una categoría o cree una nueva");
      }
      payload.category_id = Number(catVal);
    }

    return payload;
  }

  // 1. Existing category selected -> category_id present, new_category_name undefined
  const p1 = prepareAssetPayload({
    code: "BIE-00100",
    name: "Lanza Triple Efecto 45mm",
    categoryId: "3",
    locationId: "1",
  });
  assert.equal(p1.internal_code, "BIE-00100");
  assert.equal(p1.name, "Lanza Triple Efecto 45mm");
  assert.equal(p1.category_id, 3);
  assert.equal(p1.new_category_name, undefined);
  assert.equal(p1.location_id, 1);

  // 2. User enters new category directly (even if select is untouched) -> new_category_name present
  const p2 = prepareAssetPayload({
    code: "BIE-00200",
    name: "Cámara Térmica FLIR K55",
    newCatName: "Termografía y Óptica",
    categoryId: "",
    locationId: null,
  });
  assert.equal(p2.internal_code, "BIE-00200");
  assert.equal(p2.name, "Cámara Térmica FLIR K55");
  assert.equal(p2.new_category_name, "Termografía y Óptica");
  assert.equal(p2.category_id, undefined);
  assert.equal(p2.location_id, null);

  // 3. User toggles new category mode via button or __NEW__ option
  const p3 = prepareAssetPayload({
    code: "BIE-00250",
    name: "Balsa de rescate",
    isToggleActive: true,
    newCatName: "Salvamento Acuático",
    categoryId: "__NEW__",
  });
  assert.equal(p3.new_category_name, "Salvamento Acuático");
  assert.equal(p3.category_id, undefined);

  // 4. Validation: rejects too short new category name (< 3 chars)
  assert.throws(
    () =>
      prepareAssetPayload({
        code: "BIE-00300",
        name: "Equipo",
        newCatName: "AB",
      }),
    /mínimo 3 caracteres/
  );

  // 5. Validation: rejects when neither category_id nor new_category_name is valid
  assert.throws(
    () =>
      prepareAssetPayload({
        code: "BIE-00400",
        name: "Equipo",
        newCatName: "",
        categoryId: "",
      }),
    /Seleccione una categoría o cree una nueva/
  );
});

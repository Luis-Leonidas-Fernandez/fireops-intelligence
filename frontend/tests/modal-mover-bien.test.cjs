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

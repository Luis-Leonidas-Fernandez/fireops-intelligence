/**
 * Test suite for Vista de Movimientos in Frontend
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const htmlPath = path.join(__dirname, "../index.html");
const html = fs.readFileSync(htmlPath, "utf-8");

const renderJsPath = path.join(__dirname, "../js/render.js");
const renderJs = fs.readFileSync(renderJsPath, "utf-8");

test("HTML Structure: view-movimientos exists with all required components", () => {
  assert.match(html, /<section[^>]*id="view-movimientos"[^>]*data-view="Movimientos"/, "view-movimientos section must exist");
  assert.match(html, /Historial de Movimientos<\/h2>/, "h2 title must exist");
  assert.match(html, /id="movimientos-search-input"/, "search input must exist");
  assert.match(html, /id="movimientos-count-all"/, "count all badge must exist");
  assert.match(html, /id="movimientos-count-traslados"/, "count traslados badge must exist");
  assert.match(html, /id="movimientos-table-body"/, "table body must exist");
});

test("Render: DashboardRenderer exposes renderMovimientosView and handles movements data", () => {
  assert.match(renderJs, /renderMovimientosView/, "renderMovimientosView must be defined");
  assert.match(renderJs, /setMovimientosQuery/, "setMovimientosQuery must be exposed");
  assert.match(renderJs, /setMovimientosFilter/, "setMovimientosFilter must be exposed");
});

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.resolve(__dirname, '../js/profile.js'), 'utf8',
);

function harness(reply) {
  const nodes = Object.fromEntries(
    ['#profile-name', '#profile-email', '#profile-avatar'].map(key => [key, { textContent: '' }]),
  );
  const location = { path: null, assign(value) { this.path = value; } };
  let request;
  const window = { location };
  const context = {
    window,
    document: { querySelector(selector) { return nodes[selector] || null; } },
    fetch: async (...args) => { request = args; return reply; },
  };
  vm.runInNewContext(source, context);
  return { nodes, location, window, get request() { return request; } };
}

test('authenticated Google name is shown without inserting HTML', async () => {
  const ui = harness({ ok: true, status: 200, json: async () => ({
    email: 'ana@example.test', display_name: '<Ana Pérez>',
  }) });
  await ui.window.DashboardProfile.mount();
  assert.equal(ui.nodes['#profile-name'].textContent, '<Ana Pérez>');
  assert.equal(ui.nodes['#profile-email'].textContent, 'ana@example.test');
  assert.equal(ui.nodes['#profile-avatar'].textContent, 'AP');
  assert.equal(ui.request[0], '/auth/me');
  assert.equal(ui.request[1].credentials, 'same-origin');
});

test('existing account without a name shows its email', async () => {
  const ui = harness({ ok: true, status: 200, json: async () => ({
    email: 'bombero@example.test', display_name: null,
  }) });
  await ui.window.DashboardProfile.mount();
  assert.equal(ui.nodes['#profile-name'].textContent, 'bombero@example.test');
  assert.equal(ui.nodes['#profile-avatar'].textContent, 'BO');
});

test('expired session returns to sign-in', async () => {
  const ui = harness({ ok: false, status: 401 });
  await ui.window.DashboardProfile.mount();
  assert.equal(ui.location.path, '/iniciar-sesion');
});

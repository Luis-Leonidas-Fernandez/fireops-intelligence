const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup(hash = '') {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      hidden: false, disabled: false, value: '', textContent: '', handlers: {},
      addEventListener(type, handler) { this.handlers[type] = handler; },
      querySelector(selector) { return element(selector); },
    });
    return elements.get(id);
  }
  const location = { hash, search: '', pathname: '/registro', path: null, assign(path) { this.path = path; } };
  const requests = [];
  const document = { querySelector(selector) {
    if (selector === '#pending-requests') return null;
    return element(selector);
  } };
  const context = { document, window: { location, history: { replaceState() {} } }, URLSearchParams,
    fetch: async (url, options) => { requests.push([url, options]); return { ok: true }; } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../js/registration-requests.js'), 'utf8'), context);
  return { element, location, requests };
}

test('request screen hides signup until an approved token is present', () => {
  const pending = setup();
  assert.equal(pending.element('#registration-request-panel').hidden, false);
  assert.equal(pending.element('#registration-form').hidden, true);
  const approved = setup('#invite=one-use-token');
  assert.equal(approved.element('#registration-request-panel').hidden, true);
  assert.equal(approved.element('#registration-form').hidden, false);
});

test('request sends only email and Google starts verified OAuth', async () => {
  const ui = setup();
  ui.element('#request-email').value = 'person@example.test';
  await ui.element('#registration-request-form').handlers.submit({ preventDefault() {}, currentTarget: ui.element('#registration-request-form') });
  assert.equal(ui.requests[0][0], '/auth/registration-requests');
  assert.equal(JSON.parse(ui.requests[0][1].body).email, 'person@example.test');
  assert.equal(ui.element('#request-status').hidden, false);
  ui.element('#google-request-button').handlers.click();
  assert.equal(ui.location.path, '/auth/google/start?flow=signin&source=request');
});

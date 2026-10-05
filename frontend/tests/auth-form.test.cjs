const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const frontend = path.resolve(__dirname, '..');

class Element {
  constructor() {
    this.listeners = {};
    this.attributes = {};
    this.dataset = {};
    this.hidden = false;
    this.disabled = false;
    this.textContent = '';
    this.value = '';
  }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this.attributes[name] = value; }
  focus() { this.focused = true; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  querySelector(selector) { return this.children?.[selector] || null; }
}

function harness(mode = 'login', search = '') {
  const form = new Element();
  const button = new Element();
  const label = new Element();
  const loader = new Element();
  const status = new Element();
  const displayName = new Element();
  const email = new Element();
  const password = new Element();
  const repeatPassword = new Element();
  const dialog = new Element();
  const dialogMessage = new Element();
  const closeButton = new Element();
  const googleButton = new Element();
  const errors = Object.fromEntries(['displayName', 'email', 'password', 'repeatPassword'].map((key) => [key, new Element()]));
  button.children = { '.button-label': label, '.particle-loader': loader };
  form.children = {
    '.submit-button': button, '.form-status': status,
    '#display-name': mode === 'register' ? displayName : null,
    '#email': email, '#password': password,
    '#password-repeat': mode === 'register' ? repeatPassword : null,
    ...Object.fromEntries(Object.entries(errors).map(([key, element]) => [`[data-error-for="${key}"]`, element])),
  };
  dialog.children = { '.modal-message': dialogMessage, '.modal-close': closeButton };

  const location = { path: null, search, pathname: mode === 'login' ? '/iniciar-sesion' : '/registro', assign(value) { this.path = value; } };
  let callback;
  let requests = 0;
  let lastRequest;
  let fetchResult = async () => ({ ok: true, json: async () => ({ message: 'Correcto.' }) });
  const window = { location, history: { replaceState(_state, _title, path) { location.cleanedPath = path; } }, setTimeout(fn) { callback = fn; } };
  const document = {
    querySelector(selector) {
      if (selector === '#auth-error-dialog') return dialog;
      if (selector === '.google-button') return googleButton;
      return form;
    },
    querySelectorAll() { return []; },
  };
  const context = { window, document, HTMLInputElement: Element, URLSearchParams,
    fetch: (...args) => { requests += 1; lastRequest = args; return fetchResult(...args); } };
  for (const file of ['js/validations/credentials.js', 'js/auth-form.js']) {
    vm.runInNewContext(fs.readFileSync(path.join(frontend, file), 'utf8'), context);
  }
  window.AuthForm.mount({ formSelector: '#form', endpoint: '/auth/login', mode });
  email.value = 'persona@example.com';
  password.value = 'ClaveSegura123';
  repeatPassword.value = password.value;
  return {
    window, form, button, label, loader, status, displayName, email, password, repeatPassword,
    dialog, dialogMessage, closeButton, googleButton, errors, location,
    get requests() { return requests; },
    get lastRequest() { return lastRequest; },
    respondWith(fn) { fetchResult = fn; },
    redirect() { callback?.(); },
    submit() { return form.listeners.submit({ preventDefault() {} }); },
  };
}

test('invalid email and password show field errors without calling backend', async () => {
  const ui = harness('register');
  ui.email.value = 'invalid';
  ui.password.value = 'abc';
  ui.repeatPassword.value = 'abc';
  await ui.submit();
  assert.match(ui.errors.email.textContent, /correo/);
  assert.match(ui.errors.password.textContent, /8 y 128/);
  assert.equal(ui.requests, 0);
});

test('valid form sends normalized credentials and shows loading while pending', async () => {
  const ui = harness();
  ui.email.value = ' Persona@Example.COM ';
  let resolve;
  ui.respondWith(() => new Promise((done) => { resolve = done; }));
  const pending = ui.submit();
  assert.equal(ui.requests, 1);
  assert.equal(ui.button.disabled, true);
  assert.equal(ui.loader.hidden, false);
  assert.equal(ui.label.hidden, true);
  resolve({ ok: true, json: async () => ({ message: 'Inicio correcto.' }) });
  await pending;
  assert.equal(ui.status.hidden, false);
  assert.equal(ui.status.textContent, 'Inicio correcto.');
  assert.equal(ui.location.path, null);
  ui.redirect();
  assert.equal(ui.location.path, '/');
});

test('server error opens closable modal and never redirects', async () => {
  const ui = harness();
  ui.respondWith(async () => ({ ok: false, json: async () => ({
    error: { code: 'INVALID_CREDENTIALS', message: 'Credenciales incorrectas.' },
  }) }));
  await ui.submit();
  assert.equal(ui.dialog.open, true);
  assert.equal(ui.dialog.dataset.errorCode, 'INVALID_CREDENTIALS');
  assert.equal(ui.dialogMessage.textContent, 'Credenciales incorrectas.');
  assert.equal(ui.location.path, null);
  ui.closeButton.listeners.click();
  assert.equal(ui.dialog.open, false);
});

test('Google button starts server-side OAuth without granting a local session', () => {
  const ui = harness();
  ui.googleButton.listeners.click();
  assert.equal(ui.location.path, '/auth/google/start?flow=signin&source=login');
  assert.equal(ui.googleButton.disabled, true);
  assert.equal(ui.googleButton.attributes['aria-busy'], 'true');
});

test('registration Google button preserves its source', () => {
  const ui = harness('register');
  ui.googleButton.listeners.click();
  assert.equal(ui.location.path, '/auth/google/start?flow=signin&source=register');
});

test('Google callback error is shown in a controlled modal and removed from URL', () => {
  const ui = harness('login', '?auth_error=GOOGLE_LINK_REQUIRED');
  assert.equal(ui.dialog.open, true);
  assert.match(ui.dialogMessage.textContent, /vinculá Google/);
  assert.equal(ui.location.cleanedPath, '/iniciar-sesion');
});

test('valid registration submits and redirects only after success', async () => {
  const ui = harness('register');
  ui.displayName.value = '  Ana   Pérez  ';
  await ui.submit();
  assert.equal(ui.requests, 1);
  assert.equal(JSON.parse(ui.lastRequest[1].body).display_name, 'Ana Pérez');
  assert.equal(ui.status.dataset.state, 'success');
  ui.redirect();
  assert.equal(ui.location.path, '/');
});

test('too long display name prevents registration request', async () => {
  const ui = harness('register');
  ui.displayName.value = 'A'.repeat(121);
  await ui.submit();
  assert.equal(ui.requests, 0);
  assert.match(ui.errors.displayName.textContent, /120/);
});

test('network failure opens an error modal without redirecting', async () => {
  const ui = harness();
  ui.respondWith(async () => { throw new Error('offline'); });
  await ui.submit();
  assert.equal(ui.dialog.dataset.errorCode, 'NETWORK_ERROR');
  assert.equal(ui.location.path, null);
});

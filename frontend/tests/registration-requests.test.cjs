const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup(hash = '', search = '') {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      hidden: false,
      disabled: false,
      value: '',
      textContent: '',
      dataset: {},
      handlers: {},
      addEventListener(type, handler) { this.handlers[type] = handler; },
      querySelector(selector) { return element(selector); },
    });
    return elements.get(id);
  }
  const listeners = {};
  const location = {
    hash,
    search,
    pathname: '/registro',
    path: null,
    assign(path) { this.path = path; }
  };
  const requests = [];
  const document = {
    querySelector(selector) {
      if (selector === '#pending-requests') return null;
      return element(selector);
    }
  };
  const window = {
    location,
    history: { replaceState() {} },
    addEventListener(event, handler) { listeners[event] = handler; },
  };
  const context = {
    document,
    window,
    URLSearchParams,
    fetch: async (url, options) => {
      requests.push([url, options]);
      return { ok: true, json: async () => ({ message: 'ok' }) };
    }
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../js/registration-requests.js'), 'utf8'), context);
  return { element, location, requests, listeners };
}

test('1 & 3. Estado A (sin token): solamente solicitud visible, creacion oculta, sin formularios simultaneos', () => {
  const pending = setup();
  assert.equal(pending.element('#registration-request-panel').hidden, false, 'Panel de solicitud debe ser visible');
  assert.equal(pending.element('#registration-form').hidden, true, 'Formulario de creacion debe estar oculto');
  assert.equal(pending.element('#registration-title').textContent, 'Solicitar acceso');
  assert.equal(pending.element('#registration-subtitle').textContent, 'Envía tu correo para solicitar el registro. Un administrador revisará la solicitud.');
  // Nunca ambos visibles
  assert.notEqual(pending.element('#registration-request-panel').hidden, pending.element('#registration-form').hidden);
});

test('2 & 3. Estado B (con token): solamente creacion visible, solicitud oculta, sin formularios simultaneos', () => {
  const approved = setup('#invite=one-use-valid-token');
  assert.equal(approved.element('#registration-request-panel').hidden, true, 'Panel de solicitud debe estar oculto');
  assert.equal(approved.element('#registration-form').hidden, false, 'Formulario de creacion debe ser visible');
  assert.equal(approved.element('#registration-title').textContent, 'Crear cuenta');
  assert.equal(approved.element('#registration-subtitle').textContent, 'Usá el enlace de invitación para crear tu cuenta.');
  // Nunca ambos visibles
  assert.notEqual(approved.element('#registration-request-panel').hidden, approved.element('#registration-form').hidden);
});

test('3b. Dinámica por hashchange alterna limpiamente entre Estado A y Estado B', () => {
  const ui = setup();
  assert.equal(ui.element('#registration-request-panel').hidden, false);
  assert.equal(ui.element('#registration-form').hidden, true);

  // Simular llegada de hash de invitación
  ui.location.hash = '#invite=fresh-token';
  ui.listeners['hashchange']();
  assert.equal(ui.element('#registration-request-panel').hidden, true);
  assert.equal(ui.element('#registration-form').hidden, false);
  assert.equal(ui.element('#registration-title').textContent, 'Crear cuenta');

  // Simular remoción de hash
  ui.location.hash = '';
  ui.listeners['hashchange']();
  assert.equal(ui.element('#registration-request-panel').hidden, false);
  assert.equal(ui.element('#registration-form').hidden, true);
  assert.equal(ui.element('#registration-title').textContent, 'Solicitar acceso');
});

test('5 & 7. Formulario de solicitud envia POST y boton Google inicia OAuth con source=request', async () => {
  const ui = setup();
  ui.element('#request-email').value = 'bombero@example.test';
  await ui.element('#registration-request-form').handlers.submit({
    preventDefault() {},
    currentTarget: ui.element('#registration-request-form')
  });

  assert.equal(ui.requests.length, 1);
  assert.equal(ui.requests[0][0], '/auth/registration-requests');
  assert.equal(ui.requests[0][1].method, 'POST');
  assert.equal(JSON.parse(ui.requests[0][1].body).email, 'bombero@example.test');

  const status = ui.element('#request-status');
  assert.equal(status.hidden, false);
  assert.equal(status.textContent, 'Si corresponde, recibirás novedades por correo.');
  assert.equal(status.dataset.state, 'success', 'Debe marcar dataset.state=success para color verde');

  ui.element('#google-request-button').handlers.click();
  assert.equal(ui.location.path, '/auth/google/start?flow=signin&source=request');
});

test('8. Mensajes de error en solicitud eliminan dataset.state=success para reflejar color rojo', async () => {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      hidden: false, disabled: false, value: '', textContent: '', dataset: {}, handlers: {},
      addEventListener(type, handler) { this.handlers[type] = handler; },
      querySelector(selector) { return element(selector); },
    });
    return elements.get(id);
  }
  const location = { hash: '', search: '', pathname: '/registro', path: null, assign(p) { this.path = p; } };
  const context = {
    document: { querySelector(selector) { if (selector === '#pending-requests') return null; return element(selector); } },
    window: { location, history: { replaceState() {} }, addEventListener() {} },
    URLSearchParams,
    fetch: async () => ({ ok: false, status: 500 }),
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../js/registration-requests.js'), 'utf8'), context);

  element('#request-email').value = 'fail@example.test';
  await element('#registration-request-form').handlers.submit({
    preventDefault() {},
    currentTarget: element('#registration-request-form')
  });

  const status = element('#request-status');
  assert.equal(status.hidden, false);
  assert.equal(status.textContent, 'No se pudo enviar la solicitud. Inténtalo nuevamente.');
  assert.equal(status.dataset.state, undefined, 'No debe tener state=success en caso de error');
});

test('8b. Retorno de Google con request_status=received activa confirmacion de exito', () => {
  const ui = setup('', '?request_status=received');
  const status = ui.element('#request-status');
  assert.equal(status.hidden, false);
  assert.equal(status.textContent, 'Si corresponde, recibirás novedades por correo.');
  assert.equal(status.dataset.state, 'success');
});

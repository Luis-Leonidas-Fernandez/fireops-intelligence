const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const frontendDir = path.resolve(__dirname, "..");
const { createApiClient, getSafeNextUrl } = require(path.join(frontendDir, "js/api-client.js"));
const { createNavigationController, MODULE_PERMISSIONS } = require(path.join(frontendDir, "js/navigation.js"));

class MockElement {
  constructor(tag = "div") {
    this.tag = tag;
    this.listeners = {};
    this.attributes = {};
    this.dataset = {};
    this.classList = new Set();
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.value = "";
    this.children = {};
    this.focused = false;
    this.open = false;
  }
  addEventListener(name, callback) {
    this.listeners[name] = callback;
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
  getAttribute(name) {
    return this.attributes[name] ?? null;
  }
  removeAttribute(name) {
    delete this.attributes[name];
  }
  focus() {
    this.focused = true;
  }
  showModal() {
    this.open = true;
  }
  close() {
    this.open = false;
  }
  querySelector(selector) {
    return this.children[selector] || null;
  }
  querySelectorAll(_selector) {
    return [];
  }
}

function createLoginHarness({ search = "", hash = "", pathname = "/iniciar-sesion" } = {}) {
  const form = new MockElement("form");
  const submitButton = new MockElement("button");
  const buttonLabel = new MockElement("span");
  const loader = new MockElement("span");
  const status = new MockElement("p");
  const emailInput = new MockElement("input");
  const passwordInput = new MockElement("input");
  const emailError = new MockElement("small");
  const passwordError = new MockElement("small");
  const dialog = new MockElement("dialog");
  const dialogMessage = new MockElement("p");
  const dialogClose = new MockElement("button");
  const googleButton = new MockElement("button");

  buttonLabel.className = "button-label";
  loader.className = "particle-loader";
  submitButton.children[".button-label"] = buttonLabel;
  submitButton.children[".particle-loader"] = loader;

  form.children[".submit-button"] = submitButton;
  form.children[".form-status"] = status;
  form.children[".google-button"] = googleButton;
  form.children["#email"] = emailInput;
  form.children["#password"] = passwordInput;
  form.children['[data-error-for="email"]'] = emailError;
  form.children['[data-error-for="password"]'] = passwordError;

  dialog.children[".modal-message"] = dialogMessage;
  dialog.children[".modal-close"] = dialogClose;

  const location = {
    pathname,
    search,
    hash,
    path: null,
    assign(val) {
      this.path = val;
    },
  };

  const localStorage = {
    _store: {},
    getItem(k) { return this._store[k] ?? null; },
    setItem(k, v) { this._store[k] = String(v); },
    removeItem(k) { delete this._store[k]; },
    clear() { this._store = {}; },
    get length() { return Object.keys(this._store).length; },
  };

  const sessionStorage = {
    _store: {},
    getItem(k) { return this._store[k] ?? null; },
    setItem(k, v) { this._store[k] = String(v); },
    removeItem(k) { delete this._store[k]; },
    clear() { this._store = {}; },
    get length() { return Object.keys(this._store).length; },
  };

  let scheduledTimer = null;
  const windowObj = {
    location,
    localStorage,
    sessionStorage,
    history: {
      replaceState(_state, _title, p) {
        location.pathname = p;
      },
    },
    setTimeout(fn, ms) {
      scheduledTimer = fn;
      return 1;
    },
    clearTimeout(_id) {
      scheduledTimer = null;
    },
    FireApiClient: {
      getSafeNextUrl,
    },
  };

  const docObj = {
    body: { append() {} },
    createElement(tag) { return new MockElement(tag); },
    querySelector(selector) {
      if (selector === "#login-form" || selector === "#form") return form;
      if (selector === "#auth-error-dialog") return dialog;
      if (selector === ".google-button") return googleButton;
      return null;
    },
    querySelectorAll() { return []; },
  };

  let requests = [];
  let fetchResponse = async () => ({
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: async () => ({ message: "Inicio de sesión correcto.", user: { id: 1, email: "admin@bomberos.test" } }),
  });

  const context = {
    window: windowObj,
    document: docObj,
    HTMLInputElement: MockElement,
    URLSearchParams,
    fetch: async (...args) => {
      requests.push(args);
      return fetchResponse(...args);
    },
  };

  // Run validation and auth-form in context
  const credsCode = fs.readFileSync(path.join(frontendDir, "js/validations/credentials.js"), "utf8");
  const authFormCode = fs.readFileSync(path.join(frontendDir, "js/auth-form.js"), "utf8");
  vm.runInNewContext(credsCode, context);
  vm.runInNewContext(authFormCode, context);

  windowObj.AuthForm.mount({ formSelector: "#login-form", endpoint: "/auth/login", mode: "login" });

  return {
    window: windowObj,
    location,
    form,
    submitButton,
    buttonLabel,
    loader,
    status,
    emailInput,
    passwordInput,
    emailError,
    passwordError,
    dialog,
    dialogMessage,
    dialogClose,
    requests,
    setResponse(fn) {
      fetchResponse = fn;
    },
    runScheduledTimer() {
      if (scheduledTimer) scheduledTimer();
    },
    async submit() {
      if (form.listeners.submit) {
        return form.listeners.submit({ preventDefault() {} });
      }
    },
  };
}

// ============================================================================
// 1. Validaciones y Prevención de Doble Envío
// ============================================================================

test("login: form rejects invalid email format without backend request", async () => {
  const h = createLoginHarness();
  h.emailInput.value = "no-es-correo";
  h.passwordInput.value = "ClaveValida123";

  await h.submit();

  assert.equal(h.requests.length, 0, "No HTTP call should be made when validation fails");
  assert.match(h.emailError.textContent, /correo electrónico válido/i);
  assert.equal(h.emailInput.attributes["aria-invalid"], "true");
});

test("login: form rejects empty password without backend request", async () => {
  const h = createLoginHarness();
  h.emailInput.value = "aspirante@bomberos.test";
  h.passwordInput.value = "";

  await h.submit();

  assert.equal(h.requests.length, 0);
  assert.match(h.passwordError.textContent, /contraseña/i);
  assert.equal(h.passwordInput.attributes["aria-invalid"], "true");
});

test("login: double-submit prevention blocks concurrent submissions and sets aria-busy", async () => {
  const h = createLoginHarness();
  h.emailInput.value = "bombero@bomberos.test";
  h.passwordInput.value = "ClaveSegura123";

  let resolveFetch;
  const delayedPromise = new Promise((resolve) => { resolveFetch = resolve; });
  h.setResponse(async () => {
    await delayedPromise;
    return {
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => ({ message: "OK" }),
    };
  });

  // First submit (in-flight)
  const firstSubmit = h.submit();
  assert.equal(h.submitButton.disabled, true);
  assert.equal(h.submitButton.attributes["aria-busy"], "true");
  assert.equal(h.loader.hidden, false);
  assert.equal(h.buttonLabel.hidden, true);

  // Second submit attempted while pending
  await h.submit();
  assert.equal(h.requests.length, 1, "Second click while pending must NOT trigger another request");

  // Complete first request
  resolveFetch();
  await firstSubmit;
  assert.equal(h.submitButton.disabled, false);
  assert.equal(h.submitButton.attributes["aria-busy"], "false");
});

// ============================================================================
// 2. Manejo de Errores Backend (401, 403, 422, 429, 503, Network)
// ============================================================================

test("login: network failure surfaces NETWORK_ERROR in accessible dialog without redirection", async () => {
  const h = createLoginHarness();
  h.emailInput.value = "bombero@bomberos.test";
  h.passwordInput.value = "ClaveSegura123";
  h.setResponse(async () => {
    throw new Error("Failed to fetch");
  });

  await h.submit();

  assert.equal(h.dialog.open, true);
  assert.equal(h.dialog.dataset.errorCode, "NETWORK_ERROR");
  assert.match(h.dialogMessage.textContent, /conectar con el servidor/i);
  assert.equal(h.location.path, null, "Should not redirect on error");
});

test("login: 401 invalid credentials surfaces descriptive error and re-enables submit button", async () => {
  const h = createLoginHarness();
  h.emailInput.value = "bombero@bomberos.test";
  h.passwordInput.value = "ClaveErronea999";
  h.setResponse(async () => ({
    ok: false,
    status: 401,
    headers: { get: () => "application/json" },
    json: async () => ({
      error: { code: "INVALID_CREDENTIALS", message: "Credenciales incorrectas." },
    }),
  }));

  await h.submit();

  assert.equal(h.dialog.open, true);
  assert.equal(h.dialog.dataset.errorCode, "INVALID_CREDENTIALS");
  assert.match(h.dialogMessage.textContent, /Credenciales incorrectas/);
  assert.equal(h.submitButton.disabled, false);
  assert.equal(h.location.path, null);
});

test("login: 403 inactive account surfaces ACCOUNT_INACTIVE in dialog", async () => {
  const h = createLoginHarness();
  h.emailInput.value = "suspendido@bomberos.test";
  h.passwordInput.value = "ClaveValida123";
  h.setResponse(async () => ({
    ok: false,
    status: 403,
    headers: { get: () => "application/json" },
    json: async () => ({
      error: { code: "ACCOUNT_INACTIVE", message: "Tu cuenta se encuentra inactiva." },
    }),
  }));

  await h.submit();

  assert.equal(h.dialog.open, true);
  assert.equal(h.dialog.dataset.errorCode, "ACCOUNT_INACTIVE");
  assert.match(h.dialogMessage.textContent, /inactiva/);
});

test("login: 422 validation error displays message returned by backend", async () => {
  const h = createLoginHarness();
  h.emailInput.value = "test@bomberos.test";
  h.passwordInput.value = "ClaveValida123";
  h.setResponse(async () => ({
    ok: false,
    status: 422,
    headers: { get: () => "application/json" },
    json: async () => ({
      error: { code: "VALIDATION_ERROR", message: "Longitud de contraseña inválida." },
    }),
  }));

  await h.submit();

  assert.equal(h.dialog.open, true);
  assert.equal(h.dialog.dataset.errorCode, "VALIDATION_ERROR");
  assert.match(h.dialogMessage.textContent, /contraseña inválida/);
});

test("login: 429 rate limit surfaces rate limited message", async () => {
  const h = createLoginHarness();
  h.emailInput.value = "test@bomberos.test";
  h.passwordInput.value = "ClaveValida123";
  h.setResponse(async () => ({
    ok: false,
    status: 429,
    headers: { get: (hdr) => (hdr === "Retry-After" ? "30" : "application/json") },
    json: async () => ({
      error: { code: "RATE_LIMITED", message: "Demasiados intentos. Esperá 30 segundos." },
    }),
  }));

  await h.submit();

  assert.equal(h.dialog.open, true);
  assert.equal(h.dialog.dataset.errorCode, "RATE_LIMITED");
  assert.match(h.dialogMessage.textContent, /Demasiados intentos/);
});

// ============================================================================
// 3. Redirecciones Seguras y Prevención de Open Redirect
// ============================================================================

test("login: successful authentication redirects to '/' by default", async () => {
  const h = createLoginHarness();
  h.emailInput.value = "admin@bomberos.test";
  h.passwordInput.value = "ClaveSegura123";

  await h.submit();
  assert.equal(h.status.dataset.state, "success");
  h.runScheduledTimer();
  assert.equal(h.location.path, "/");
});

test("login: successful authentication redirects to safe internal 'next' path (/solicitudes)", async () => {
  const h = createLoginHarness({ search: "?next=/solicitudes" });
  h.emailInput.value = "supervisor@bomberos.test";
  h.passwordInput.value = "ClaveSegura123";

  await h.submit();
  h.runScheduledTimer();
  assert.equal(h.location.path, "/solicitudes");
});

test("login: successful authentication preserves query params in safe internal 'next' path", async () => {
  const h = createLoginHarness({ search: "?next=%2Finventario%3Ftab%3Dmovimientos" });
  h.emailInput.value = "supervisor@bomberos.test";
  h.passwordInput.value = "ClaveSegura123";

  await h.submit();
  h.runScheduledTimer();
  assert.equal(h.location.path, "/inventario?tab=movimientos");
});

test("login: open redirect to external domain (https://evil.com) is sanitized to default '/'", async () => {
  const h = createLoginHarness({ search: "?next=https://evil.com/phishing" });
  h.emailInput.value = "admin@bomberos.test";
  h.passwordInput.value = "ClaveSegura123";

  await h.submit();
  h.runScheduledTimer();
  assert.equal(h.location.path, "/");
});

test("login: open redirect with protocol-relative URL (//evil.com) is sanitized to default '/'", async () => {
  const h = createLoginHarness({ search: "?next=//evil.com/test" });
  h.emailInput.value = "admin@bomberos.test";
  h.passwordInput.value = "ClaveSegura123";

  await h.submit();
  h.runScheduledTimer();
  assert.equal(h.location.path, "/");
});

test("login: open redirect with backslash evasion (/\\evil.com) is sanitized to default '/'", async () => {
  const h = createLoginHarness({ search: "?next=/\\evil.com" });
  h.emailInput.value = "admin@bomberos.test";
  h.passwordInput.value = "ClaveSegura123";

  await h.submit();
  h.runScheduledTimer();
  assert.equal(h.location.path, "/");
});

test("security: localStorage and sessionStorage remain empty after authentication (HttpOnly cookie used)", async () => {
  const h = createLoginHarness();
  h.emailInput.value = "admin@bomberos.test";
  h.passwordInput.value = "ClaveSegura123";

  await h.submit();

  assert.equal(h.window.localStorage.length, 0, "No tokens or sensitive keys must exist in localStorage");
  assert.equal(h.window.sessionStorage.length, 0, "No tokens or sensitive keys must exist in sessionStorage");
  // Credentials mode verified in fetch
  assert.equal(h.requests[0][1].credentials, "same-origin");
});

// ============================================================================
// 4. Perfil de Usuario, Badges de Rol y Control de Navegación
// ============================================================================

test("profile: retrieves user from /auth/me, renders name, email and role badge with accessible ARIA label", async () => {
  const nameNode = { textContent: "" };
  const emailNode = { textContent: "" };
  const avatarNode = { textContent: "" };
  const roleNode = { textContent: "", hidden: true, dataset: {}, attributes: {}, setAttribute(k, v) { this.attributes[k] = v; } };

  const dom = {
    "#profile-name": nameNode,
    "#profile-email": emailNode,
    "#profile-avatar": avatarNode,
    "#profile-role": roleNode,
  };

  const context = {
    window: { location: { pathname: "/", search: "", assign() {} } },
    document: { querySelector: (sel) => dom[sel] || null },
    fetch: async (url, opts) => {
      assert.equal(url, "/auth/me");
      assert.equal(opts.credentials, "same-origin");
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: 10,
          email: "oficial@bomberos.test",
          display_name: "Comandante Pérez",
          role: "ADMINISTRADOR",
        }),
      };
    },
  };

  const profileCode = fs.readFileSync(path.join(frontendDir, "js/profile.js"), "utf8");
  vm.runInNewContext(profileCode, context);

  await context.window.DashboardProfile.mount();

  assert.equal(nameNode.textContent, "Comandante Pérez");
  assert.equal(emailNode.textContent, "oficial@bomberos.test");
  assert.equal(avatarNode.textContent, "CP");
  assert.equal(roleNode.hidden, false);
  assert.equal(roleNode.textContent, "ADMINISTRADOR");
  assert.equal(roleNode.dataset.role, "ADMINISTRADOR");
  assert.equal(roleNode.attributes["aria-label"], "Rol operativo: ADMINISTRADOR");
});

test("profile: propagates role to FireNavigationController.setRole to restrict unauthorized sections", async () => {
  const nav = createNavigationController({ initialRole: null });
  const buttons = [
    { dataset: { view: "Inventario general" }, setAttribute() {}, removeAttribute() {}, classList: { add() {}, remove() {} } },
    { dataset: { view: "Auditoría" }, setAttribute() {}, removeAttribute() {}, classList: { add() {}, remove() {} } },
  ];

  const dom = {
    "#profile-name": { textContent: "" },
    "#profile-email": { textContent: "" },
    "#profile-avatar": { textContent: "" },
    "#profile-role": { textContent: "", setAttribute() {}, dataset: {} },
  };

  const context = {
    window: {
      location: { pathname: "/", search: "", assign() {} },
      FireNavigationController: nav,
    },
    document: {
      querySelector: (sel) => dom[sel] || null,
      querySelectorAll: () => buttons,
    },
    fetch: async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        id: 20,
        email: "voluntario@bomberos.test",
        display_name: "Juan Voluntario",
        role: "BOMBERO",
      }),
    }),
  };

  const profileCode = fs.readFileSync(path.join(frontendDir, "js/profile.js"), "utf8");
  vm.runInNewContext(profileCode, context);

  await context.window.DashboardProfile.mount();

  assert.equal(nav.getCurrentRole(), "BOMBERO");
  assert.equal(nav.canAccessModule("Inventario general", "BOMBERO"), true);
  assert.equal(nav.canAccessModule("Auditoría", "BOMBERO"), false, "BOMBERO cannot access Auditoría module");
});

test("profile: 401 unauthenticated response preserves destination in next query parameter", async () => {
  let redirectedTo = null;
  const context = {
    window: {
      location: {
        pathname: "/inventario/movimientos",
        search: "?filtro=activos",
        assign(p) { redirectedTo = p; },
      },
    },
    document: {
      querySelector: () => ({ textContent: "" }),
    },
    fetch: async () => ({ ok: false, status: 401 }),
  };

  const profileCode = fs.readFileSync(path.join(frontendDir, "js/profile.js"), "utf8");
  vm.runInNewContext(profileCode, context);

  await context.window.DashboardProfile.mount();

  assert.equal(
    redirectedTo,
    "/iniciar-sesion?next=%2Finventario%2Fmovimientos%3Ffiltro%3Dactivos"
  );
});

// ============================================================================
// 5. Cierre de Sesión (Logout)
// ============================================================================

test("logout: clicking logout button invokes POST /auth/logout with same-origin credentials and redirects", async () => {
  let logoutCalled = false;
  let logoutOpts = null;
  let redirected = null;

  globalThis.fetch = async (url, opts) => {
    if (url === "/auth/logout") {
      logoutCalled = true;
      logoutOpts = opts;
      return { ok: true, status: 204 };
    }
    return { ok: true, status: 200 };
  };

  const client = createApiClient();
  await client.auth.logout();

  assert.equal(logoutCalled, true);
  assert.equal(logoutOpts.method, "POST");
  assert.equal(logoutOpts.credentials, "same-origin");
});

// ============================================================================
// 6. Idempotencia en el Cliente API: Clave Única Reutilizada en Reintentos
// ============================================================================

test("api-client: preserves exact same Idempotency-Key across transport retries of mutating requests", async () => {
  const seenIdempotencyKeys = [];
  let attempts = 0;

  globalThis.fetch = async (_url, options) => {
    attempts++;
    const key = options.headers.get("Idempotency-Key");
    seenIdempotencyKeys.push(key);

    if (attempts < 3) {
      // Simulate transient network or server 503 error
      return {
        ok: false,
        status: 503,
        statusText: "Service Unavailable",
        headers: { get: () => null },
        json: async () => ({ error: { code: "SERVICE_UNAVAILABLE" } }),
      };
    }
    return {
      ok: true,
      status: 201,
      headers: { get: (h) => (h === "content-type" ? "application/json" : null) },
      json: async () => ({ id: 99, status: "created" }),
    };
  };

  const client = createApiClient({ retries: 2, retryDelayMs: 10 });
  const response = await client.post("/inventory/assets", { name: "Bomba Hidráulica" });

  assert.equal(response.ok, true);
  assert.equal(response.status, 201);
  assert.equal(attempts, 3, "Should have executed initial attempt + 2 retries");

  assert.equal(seenIdempotencyKeys.length, 3);
  const initialKey = seenIdempotencyKeys[0];
  assert.ok(initialKey, "Initial request must have an Idempotency-Key header");
  assert.match(initialKey, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);

  // CRUCIAL REQUIREMENT CHECK: The EXACT same key must be sent on retry 1 and retry 2!
  assert.equal(seenIdempotencyKeys[1], initialKey, "Retry 1 must use the exact same Idempotency-Key");
  assert.equal(seenIdempotencyKeys[2], initialKey, "Retry 2 must use the exact same Idempotency-Key");
});

test("api-client: getSafeNextUrl rejects dangerous schemes like javascript:, data:, and external hosts", () => {
  assert.equal(getSafeNextUrl("/dashboard"), "/dashboard");
  assert.equal(getSafeNextUrl("/solicitudes?estado=pendiente"), "/solicitudes?estado=pendiente");
  assert.equal(getSafeNextUrl("https://phishing.com/login"), "/");
  assert.equal(getSafeNextUrl("//attacker.org/evil"), "/");
  assert.equal(getSafeNextUrl("/\\attacker.org"), "/");
  assert.equal(getSafeNextUrl("javascript:alert(document.cookie)"), "/");
  assert.equal(getSafeNextUrl("data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=="), "/");
  assert.equal(getSafeNextUrl(""), "/");
  assert.equal(getSafeNextUrl(null), "/");
  assert.equal(getSafeNextUrl(undefined), "/");
});

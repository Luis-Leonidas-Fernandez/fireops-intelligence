const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const { createApiClient, ApiError, generateUuidV4 } = require(
  path.resolve(__dirname, "../js/api-client.js")
);

// Mock factory for fetch responses
function createMockResponse({
  ok = true,
  status = 200,
  statusText = "OK",
  json = async () => ({}),
  text = async () => "",
  headers = {},
}) {
  const headerMap = new Map(Object.entries(headers));
  return {
    ok,
    status,
    statusText,
    headers: {
      get: (key) => headerMap.get(key.toLowerCase()) || headerMap.get(key) || null,
      has: (key) => headerMap.has(key.toLowerCase()) || headerMap.has(key),
    },
    json,
    text,
  };
}

test("API Client: sends GET request with same-origin credentials and parses JSON", async () => {
  let capturedUrl = null;
  let capturedOptions = null;

  globalThis.fetch = async (url, options) => {
    capturedUrl = url;
    capturedOptions = options;
    return createMockResponse({
      status: 200,
      headers: { "content-type": "application/json" },
      json: async () => [{ id: 1, name: "Casco F1" }],
    });
  };

  const client = createApiClient({ baseUrl: "http://localhost:8000" });
  const result = await client.inventory.listAssets();

  assert.equal(result.ok, true);
  assert.equal(result.status, 200);
  assert.equal(result.data.length, 1);
  assert.equal(result.data[0].name, "Casco F1");
  assert.equal(capturedUrl, "http://localhost:8000/inventory/assets/");
  assert.equal(capturedOptions.method, "GET");
  assert.equal(capturedOptions.credentials, "same-origin");
  assert.equal(capturedOptions.headers.get("Accept"), "application/json");
});

test("API Client: auto-generates Idempotency-Key UUIDv4 on POST mutations", async () => {
  let capturedHeaders = null;

  globalThis.fetch = async (_url, options) => {
    capturedHeaders = options.headers;
    return createMockResponse({
      status: 201,
      headers: { "content-type": "application/json" },
      json: async () => ({ id: 42, internal_code: "E-01", name: "Extintor 10kg" }),
    });
  };

  const client = createApiClient();
  const res = await client.post("/inventory/assets", {
    internal_code: "E-01",
    name: "Extintor 10kg",
  });

  assert.equal(res.ok, true);
  assert.equal(res.status, 201);
  const idemKey = capturedHeaders.get("Idempotency-Key");
  assert.ok(idemKey, "Idempotency-Key should be present");
  assert.match(
    idemKey,
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    "Should match UUIDv4 pattern"
  );
});

test("API Client: respects custom Idempotency-Key on invitations.reissue", async () => {
  let capturedHeaders = null;
  let capturedBody = null;

  globalThis.fetch = async (_url, options) => {
    capturedHeaders = options.headers;
    capturedBody = JSON.parse(options.body);
    return createMockResponse({
      status: 200,
      headers: { "content-type": "application/json" },
      json: async () => ({
        message: "Invitación reemitida exitosamente.",
        request_id: 10,
        invitation_id: 88,
        reissue_count: 1,
        idempotent_replay: false,
      }),
    });
  };

  const client = createApiClient();
  const customKey = "admin-reissue-custom-12345";
  const res = await client.invitations.reissue(10, {
    idempotencyKey: customKey,
    reason: "Pérdida de acceso",
  });

  assert.equal(res.ok, true);
  assert.equal(capturedHeaders.get("Idempotency-Key"), customKey);
  assert.equal(capturedBody.reason, "Pérdida de acceso");
  assert.equal(res.data.reissue_count, 1);
});

test("API Client: handles 401 Unauthorized with onUnauthorized hook and structured ApiError", async () => {
  let hookCalled = false;
  let hookError = null;

  globalThis.fetch = async () =>
    createMockResponse({
      ok: false,
      status: 401,
      headers: { "content-type": "application/json" },
      json: async () => ({
        error: {
          code: "AUTH_REQUIRED",
          message: "Iniciá sesión para usar el inventario.",
          details: {},
        },
      }),
    });

  const client = createApiClient({
    onUnauthorized: (err) => {
      hookCalled = true;
      hookError = err;
    },
  });

  await assert.rejects(
    async () => {
      await client.inventory.listAssets();
    },
    (err) => {
      assert.ok(err instanceof ApiError);
      assert.equal(err.status, 401);
      assert.equal(err.code, "AUTH_REQUIRED");
      assert.equal(err.message, "Iniciá sesión para usar el inventario.");
      return true;
    }
  );

  assert.equal(hookCalled, true);
  assert.equal(hookError.code, "AUTH_REQUIRED");
});

test("API Client: handles 403 Forbidden with onForbidden hook", async () => {
  let forbiddenCalled = false;

  globalThis.fetch = async () =>
    createMockResponse({
      ok: false,
      status: 403,
      headers: { "content-type": "application/json" },
      json: async () => ({
        error: {
          code: "INVENTORY_ACCESS_DENIED",
          message: "Tu cuenta no tiene permiso para usar el inventario.",
          details: {},
        },
      }),
    });

  const client = createApiClient({
    onForbidden: (err) => {
      forbiddenCalled = true;
      assert.equal(err.code, "INVENTORY_ACCESS_DENIED");
    },
  });

  await assert.rejects(async () => {
    await client.inventory.createCategory("Equipos");
  }, ApiError);

  assert.equal(forbiddenCalled, true);
});

test("API Client: handles 422 Unprocessable Entity extracting validation details", async () => {
  let validationCalled = false;

  globalThis.fetch = async () =>
    createMockResponse({
      ok: false,
      status: 422,
      headers: { "content-type": "application/json" },
      json: async () => ({
        error: {
          code: "VALIDATION_ERROR",
          message: "Revisá los datos ingresados.",
          details: {
            fields: [{ field: "email", message: "Formato de correo no válido" }],
          },
        },
      }),
    });

  const client = createApiClient({
    onValidationError: (err) => {
      validationCalled = true;
      assert.equal(err.details.fields[0].field, "email");
    },
  });

  await assert.rejects(
    async () => {
      await client.auth.login("invalid-email", "secret");
    },
    (err) => {
      assert.equal(err.status, 422);
      assert.equal(err.code, "VALIDATION_ERROR");
      assert.equal(err.details.fields.length, 1);
      return true;
    }
  );

  assert.equal(validationCalled, true);
});

test("API Client: handles 429 Too Many Requests parsing Retry-After header", async () => {
  let rateLimitCalled = false;
  let receivedRetryAfter = null;

  globalThis.fetch = async () =>
    createMockResponse({
      ok: false,
      status: 429,
      headers: {
        "content-type": "application/json",
        "retry-after": "45",
      },
      json: async () => ({
        error: {
          code: "TOO_MANY_REQUESTS",
          message: "Demasiadas solicitudes. Por favor, intentá nuevamente.",
          details: {},
        },
      }),
    });

  const client = createApiClient({
    onRateLimited: (_err, retryAfter) => {
      rateLimitCalled = true;
      receivedRetryAfter = retryAfter;
    },
  });

  await assert.rejects(
    async () => {
      await client.invitations.submitRequest("user@test.org");
    },
    (err) => {
      assert.equal(err.status, 429);
      assert.equal(err.retryAfter, 45);
      return true;
    }
  );

  assert.equal(rateLimitCalled, true);
  assert.equal(receivedRetryAfter, 45);
});

test("API Client: handles 503 Service Unavailable", async () => {
  let unavailableCalled = false;

  globalThis.fetch = async () =>
    createMockResponse({
      ok: false,
      status: 503,
      headers: {
        "content-type": "application/json",
        "retry-after": "5",
      },
      json: async () => ({
        error: {
          code: "RATE_LIMIT_STORAGE_UNAVAILABLE",
          message: "Servicio de control de tráfico temporalmente no disponible.",
          details: {},
        },
      }),
    });

  const client = createApiClient({
    onServiceUnavailable: (err) => {
      unavailableCalled = true;
      assert.equal(err.code, "RATE_LIMIT_STORAGE_UNAVAILABLE");
    },
  });

  await assert.rejects(async () => {
    await client.system.ready();
  }, ApiError);

  assert.equal(unavailableCalled, true);
});

test("API Client: AbortController handles timeout cancellation cleanly", async () => {
  globalThis.fetch = async (_url, options) => {
    return new Promise((_resolve, reject) => {
      if (options.signal) {
        options.signal.addEventListener("abort", () => {
          const abortError = new Error("This operation was aborted");
          abortError.name = "AbortError";
          reject(abortError);
        });
      }
    });
  };

  const client = createApiClient({ timeoutMs: 30 });

  await assert.rejects(
    async () => {
      await client.get("/health");
    },
    (err) => {
      assert.ok(err instanceof ApiError);
      assert.equal(err.isTimeout, true);
      assert.equal(err.code, "TIMEOUT");
      assert.match(err.message, /tiempo límite/);
      return true;
    }
  );
});

test("generateUuidV4 returns valid RFC4122 v4 UUID format", () => {
  const uuid = generateUuidV4();
  assert.match(
    uuid,
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
  );
});

test("API Client: invitations.listInvitations sends GET /auth/invitations", async () => {
  let capturedUrl = null;
  let capturedOptions = null;

  globalThis.fetch = async (url, options) => {
    capturedUrl = url;
    capturedOptions = options;
    return createMockResponse({
      status: 200,
      headers: { "content-type": "application/json" },
      json: async () => [
        {
          id: 7,
          email: "bombero@cuartel.gob.ar",
          role: "SUPERVISOR",
          created_at: "2026-10-28T10:00:00Z",
          expires_at: "2026-10-30T10:00:00Z",
          used_at: null,
          status: "active",
          registration_request_id: 3,
          reissue_count: 0,
          can_reissue: false,
        },
      ],
    });
  };

  const client = createApiClient({ baseUrl: "http://localhost:8000" });
  const res = await client.invitations.listInvitations();

  assert.equal(res.ok, true);
  assert.equal(capturedUrl, "http://localhost:8000/auth/invitations");
  assert.equal(capturedOptions.method, "GET");
  assert.equal(capturedOptions.credentials, "same-origin");
  assert.equal(res.data.length, 1);
  assert.equal(res.data[0].email, "bombero@cuartel.gob.ar");
  assert.equal(res.data[0].can_reissue, false);
});

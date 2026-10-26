/**
 * Fire Control API Client
 * Enterprise-grade, typed, and secure HTTP client for FireOps-Intelligence.
 *
 * Capabilities:
 * - Same-origin and configurable base URL
 * - Credentials included automatically (fire_control_access HttpOnly cookie)
 * - Automatic UUIDv4 Idempotency-Key header for state-mutating requests
 * - Bounded timeouts with clean AbortController cancellation
 * - Canonical error deserialization: { error: { code, message, details } }
 * - Specific lifecycle handlers for 401, 403, 422, 429 (Retry-After), 503
 * - Domain-scoped methods for Auth, Invitations, Inventory, and Health Probes
 */

(function (root, factory) {
  if (typeof module === "object" && typeof module.exports === "object") {
    module.exports = factory();
  } else {
    root.FireApiClient = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  /**
   * Generates a cryptographically secure or pseudo-random UUIDv4.
   * @returns {string}
   */
  function generateUuidV4() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      bytes[6] = (bytes[6] & 0x0f) | 0x40; // Version 4
      bytes[8] = (bytes[8] & 0x3f) | 0x80; // Variant RFC4122
      const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  /**
   * Validates and sanitizes a redirection URL to prevent Open Redirect vulnerabilities.
   * Only allows safe relative paths within the same origin.
   * Rejects external protocols, protocol-relative URLs (//), and backslash tricks.
   *
   * @param {string|null|undefined} rawUrl
   * @param {string} defaultUrl
   * @returns {string}
   */
  function getSafeNextUrl(rawUrl, defaultUrl = "/") {
    if (typeof rawUrl !== "string" || !rawUrl.trim()) {
      return defaultUrl;
    }
    const trimmed = rawUrl.trim();
    // Must start with exactly one "/" and NOT followed by "/" or "\"
    if (!trimmed.startsWith("/") || trimmed.startsWith("//") || trimmed.startsWith("/\\")) {
      return defaultUrl;
    }
    // Disallow backslashes and null bytes entirely
    if (trimmed.includes("\\") || trimmed.includes("\0")) {
      return defaultUrl;
    }
    try {
      const parsed = new URL(trimmed, "http://fire-control.local");
      if (parsed.origin !== "http://fire-control.local") {
        return defaultUrl;
      }
      return parsed.pathname + parsed.search + parsed.hash;
    } catch (_e) {
      return defaultUrl;
    }
  }

  /**
   * Structured API Error wrapping FastAPI ApplicationError and Starlette HTTP exceptions.
   */
  class ApiError extends Error {
    constructor({
      message = "Ocurrió un error en la solicitud.",
      code = "UNKNOWN_ERROR",
      status = 0,
      details = {},
      retryAfter = null,
      isTimeout = false,
      url = "",
    } = {}) {
      super(message);
      this.name = "ApiError";
      this.code = code;
      this.status = status;
      this.details = details;
      this.retryAfter = retryAfter;
      this.isTimeout = isTimeout;
      this.url = url;
    }
  }

  /**
   * Creates an instance of the Fire Control API Client.
   * @param {Object} config
   */
  function createApiClient(config = {}) {
    const defaultBaseUrl =
      typeof window !== "undefined" && window.location ? window.location.origin : "";
    const baseUrl = (config.baseUrl !== undefined ? config.baseUrl : defaultBaseUrl).replace(
      /\/+$/,
      ""
    );
    const defaultTimeoutMs = config.timeoutMs || 10000;
    const defaultCredentials = config.credentials || "same-origin";

    // Lifecycle handlers
    const onUnauthorized =
      config.onUnauthorized ||
      function (error) {
        if (typeof window !== "undefined" && window.location) {
          const current = window.location.pathname + window.location.search;
          if (!window.location.pathname.startsWith("/iniciar-sesion")) {
            const next = encodeURIComponent(current);
            window.location.assign(`/iniciar-sesion?next=${next}`);
          }
        }
      };

    const onForbidden = config.onForbidden || function () {};
    const onValidationError = config.onValidationError || function () {};
    const onRateLimited = config.onRateLimited || function () {};
    const onServiceUnavailable = config.onServiceUnavailable || function () {};

    /**
     * Internal generic fetch execution wrapper with transport retry support.
     */
    async function request(path, options = {}) {
      const method = (options.method || "GET").toUpperCase();
      const headers = new Headers(options.headers || {});
      const url = `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
      const timeoutMs = options.timeoutMs !== undefined ? options.timeoutMs : defaultTimeoutMs;
      const credentials = options.credentials || defaultCredentials;
      const maxRetries = options.retries !== undefined ? options.retries : (config.retries || 0);
      const retryDelayMs = options.retryDelayMs !== undefined ? options.retryDelayMs : (config.retryDelayMs || 50);

      if (!headers.has("Accept")) {
        headers.set("Accept", "application/json");
      }

      // Serialize body if object
      let body = options.body;
      if (body !== undefined && body !== null && typeof body === "object" && !(body instanceof FormData)) {
        if (!headers.has("Content-Type")) {
          headers.set("Content-Type", "application/json");
        }
        body = JSON.stringify(body);
      }

      // Automatic Idempotency-Key injection for mutating operations (generated ONCE per logical user action)
      const isMutation = ["POST", "PATCH", "PUT"].includes(method);
      if (isMutation) {
        if (options.idempotencyKey) {
          headers.set("Idempotency-Key", options.idempotencyKey);
        } else if (options.autoIdempotency !== false && !headers.has("Idempotency-Key")) {
          // If the caller provided a key in body or options, respect it; otherwise auto-generate ONCE
          headers.set("Idempotency-Key", generateUuidV4());
        }
      }

      let attempt = 0;
      while (true) {
        // AbortController setup per attempt
        const controller = new AbortController();
        let timeoutId = null;
        if (timeoutMs > 0) {
          timeoutId = setTimeout(() => {
            controller.abort();
          }, timeoutMs);
        }

        // Chain caller's signal if present
        if (options.signal) {
          options.signal.addEventListener("abort", () => controller.abort());
        }

        try {
          const response = await fetch(url, {
            method,
            headers,
            body,
            credentials,
            signal: controller.signal,
          });

          // Parse retry-after if present
          let retryAfter = null;
          const retryHeader = response.headers ? response.headers.get("Retry-After") : null;
          if (retryHeader) {
            const parsed = parseInt(retryHeader, 10);
            if (!isNaN(parsed)) {
              retryAfter = parsed;
            }
          }

          // Check if retryable server error (503) and attempts remain
          if (response.status === 503 && attempt < maxRetries) {
            attempt++;
            if (timeoutId !== null) clearTimeout(timeoutId);
            const delay = retryAfter ? retryAfter * 1000 : retryDelayMs * Math.pow(2, attempt - 1);
            await new Promise((resolve) => setTimeout(resolve, delay));
            continue;
          }

          if (response.status === 204) {
            return { ok: true, status: 204, data: null, headers: response.headers };
          }

          // Attempt JSON parse
          let responseData = null;
          const contentType = response.headers ? response.headers.get("content-type") || "" : "";
          if (contentType.includes("application/json")) {
            try {
              responseData = await response.json();
            } catch (_e) {
              responseData = null;
            }
          } else {
            try {
              responseData = await response.text();
            } catch (_e) {
              responseData = null;
            }
          }

          if (!response.ok) {
            let code = `HTTP_${response.status}`;
            let message = response.statusText || "Error en la petición";
            let details = {};

            if (responseData && typeof responseData === "object" && responseData.error) {
              code = responseData.error.code || code;
              message = responseData.error.message || message;
              details = responseData.error.details || details;
            } else if (responseData && typeof responseData === "object" && responseData.detail) {
              message = typeof responseData.detail === "string" ? responseData.detail : message;
              details = responseData;
            }

            const apiError = new ApiError({
              message,
              code,
              status: response.status,
              details,
              retryAfter,
              url,
            });

            // Trigger appropriate lifecycle hooks
            if (response.status === 401) {
              onUnauthorized(apiError, { url, method });
            } else if (response.status === 403) {
              onForbidden(apiError, { url, method });
            } else if (response.status === 422) {
              onValidationError(apiError, { url, method });
            } else if (response.status === 429) {
              onRateLimited(apiError, retryAfter, { url, method });
            } else if (response.status === 503) {
              onServiceUnavailable(apiError, { url, method });
            }

            throw apiError;
          }

          return {
            ok: true,
            status: response.status,
            data: responseData,
            headers: response.headers,
          };
        } catch (err) {
          if (timeoutId !== null) {
            clearTimeout(timeoutId);
          }
          if (err instanceof ApiError) {
            throw err;
          }

          const isAbort = err.name === "AbortError" || controller.signal.aborted;
          if (attempt < maxRetries) {
            attempt++;
            const delay = retryDelayMs * Math.pow(2, attempt - 1);
            await new Promise((resolve) => setTimeout(resolve, delay));
            continue;
          }

          const fallbackError = new ApiError({
            message: isAbort
              ? `La solicitud excedió el tiempo límite de ${timeoutMs}ms.`
              : err.message || "Error de red o conexión no disponible.",
            code: isAbort ? "TIMEOUT" : "NETWORK_ERROR",
            status: 0,
            isTimeout: isAbort,
            url,
          });

          if (isAbort) {
            onServiceUnavailable(fallbackError, { url, method });
          }
          throw fallbackError;
        } finally {
          if (timeoutId !== null) {
            clearTimeout(timeoutId);
          }
        }
      }
    }

    // HTTP method shortcuts
    const get = (path, options = {}) => request(path, { ...options, method: "GET" });
    const post = (path, body, options = {}) => request(path, { ...options, method: "POST", body });
    const patch = (path, body, options = {}) => request(path, { ...options, method: "PATCH", body });
    const del = (path, options = {}) => request(path, { ...options, method: "DELETE" });

    // Domain Services
    const auth = {
      login: (email, password) =>
        post("/auth/login", { email, password }, { autoIdempotency: false }),
      register: (payload) => post("/auth/register", payload, { autoIdempotency: false }),
      logout: () => post("/auth/logout", null, { autoIdempotency: false }),
      me: () => get("/auth/me"),
    };

    const invitations = {
      submitRequest: (email) => post("/auth/registration-requests", { email }),
      listRequests: () => get("/auth/registration-requests"),
      review: (requestId, decision) =>
        post(`/auth/registration-requests/${requestId}/review`, { decision }),
      reissue: (requestId, { idempotencyKey, reason } = {}) =>
        post(
          `/auth/registration-requests/${requestId}/reissue`,
          { reason },
          { idempotencyKey: idempotencyKey || generateUuidV4() }
        ),
    };

    const inventory = {
      listAssets: () => get("/inventory/assets/"),
      getAsset: (assetId) => get(`/inventory/assets/${assetId}`),
      registerAsset: (payload) => post("/inventory/assets", payload),
      updateAsset: (assetId, payload) => patch(`/inventory/assets/${assetId}`, payload),
      transferAsset: (assetId, payload) =>
        post(`/inventory/assets/${assetId}/transfers`, payload),
      listTransfers: (assetId) => get(`/inventory/assets/${assetId}/transfers`),
      listCategories: () => get("/inventory/categories"),
      createCategory: (name) => post("/inventory/categories", { name }),
      listLocations: () => get("/inventory/locations"),
      createLocation: (payload) => post("/inventory/locations", payload),
      getLocation: (locationId) => get(`/inventory/locations/${locationId}`),
    };

    const system = {
      health: () => get("/health"),
      ready: () => get("/health/ready"),
    };

    return Object.freeze({
      baseUrl,
      request,
      get,
      post,
      patch,
      delete: del,
      auth,
      invitations,
      inventory,
      system,
      generateUuidV4,
      getSafeNextUrl,
    });
  }

  return Object.freeze({
    createApiClient,
    ApiError,
    generateUuidV4,
    getSafeNextUrl,
  });
});

(() => {
  "use strict";

  function mount({ formSelector, endpoint, mode }) {
    const form = document.querySelector(formSelector);
    if (!form) return;

    const submitButton = form.querySelector(".submit-button");
    const buttonLabel = submitButton.querySelector(".button-label");
    const loader = submitButton.querySelector(".particle-loader");
    const status = form.querySelector(".form-status");
    const dialog = document.querySelector("#auth-error-dialog");
    const dialogMessage = dialog.querySelector(".modal-message");
    const fields = {
      displayName: form.querySelector("#display-name"),
      email: form.querySelector("#email"),
      password: form.querySelector("#password"),
      repeatPassword: form.querySelector("#password-repeat"),
    };
    let pending = false;
    const googleErrors = {
      GOOGLE_NOT_CONFIGURED: "El acceso con Google no está configurado en este entorno.",
      GOOGLE_SESSION_EXPIRED: "La autorización con Google venció o no es válida. Intentá nuevamente.",
      GOOGLE_ACCESS_DENIED: "Se canceló el acceso con Google.",
      GOOGLE_AUTH_FAILED: "No pudimos verificar tu cuenta de Google. Intentá nuevamente.",
      GOOGLE_LINK_REQUIRED: "Ese correo ya tiene una cuenta. Iniciá sesión con contraseña y vinculá Google desde tu perfil.",
      GOOGLE_LOGIN_REQUIRED: "Iniciá sesión antes de vincular Google.",
      GOOGLE_ACCOUNT_CONFLICT: "Esta cuenta de Google ya está asociada o existe un conflicto. Contactá al administrador.",
      GOOGLE_EMAIL_MISMATCH: "El correo de Google debe coincidir con el correo de tu cuenta.",
      GOOGLE_ALREADY_LINKED: "Tu cuenta ya está vinculada con otra cuenta de Google.",
    };

    function showFieldErrors(errors) {
      Object.entries(fields).forEach(([name, input]) => {
        if (!input) return;
        const message = form.querySelector(`[data-error-for="${name}"]`);
        if (message) message.textContent = errors[name] || "";
        input.setAttribute("aria-invalid", String(Boolean(errors[name])));
      });
    }

    function showError(code, message) {
      dialog.dataset.errorCode = code;
      dialogMessage.textContent = message;
      dialog.showModal();
    }

    function setLoading(loading) {
      pending = loading;
      submitButton.disabled = loading;
      submitButton.setAttribute("aria-busy", String(loading));
      buttonLabel.hidden = loading;
      loader.hidden = !loading;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (pending) return;

      const result = window.CredentialValidation.validateForm(mode, {
        displayName: fields.displayName?.value,
        email: fields.email.value,
        password: fields.password.value,
        repeatPassword: fields.repeatPassword?.value,
      });
      showFieldErrors(result.errors);
      status.hidden = true;
      if (Object.keys(result.errors).length) {
        fields[Object.keys(result.errors)[0]].focus();
        return;
      }

      setLoading(true);
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            email: result.email,
            password: result.password,
            ...(mode === "register" && result.displayName ? { display_name: result.displayName } : {}),
          }),
        });
        const body = await response.json();
        if (!response.ok) {
          const error = body.error || {};
          showError(error.code || "REQUEST_FAILED", error.message || "No pudimos completar la solicitud. Intentá nuevamente.");
          return;
        }
        status.textContent = body.message || "Acceso correcto.";
        status.hidden = false;
        status.dataset.state = "success";
        window.setTimeout(() => window.location.assign("/"), 450);
      } catch (_error) {
        showError("NETWORK_ERROR", "No pudimos conectar con el servidor. Intentá nuevamente.");
      } finally {
        setLoading(false);
      }
    });

    const oauthCode = new URLSearchParams(window.location.search || "").get("auth_error");
    if (oauthCode && Object.hasOwn(googleErrors, oauthCode)) {
      showError(oauthCode, googleErrors[oauthCode]);
      window.history?.replaceState(null, "", window.location.pathname);
    }

    document.querySelector(".google-button")?.addEventListener("click", (event) => {
      const button = event?.currentTarget || document.querySelector(".google-button");
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      window.location.assign(`/auth/google/start?flow=signin&source=${mode === "register" ? "register" : "login"}`);
    });
    dialog.querySelector(".modal-close").addEventListener("click", () => dialog.close());

    document.querySelectorAll(".password-toggle").forEach((toggle) => {
      toggle.addEventListener("click", () => {
        const input = document.getElementById(toggle.dataset.target);
        if (!(input instanceof HTMLInputElement)) return;
        const visible = input.type === "password";
        input.type = visible ? "text" : "password";
        toggle.setAttribute("aria-pressed", String(visible));
        toggle.setAttribute("aria-label", visible ? "Ocultar contraseña" : "Mostrar contraseña");
      });
    });
  }

  window.AuthForm = Object.freeze({ mount });
})();

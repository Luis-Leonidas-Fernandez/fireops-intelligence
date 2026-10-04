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
      email: form.querySelector("#email"),
      password: form.querySelector("#password"),
      repeatPassword: form.querySelector("#password-repeat"),
    };
    let pending = false;

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
          body: JSON.stringify({ email: result.email, password: result.password }),
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

    document.querySelector(".google-button")?.addEventListener("click", () => {
      showError("GOOGLE_NOT_AVAILABLE", "El acceso con Google todavía no está disponible. Usá tu correo y contraseña.");
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

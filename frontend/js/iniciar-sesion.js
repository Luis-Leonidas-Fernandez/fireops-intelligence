(() => {
  "use strict";

  const form = document.querySelector("#login-form");
  const googleButton = document.querySelector(".google-button");
  const passwordToggles = document.querySelectorAll(".password-toggle");

  const goToDashboard = () => window.location.assign("/");

  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    goToDashboard();
  });

  googleButton?.addEventListener("click", goToDashboard);

  passwordToggles.forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const targetId = toggle.dataset.target;
      const input = targetId ? document.getElementById(targetId) : null;

      if (!(input instanceof HTMLInputElement)) return;

      const willShow = input.type === "password";
      input.type = willShow ? "text" : "password";
      toggle.setAttribute("aria-pressed", String(willShow));
      toggle.setAttribute(
        "aria-label",
        willShow ? "Ocultar contraseña" : "Mostrar contraseña"
      );
    });
  });
})();

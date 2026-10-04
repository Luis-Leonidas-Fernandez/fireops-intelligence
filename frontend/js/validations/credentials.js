(() => {
  "use strict";

  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function validateForm(mode, values) {
    const errors = {};
    const email = values.email.trim().toLowerCase();
    const password = values.password;

    if (!emailPattern.test(email) || email.length > 320) {
      errors.email = "Ingresá un correo electrónico válido.";
    }
    if (!password) {
      errors.password = "Ingresá tu contraseña.";
    } else if (password.length > 128 || (mode === "register" && (password.length < 8 || !/[A-Za-zÀ-ÿ]/.test(password) || !/\d/.test(password)))) {
      errors.password = "Usá entre 8 y 128 caracteres, con letras y números.";
    }
    if (mode === "register" && values.repeatPassword !== password) {
      errors.repeatPassword = "Las contraseñas no coinciden.";
    }
    return { email, password, errors };
  }

  window.CredentialValidation = Object.freeze({ validateForm });
})();

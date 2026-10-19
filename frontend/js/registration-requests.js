(() => {
  "use strict";

  const requestPanel = document.querySelector("#registration-request-panel");
  const registrationForm = document.querySelector("#registration-form");
  if (requestPanel && registrationForm) {
    const token = new URLSearchParams((window.location.hash || "").slice(1)).get("invite");
    requestPanel.hidden = Boolean(token);
    registrationForm.hidden = !token;
    const title = document.querySelector("#registration-title");
    if (title && !token) title.textContent = "Solicitar registro";
    const status = document.querySelector("#request-status");
    if (new URLSearchParams(window.location.search).get("request_status") === "received") {
      status.textContent = "Si corresponde, recibirás novedades por correo.";
      status.hidden = false;
      window.history.replaceState(null, "", window.location.pathname);
    }
    requestPanel.querySelector("#registration-request-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const button = form.querySelector("button[type=submit]");
      button.disabled = true;
      try {
        const response = await fetch("/auth/registration-requests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ email: form.querySelector("#request-email").value.trim() }),
        });
        if (!response.ok) throw new Error("request_failed");
        status.textContent = "Si corresponde, recibirás novedades por correo.";
      } catch (_error) {
        status.textContent = "No se pudo enviar la solicitud. Inténtalo nuevamente.";
      } finally {
        status.hidden = false;
        button.disabled = false;
      }
    });
    requestPanel.querySelector("#google-request-button").addEventListener("click", () => {
      window.location.assign("/auth/google/start?flow=signin&source=request");
    });
  }

  const list = document.querySelector("#pending-requests");
  if (!list) return;
  const pageStatus = document.querySelector("#review-status");
  async function load() {
    const response = await fetch("/auth/registration-requests", { credentials: "same-origin" });
    if (response.status === 401 || response.status === 403) {
      window.location.assign("/iniciar-sesion");
      return;
    }
    if (!response.ok) throw new Error("load_failed");
    const requests = await response.json();
    list.replaceChildren();
    if (!requests.length) {
      const empty = document.createElement("li");
      empty.textContent = "No hay solicitudes pendientes.";
      list.append(empty);
      return;
    }
    for (const item of requests) {
      const row = document.createElement("li");
      row.className = "request-row";
      const label = document.createElement("span");
      label.textContent = item.email;
      row.append(label);
      for (const [decision, caption] of [["approved", "Aprobar"], ["rejected", "Rechazar"]]) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = caption;
        button.addEventListener("click", async () => {
          row.querySelectorAll("button").forEach((control) => { control.disabled = true; });
          try {
            const response = await fetch(`/auth/registration-requests/${item.id}/review`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              credentials: "same-origin", body: JSON.stringify({ decision }),
            });
            if (!response.ok) throw new Error("review_failed");
            pageStatus.textContent = "Solicitud revisada.";
            await load();
          } catch (_error) {
            pageStatus.textContent = "No se pudo revisar la solicitud. Inténtalo nuevamente.";
            row.querySelectorAll("button").forEach((control) => { control.disabled = false; });
          }
        });
        row.append(button);
      }
      list.append(row);
    }
  }
  load().catch(() => { pageStatus.textContent = "No se pudieron cargar las solicitudes."; });
})();

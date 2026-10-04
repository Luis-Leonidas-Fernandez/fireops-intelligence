(function () {
  "use strict";
  const data = window.DashboardData;
  const renderer = window.DashboardRenderer;
  const dateRange = document.querySelector("#date-range");
  const movementSearch = document.querySelector("#country-search");
  const globalSearch = document.querySelector("#global-search");
  const mobileMenu = document.querySelector(".mobile-menu");
  const mobileNav = document.querySelector("#mobile-nav");
  const toast = document.querySelector("#toast");
  const apiStatus = document.querySelector("#api-status");
  const themeToggle = document.querySelector("#brightness-toggle");
  let toastTimer;

  async function checkApiConnection() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);

    try {
      const healthResponse = await fetch("/health", { signal: controller.signal });
      if (!healthResponse.ok || (await healthResponse.json()).status !== "ok") throw new Error("API unavailable");

      const categoriesResponse = await fetch("/inventory/categories", { signal: controller.signal });
      if (!categoriesResponse.ok) throw new Error("Categories unavailable");
      const categories = await categoriesResponse.json();
      if (!Array.isArray(categories)) throw new Error("Unexpected categories response");

      apiStatus.textContent = `Fire Control API conectada · Categorías en vivo: ${categories.length}`;
      apiStatus.dataset.state = "connected";
    } catch (_error) {
      apiStatus.textContent = "Fire Control API no disponible · Conteo de categorías en vivo no disponible · Datos de demostración visibles";
      apiStatus.dataset.state = "offline";
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function showToast(message) {
    window.clearTimeout(toastTimer); toast.textContent = message; toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2600);
  }

  function setActiveView(view) {
    document.querySelectorAll("[data-view]").forEach(button => {
      const active = button.dataset.view === view;
      button.classList.toggle("is-active", active);
      if (button.closest("nav")) active ? button.setAttribute("aria-current", "page") : button.removeAttribute("aria-current");
    });
    document.querySelector("#page-title").textContent = view;
    document.querySelector("#page-subtitle").textContent = view === "Inventario general" ? "Vista operativa de bienes, estados y movimientos del inventario." : `${view}: vista ilustrativa con datos de demostración.`;
    showToast(`${view} seleccionado`);
  }

  function csvCell(value) { return `"${String(value).replaceAll('"', '""')}"`; }
  function exportCsv() {
    const period = data.periods[dateRange.value];
    const multiplier = period.multiplier;
    const rows = [["Fire Control — Inventario", period.label], ["Datos de demostración"], [], ["Bien", "Código", "Movimiento", "Cantidad"]];
    data.movements.forEach(movement => rows.push([movement.name, movement.code, movement.action, Math.max(1, Math.round(movement.quantity * multiplier))]));
    rows.push([], ["Estado", "Proporción", "Total"]);
    data.statuses.forEach(status => rows.push([status.name, `${status.share}%`, Math.round(status.total * multiplier)]));
    const blob = new Blob([rows.map(row => row.map(csvCell).join(",")).join("\n")], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `fire-control-inventario-demo-${dateRange.value}-dias.csv`; document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(link.href);
    showToast("CSV de demostración exportado");
  }

  renderer.render(dateRange.value);
  checkApiConnection();
  document.querySelector(".global-search").addEventListener("submit", event => event.preventDefault());
  document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => setActiveView(button.dataset.view)));
  dateRange.addEventListener("change", () => { renderer.render(dateRange.value, movementSearch.value); showToast(`Período: ${data.periods[dateRange.value].label.toLowerCase()}`); });
  movementSearch.addEventListener("input", () => renderer.renderMovements(movementSearch.value, data.periods[dateRange.value].multiplier));
  globalSearch.addEventListener("input", () => { movementSearch.value = globalSearch.value; renderer.renderMovements(globalSearch.value, data.periods[dateRange.value].multiplier); });
  document.querySelector("#export-button").addEventListener("click", exportCsv);
  document.querySelector(".logout-button").addEventListener("click", () => {
    window.location.assign("/iniciar-sesion");
  });
  themeToggle.addEventListener("click", () => {
    const lightMode = document.documentElement.dataset.theme !== "light";
    document.documentElement.dataset.theme = lightMode ? "light" : "dark";
    themeToggle.setAttribute("aria-pressed", String(lightMode));
    themeToggle.setAttribute("aria-label", lightMode ? "Activar modo oscuro" : "Activar modo claro");
    showToast(lightMode ? "Modo claro activado" : "Modo oscuro activado");
  });
  mobileMenu.addEventListener("click", () => { const expanded = mobileMenu.getAttribute("aria-expanded") === "true"; mobileMenu.setAttribute("aria-expanded", String(!expanded)); mobileNav.hidden = expanded; });
  document.querySelectorAll(".table-tabs button").forEach(button => button.addEventListener("click", () => { document.querySelectorAll(".table-tabs button").forEach(tab => { tab.classList.toggle("is-active", tab === button); tab.setAttribute("aria-selected", String(tab === button)); }); showToast(`Filtro ilustrativo: ${button.textContent.toLowerCase()}`); }));
  document.addEventListener("keydown", event => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); globalSearch.focus(); } });
})();

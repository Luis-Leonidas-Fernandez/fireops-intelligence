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
  const profileButton = document.querySelector(".profile-button");
  const profileMenu = document.querySelector("#profile-menu");
  let toastTimer;

  function populateCategoryOptions(categories) {
    const catSelect = document.querySelector("#asset-category");
    if (!catSelect || !Array.isArray(categories)) return;
    const currentVal = catSelect.value;
    const isNew = currentVal === "__NEW__";
    const options = [
      `<option value="" disabled ${!currentVal ? "selected" : ""}>Seleccione una categoría…</option>`,
      ...categories.map(c => `<option value="${c.id}">${c.name}</option>`),
      `<option value="__NEW__" class="opt-new-category" ${isNew ? "selected" : ""}>+ Crear nueva categoría…</option>`
    ];
    catSelect.innerHTML = options.join("");
    if (isNew) {
      catSelect.value = "__NEW__";
    } else if (currentVal && categories.some(c => String(c.id) === currentVal)) {
      catSelect.value = currentVal;
    }
  }

  function extractApiErrorMessage(errData, fallbackMsg = "No se pudo registrar el bien.") {
    if (!errData) return fallbackMsg;
    if (typeof errData.error?.message === "string") {
      const fields = errData.error.details?.fields;
      if (Array.isArray(fields) && fields.length > 0) {
        const fieldDetails = fields.map(f => `${f.field}: ${f.message}`).join(", ");
        return `${errData.error.message} (${fieldDetails})`;
      }
      return errData.error.message;
    }
    if (typeof errData.detail === "string") return errData.detail;
    if (Array.isArray(errData.detail) && errData.detail[0]?.msg) return errData.detail[0].msg;
    if (typeof errData.message === "string") return errData.message;
    return fallbackMsg;
  }

  function isExactVehicleCategoryName(name) {
    const normalized = String(name || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase();
    return normalized === "vehiculo" || normalized === "vehiculos";
  }

  function escapeOptionHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function buildDestinationOptionItems({
    locations = [],
    assets = [],
    categories = [],
    excludeLocationId = null,
    excludeAssetId = null,
  }) {
    const locList = Array.isArray(locations) ? locations : [];
    const assetList = Array.isArray(assets) ? assets : [];
    const catList = Array.isArray(categories) ? categories : [];

    const vehicleCategoryIds = new Set();
    catList.forEach(c => {
      if (isExactVehicleCategoryName(c.name)) {
        vehicleCategoryIds.add(Number(c.id));
      }
    });

    const assetByIdMap = new Map(assetList.map(a => [Number(a.id), a]));
    const vehicleLocationByAssetId = new Map();
    const standaloneVehicleLocations = [];

    locList.forEach(loc => {
      const isVeh = String(loc?.location_type || loc?.type || "FISICA").toUpperCase() === "VEHICULO";
      if (isVeh && loc.container_asset_id !== null && loc.container_asset_id !== undefined) {
        const cid = Number(loc.container_asset_id);
        vehicleLocationByAssetId.set(cid, loc);
        if (!assetByIdMap.has(cid)) {
          standaloneVehicleLocations.push(loc);
        }
      } else if (isVeh) {
        standaloneVehicleLocations.push(loc);
      }
    });

    const physicalLocations = locList.filter(
      loc => String(loc?.location_type || loc?.type || "FISICA").toUpperCase() !== "VEHICULO"
    );
    const physicalLocMap = new Map(physicalLocations.map(l => [Number(l.id), l]));

    const vehicleTargets = [];
    const seenAssetIds = new Set();

    assetList.forEach(asset => {
      const aid = Number(asset.id);
      if (seenAssetIds.has(aid)) return;
      if (excludeAssetId !== null && aid === Number(excludeAssetId)) return;

      const mobileLoc = vehicleLocationByAssetId.get(aid) || null;
      const inVehCat =
        asset.category_id !== null &&
        asset.category_id !== undefined &&
        vehicleCategoryIds.has(Number(asset.category_id));

      if (!mobileLoc && !inVehCat) return;
      seenAssetIds.add(aid);

      if (mobileLoc && excludeLocationId !== null && Number(mobileLoc.id) === Number(excludeLocationId)) {
        return;
      }

      const parkingLocId =
        asset.location_id !== null &&
        asset.location_id !== undefined &&
        physicalLocMap.has(Number(asset.location_id))
          ? Number(asset.location_id)
          : null;
      const parkingLocName = parkingLocId !== null ? physicalLocMap.get(parkingLocId).name : null;

      if (mobileLoc) {
        const baseLabel =
          mobileLoc.name && mobileLoc.name !== asset.name
            ? `${mobileLoc.name} (${asset.internal_code})`
            : `${asset.name} (${asset.internal_code})`;
        vehicleTargets.push({
          value: String(mobileLoc.id),
          label: baseLabel,
          parkingLocId,
          parkingLocName,
          unconfigured: false,
        });
      } else {
        vehicleTargets.push({
          value: `veh:${aid}`,
          label: `${asset.name} (${asset.internal_code})`,
          parkingLocId,
          parkingLocName,
          unconfigured: true,
        });
      }
    });

    standaloneVehicleLocations.forEach(loc => {
      if (excludeLocationId !== null && Number(loc.id) === Number(excludeLocationId)) return;
      vehicleTargets.push({
        value: String(loc.id),
        label: loc.name,
        parkingLocId: null,
        parkingLocName: null,
        unconfigured: false,
      });
    });

    const items = [];
    const vehiclesByParkingLoc = new Map();
    const unparkedVehicles = [];

    vehicleTargets.forEach(v => {
      if (v.parkingLocId !== null) {
        if (!vehiclesByParkingLoc.has(v.parkingLocId)) {
          vehiclesByParkingLoc.set(v.parkingLocId, []);
        }
        vehiclesByParkingLoc.get(v.parkingLocId).push(v);
      } else {
        unparkedVehicles.push(v);
      }
    });

    physicalLocations.forEach(physLoc => {
      const pid = Number(physLoc.id);
      if (excludeLocationId === null || pid !== Number(excludeLocationId)) {
        items.push({
          value: String(physLoc.id),
          text: physLoc.name,
        });
      }
      const parkedHere = vehiclesByParkingLoc.get(pid) || [];
      parkedHere.forEach(v => {
        items.push({
          value: v.value,
          text: `  - ${v.label} — ${physLoc.name}`,
        });
      });
    });

    unparkedVehicles.forEach(v => {
      items.push({
        value: v.value,
        text: `  - ${v.label}`,
      });
    });

    return items;
  }

  function populateLocationOptions(locations, selectedId = null, assets = null, categories = null) {
    const locSelect = document.querySelector("#asset-location");
    if (!locSelect) return;
    const currentVal = selectedId !== null && selectedId !== undefined ? String(selectedId) : locSelect.value;
    const isNew = currentVal === "__NEW__";
    const realData = window.DashboardRenderer?.getRealData?.() || {};
    const resolvedAssets = Array.isArray(assets) ? assets : (realData.assets || []);
    const resolvedCategories = Array.isArray(categories) ? categories : (realData.categories || []);

    const destItems = buildDestinationOptionItems({
      locations: Array.isArray(locations) ? locations : [],
      assets: resolvedAssets,
      categories: resolvedCategories,
    });

    const options = [
      `<option value="" ${!currentVal ? "selected" : ""}>Sin asignación fija (Depósito)</option>`,
      ...destItems.map(
        item =>
          `<option value="${escapeOptionHtml(item.value)}" ${item.value === currentVal ? "selected" : ""}>${escapeOptionHtml(item.text)}</option>`
      ),
      `<option value="__NEW__" class="opt-new-category" ${isNew ? "selected" : ""}>+ Nueva ubicación…</option>`,
    ];
    locSelect.innerHTML = options.join("");
    if (isNew) {
      locSelect.value = "__NEW__";
    } else if (currentVal && destItems.some(item => item.value === currentVal)) {
      locSelect.value = currentVal;
    } else {
      locSelect.value = "";
    }
  }

  function populateContainerAssetOptions(assets) {
    const containerSelect = document.querySelector("#location-container-asset");
    if (!containerSelect || !Array.isArray(assets)) return;
    const currentVal = containerSelect.value;
    const options = [
      `<option value="" disabled ${!currentVal ? "selected" : ""}>Seleccione el bien contenedor…</option>`,
      ...assets.map(a => `<option value="${a.id}">${a.name} (${a.internal_code})</option>`)
    ];
    containerSelect.innerHTML = options.join("");
    if (currentVal && assets.some(a => String(a.id) === currentVal)) {
      containerSelect.value = currentVal;
    }
  }

  async function checkApiConnection() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 6000);

    try {
      const [healthResponse, categoriesResponse, assetsResponse, locationsResponse, movementsResponse] = await Promise.all([
        fetch("/health", { signal: controller.signal }),
        fetch("/inventory/categories", { signal: controller.signal, credentials: "same-origin" }),
        fetch("/inventory/assets/", { signal: controller.signal, credentials: "same-origin" }),
        fetch("/inventory/locations", { signal: controller.signal, credentials: "same-origin" }),
        fetch("/inventory/movements", { signal: controller.signal, credentials: "same-origin" }).catch(() => ({ ok: false })),
      ]);

      if (!healthResponse.ok || (await healthResponse.json()).status !== "ok") throw new Error("API unavailable");
      if (!categoriesResponse.ok) throw new Error("Categories unavailable");
      const categories = await categoriesResponse.json();
      if (!Array.isArray(categories)) throw new Error("Unexpected categories response");

      let assets = [];
      if (assetsResponse.ok) {
        const assetsData = await assetsResponse.json();
        if (Array.isArray(assetsData)) assets = assetsData;
      }

      let locations = [];
      if (locationsResponse.ok) {
        const locationsData = await locationsResponse.json();
        if (Array.isArray(locationsData)) locations = locationsData;
      }

      let movements = [];
      if (movementsResponse && movementsResponse.ok && typeof movementsResponse.json === "function") {
        try {
          const movementsData = await movementsResponse.json();
          if (Array.isArray(movementsData)) movements = movementsData;
        } catch (_) {}
      }

      populateCategoryOptions(categories);
      populateLocationOptions(locations, null, assets, categories);
      populateContainerAssetOptions(assets);

      const realData = { assets, categories, locations, movements };
      if (window.DashboardRenderer && typeof window.DashboardRenderer.setRealData === "function") {
        window.DashboardRenderer.setRealData(realData);
      }

      apiStatus.textContent = `Fire Control API conectada · Datos en tiempo real (Bienes: ${assets.length} · Categorías: ${categories.length} · Ubicaciones: ${locations.length} · Movimientos: ${movements.length})`;
      apiStatus.dataset.state = "connected";

      const dataNote = document.querySelector(".data-note");
      if (dataNote) {
        dataNote.textContent = "Datos en tiempo real sincronizados con la base de datos de Fire Control";
      }
    } catch (_error) {
      apiStatus.textContent = "Fire Control API en modo local · Datos de demostración visibles";
      apiStatus.dataset.state = "offline";
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function showToast(message) {
    window.clearTimeout(toastTimer); toast.textContent = message; toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2600);
  }

  const authParams = new URLSearchParams(window.location.search);
  const authCode = authParams.get("auth_error");
  const authStatus = authParams.get("auth_status");
  const googleMessages = {
    GOOGLE_LINKED: "Cuenta de Google vinculada correctamente.",
    GOOGLE_EMAIL_MISMATCH: "El correo de Google debe coincidir con el de tu cuenta.",
    GOOGLE_ALREADY_LINKED: "Tu cuenta ya está vinculada con otra cuenta de Google.",
    GOOGLE_ACCOUNT_CONFLICT: "Esa cuenta de Google ya está vinculada a otra persona.",
    GOOGLE_SESSION_EXPIRED: "La autorización con Google venció. Intentá nuevamente.",
    GOOGLE_ACCESS_DENIED: "Se canceló la vinculación con Google.",
    GOOGLE_AUTH_FAILED: "No pudimos verificar tu cuenta de Google.",
    GOOGLE_NOT_CONFIGURED: "El acceso con Google no está configurado en este entorno.",
  };
  const feedback = googleMessages[authStatus] || googleMessages[authCode];
  if (feedback) {
    showToast(feedback);
    window.history.replaceState(null, "", "/");
  }

  const VIEW_SUBTITLES = {
    "Inventario general": "Vista operativa de bienes, estados y movimientos del inventario.",
    "Bienes": "Gestión integral de equipamiento, herramientas y materiales operativos.",
    "Nuevo bien": "Alta de equipamiento, herramientas y materiales operativos.",
    "Detalle de bien": "Ficha técnica, ubicación actual y trazabilidad de movimientos del bien.",
    "Categorías": "Clasificación y catálogo de bienes del cuerpo de bomberos.",
    "Nueva categoría": "Alta y registro de nueva categoría en el catálogo operativo.",
    "Detalle de categoría": "Listado de bienes asociados a la categoría seleccionada.",
    "Ubicaciones": "Destinos operativos, cuarteles, depósitos y móviles asignados.",
    "Nueva ubicación": "Alta y registro de nueva ubicación física o vehicular en el inventario.",
    "Detalle de ubicación": "Listado de bienes asignados actualmente a la ubicación seleccionada.",
    "Invitaciones": "Revisión de solicitudes de registro e invitaciones emitidas con autorización administrativa.",
    "Vehículos": "Parque automotor, autobombas, cisternas y unidades de apoyo.",
    "Responsables": "Asignación de personal a cargo de activos y equipamiento.",
    "Movimientos": "Historial de ingresos, egresos, traslados y bajas.",
    "Auditoría": "Registro de eventos del sistema y trazabilidad de acciones.",
    "Reportes": "Informes consolidados y estadísticas de inventario.",
    "Alertas": "Monitoreo preventivo y avisos de mantenimiento técnico.",
  };

  let detalleBienReturnView = "Bienes";
  let ubicacionDetalleReturnView = "Ubicaciones";

  function setActiveView(view) {
    if (window.FireNavigationController && typeof window.FireNavigationController.selectView === "function") {
      const allowed = window.FireNavigationController.selectView(view);
      if (!allowed) {
        showToast(`Acceso denegado a ${view}`);
        return;
      }
    }
    document.querySelectorAll("[data-view]").forEach(button => {
      const isNav = Boolean(button.closest("nav"));
      const active = (button.dataset.view === view) ||
        (isNav && view === "Nuevo bien" && button.dataset.view === "Bienes") ||
        (isNav && view === "Detalle de bien" && (
          (detalleBienReturnView === "Detalle de ubicación" && button.dataset.view === (ubicacionDetalleReturnView === "Vehículos" ? "Vehículos" : "Ubicaciones")) ||
          (detalleBienReturnView === "Detalle de categoría" && button.dataset.view === "Categorías") ||
          (detalleBienReturnView === "Vehículos" && button.dataset.view === "Vehículos") ||
          (detalleBienReturnView !== "Detalle de ubicación" && detalleBienReturnView !== "Detalle de categoría" && detalleBienReturnView !== "Vehículos" && button.dataset.view === "Bienes")
        )) ||
        (isNav && (view === "Nueva categoría" || view === "Detalle de categoría") && button.dataset.view === "Categorías") ||
        (isNav && view === "Nueva ubicación" && button.dataset.view === "Ubicaciones") ||
        (isNav && view === "Detalle de ubicación" && button.dataset.view === (ubicacionDetalleReturnView === "Vehículos" ? "Vehículos" : "Ubicaciones"));
      button.classList.toggle("is-active", active);
      if (isNav) active ? button.setAttribute("aria-current", "page") : button.removeAttribute("aria-current");
    });

    const titleEl = document.querySelector("#page-title");
    const subtitleEl = document.querySelector("#page-subtitle");
    if (titleEl) titleEl.textContent = view === "Invitaciones" ? "Gestión de accesos" : view;
    if (subtitleEl) subtitleEl.textContent = VIEW_SUBTITLES[view] || `${view}: vista ilustrativa con datos de demostración.`;

    const headingActions = document.querySelector("#dashboard-heading-actions");
    if (headingActions) {
      headingActions.hidden = (view !== "Inventario general");
    }

    const viewContainers = document.querySelectorAll(".view-content");
    let matchedSpecific = false;
    viewContainers.forEach(container => {
      const targetView = container.dataset.view;
      if (targetView === view) {
        container.hidden = false;
        matchedSpecific = true;
      } else if (container.id !== "view-generic") {
        container.hidden = true;
      }
    });

    const genericContainer = document.querySelector("#view-generic");
    if (genericContainer) {
      if (!matchedSpecific && view !== "Inventario general") {
        genericContainer.hidden = false;
        const kicker = genericContainer.querySelector(".panel-kicker");
        if (kicker) kicker.textContent = `Módulo ${view}`;
        const h2 = genericContainer.querySelector("h2");
        if (h2) h2.textContent = `Sección de ${view}`;
      } else {
        genericContainer.hidden = true;
      }
    }

    if (view === "Invitaciones") {
      loadAccessManagementData();
    } else if (view === "Vehículos") {
      loadVehiculosViewData();
    }

    showToast(`${view === "Invitaciones" ? "Gestión de accesos" : view} seleccionado`);
  }

  function csvCell(value) { return `"${String(value).replaceAll('"', '""')}"`; }
  function exportCsv() {
    const realData = window.DashboardRenderer && typeof window.DashboardRenderer.getRealData === "function" ? window.DashboardRenderer.getRealData() : null;
    if (realData && realData.assets.length) {
      const catMap = new Map(realData.categories.map(c => [c.id, c.name]));
      const locMap = new Map(realData.locations.map(l => [l.id, l.name]));
      const rows = [
        ["Fire Control — Inventario en tiempo real", new Date().toLocaleString("es-AR")],
        ["Código", "Bien / Denominación", "Categoría", "Ubicación", "Estado"],
      ];
      realData.assets.forEach(a => {
        rows.push([
          a.internal_code,
          a.name,
          catMap.get(a.category_id) || "Sin categoría",
          locMap.get(a.location_id) || "Depósito Central",
          a.location_id ? "En servicio" : "En depósito",
        ]);
      });
      const blob = new Blob([rows.map(row => row.map(csvCell).join(",")).join("\n")], { type: "text/csv;charset=utf-8" });
      const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `fire-control-inventario-real.csv`; document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(link.href);
      showToast("CSV con datos en tiempo real exportado");
      return;
    }

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

  if (window.FireNavigation && typeof window.FireNavigation.createNavigationController === "function") {
    window.FireNavigationController = window.FireNavigation.createNavigationController();
  }

  renderer.render(dateRange.value);
  const profileMountPromise = window.DashboardProfile.mount();
  checkApiConnection();
  document.querySelector(".global-search").addEventListener("submit", event => event.preventDefault());
  document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => setActiveView(button.dataset.view)));
  dateRange.addEventListener("change", () => { renderer.render(dateRange.value, movementSearch.value); showToast(`Período: ${data.periods[dateRange.value].label.toLowerCase()}`); });
  movementSearch.addEventListener("input", () => renderer.renderMovements(movementSearch.value, data.periods[dateRange.value].multiplier));
  globalSearch.addEventListener("input", () => { movementSearch.value = globalSearch.value; renderer.renderMovements(globalSearch.value, data.periods[dateRange.value].multiplier); });
  document.querySelector("#export-button").addEventListener("click", exportCsv);
  document.querySelector(".logout-button").addEventListener("click", async () => {
    try {
      await fetch("/auth/logout", { method: "POST", credentials: "same-origin" });
    } finally {
      window.location.assign("/iniciar-sesion");
    }
  });
  profileButton.addEventListener("click", () => {
    profileMenu.hidden = !profileMenu.hidden;
    profileButton.setAttribute("aria-expanded", String(!profileMenu.hidden));
  });
  document.querySelector("#google-link-button").addEventListener("click", () => {
    window.location.assign("/auth/google/start?flow=link");
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".profile-menu-wrap")) {
      profileMenu.hidden = true;
      profileButton.setAttribute("aria-expanded", "false");
    }
  });
  themeToggle.addEventListener("click", () => {
    const lightMode = document.documentElement.dataset.theme !== "light";
    document.documentElement.dataset.theme = lightMode ? "light" : "dark";
    themeToggle.setAttribute("aria-pressed", String(lightMode));
    themeToggle.setAttribute("aria-label", lightMode ? "Activar modo oscuro" : "Activar modo claro");
    showToast(lightMode ? "Modo claro activado" : "Modo oscuro activado");
  });
  mobileMenu.addEventListener("click", () => { const expanded = mobileMenu.getAttribute("aria-expanded") === "true"; mobileMenu.setAttribute("aria-expanded", String(!expanded)); mobileNav.hidden = expanded; });
  document.querySelectorAll(".table-tabs button").forEach(button => {
    if (button.closest("#view-invitaciones, #view-bienes, #view-ubicaciones, #view-movimientos")) return;
    button.addEventListener("click", () => {
      const tabContainer = button.closest(".table-tabs");
      if (tabContainer) {
        tabContainer.querySelectorAll("button").forEach(tab => {
          const isCurrent = (tab === button);
          tab.classList.toggle("is-active", isCurrent);
          tab.setAttribute("aria-selected", String(isCurrent));
        });
      }
      const filter = button.dataset.filter;
      const panel = button.closest(".panel");
      if (panel && filter) {
        if (panel.classList.contains("countries-panel") && window.DashboardRenderer && typeof window.DashboardRenderer.setRealFilter === "function") {
          window.DashboardRenderer.setRealFilter(filter);
        } else {
          const rows = panel.querySelectorAll("tbody tr");
          rows.forEach(row => {
            if (filter === "all") {
              row.hidden = false;
            } else {
              const rowStatus = row.dataset.status || row.dataset.type;
              row.hidden = (rowStatus !== filter);
            }
          });
        }
      }
      showToast(`Filtro ilustrativo: ${button.textContent.trim().toLowerCase()}`);
    });
  });

  const nextAssetsBtn = document.querySelector("#btn-next-assets");
  const prevAssetsBtn = document.querySelector("#btn-prev-assets");
  if (nextAssetsBtn) {
    nextAssetsBtn.addEventListener("click", () => {
      if (window.DashboardRenderer && typeof window.DashboardRenderer.nextAssetsPage === "function") {
        window.DashboardRenderer.nextAssetsPage();
      }
    });
  }
  if (prevAssetsBtn) {
    prevAssetsBtn.addEventListener("click", () => {
      if (window.DashboardRenderer && typeof window.DashboardRenderer.prevAssetsPage === "function") {
        window.DashboardRenderer.prevAssetsPage();
      }
    });
  }

  document.querySelectorAll(".view-search input").forEach(input => {
    if (input.closest("#view-invitaciones, #view-bienes, #view-categorias, #view-categoria-bienes, #view-ubicaciones, #view-ubicacion-bienes, #view-vehiculos, #view-movimientos")) return;
    input.addEventListener("input", () => {
      const query = input.value.trim().toLowerCase();
      const panel = input.closest(".panel");
      if (!panel) return;
      const rows = panel.querySelectorAll("tbody tr");
      rows.forEach(row => {
        if (!query) {
          row.hidden = false;
        } else {
          row.hidden = !row.textContent.toLowerCase().includes(query);
        }
      });
    });
  });

  let ubicacionReturnView = "Ubicaciones";
  let lastValidAssetLocationValue = "";

  function configureNuevaUbicacionReturnTarget(originView = "Ubicaciones") {
    ubicacionReturnView = originView;
    const backBtn = document.querySelector("#btn-cancelar-crear-ubicacion");
    const footerCancelBtn = document.querySelector("#btn-cancelar-ubicacion-footer");
    if (backBtn) {
      backBtn.dataset.viewTarget = originView;
      backBtn.innerHTML = `<span aria-hidden="true">←</span> Volver a ${originView}`;
    }
    if (footerCancelBtn) {
      footerCancelBtn.dataset.viewTarget = originView;
    }
  }

  function setScopedBienesFeedback(selector, message, isError = true) {
    const banner = document.querySelector(selector);
    if (!banner) return;
    if (!message) {
      banner.hidden = true;
      banner.textContent = "";
      delete banner.dataset.state;
      return;
    }
    banner.hidden = false;
    banner.textContent = message;
    banner.dataset.state = isError ? "error" : "info";
    if (isError) {
      banner.style.borderColor = "rgba(229, 57, 53, 0.45)";
      banner.style.background = "rgba(229, 57, 53, 0.12)";
      banner.style.color = "var(--primary-hover)";
    } else {
      banner.style.borderColor = "var(--border)";
      banner.style.background = "var(--surface)";
      banner.style.color = "var(--text-soft)";
    }
  }

  function setUbicacionBienesFeedback(message, isError = true) {
    setScopedBienesFeedback("#ubicacion-bienes-feedback", message, isError);
  }

  function setCategoriaBienesFeedback(message, isError = true) {
    setScopedBienesFeedback("#categoria-bienes-feedback", message, isError);
  }

  function setVehiculosFeedback(message, isError = true) {
    setScopedBienesFeedback("#vehiculos-feedback", message, isError);
  }

  async function loadVehiculosViewData() {
    setVehiculosFeedback("", false);
    const tableBody = document.querySelector("#vehiculos-table-body");
    const searchInput = document.querySelector("#vehiculos-search-input");
    const existingData = window.DashboardRenderer?.getRealData?.();
    if (existingData && typeof window.DashboardRenderer?.renderVehiculosView === "function") {
      window.DashboardRenderer.renderVehiculosView(existingData, searchInput?.value || "");
    } else if (tableBody) {
      tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 24px; color: var(--text-soft);">Cargando parque automotor…</td></tr>`;
    }

    try {
      const [locsResp, assetsResp, catsResp] = await Promise.all([
        fetch("/inventory/locations", { credentials: "same-origin" }),
        fetch("/inventory/assets/", { credentials: "same-origin" }),
        fetch("/inventory/categories", { credentials: "same-origin" }),
      ]);

      if (locsResp.status === 401 || assetsResp.status === 401 || catsResp.status === 401) {
        const msg = "Sesión expirada o no autenticada. Iniciá sesión para consultar los vehículos.";
        setVehiculosFeedback(msg, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
        }
        showToast(`Error: ${msg}`);
        return;
      }

      if (locsResp.status === 403 || assetsResp.status === 403 || catsResp.status === 403) {
        const msg = "No tenés permisos para consultar el parque automotor.";
        setVehiculosFeedback(msg, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
        }
        showToast(`Error: ${msg}`);
        return;
      }

      if (!locsResp.ok || !assetsResp.ok || !catsResp.ok) {
        let errDetail = "No se pudo obtener la información de vehículos.";
        try {
          const failedResp = !locsResp.ok ? locsResp : (!assetsResp.ok ? assetsResp : catsResp);
          const errJson = await failedResp.json();
          errDetail = extractApiErrorMessage(errJson, errDetail);
        } catch (_) {}
        setVehiculosFeedback(errDetail, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 24px; color: var(--text-soft);">${errDetail}</td></tr>`;
        }
        showToast(`Error: ${errDetail}`);
        return;
      }

      const [locationsData, assetsData, categoriesData] = await Promise.all([
        locsResp.json(),
        assetsResp.json(),
        catsResp.json(),
      ]);

      const currentReal = window.DashboardRenderer?.getRealData?.() || { movements: [] };
      const updatedRealData = {
        assets: Array.isArray(assetsData) ? assetsData : [],
        categories: Array.isArray(categoriesData) ? categoriesData : [],
        locations: Array.isArray(locationsData) ? locationsData : [],
        movements: Array.isArray(currentReal.movements) ? currentReal.movements : [],
      };

      if (window.DashboardRenderer && typeof window.DashboardRenderer.setRealData === "function") {
        window.DashboardRenderer.setRealData(updatedRealData);
      }
      if (window.DashboardRenderer && typeof window.DashboardRenderer.renderVehiculosView === "function") {
        window.DashboardRenderer.renderVehiculosView(updatedRealData, searchInput?.value || "");
      }
    } catch (_error) {
      const msg = "Error de conexión al consultar el parque automotor.";
      setVehiculosFeedback(msg, true);
      if (tableBody && !existingData) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
      }
      showToast(msg);
    }
  }

  async function openLocationAssetsView(locationId, originView = "Ubicaciones") {
    const locIdNum = Number(locationId);
    if (!Number.isFinite(locIdNum) || locIdNum <= 0) {
      showToast("Error: Identificador de ubicación inválido.");
      return;
    }

    if (window.FireNavigationController && typeof window.FireNavigationController.canAccessModule === "function") {
      const role = window.FireNavigationController.getCurrentRole?.();
      if (role && !window.FireNavigationController.canAccessModule("Detalle de ubicación", role)) {
        showToast("Acceso denegado a Detalle de ubicación");
        return;
      }
    }

    ubicacionDetalleReturnView = originView || "Ubicaciones";
    const backBtn = document.querySelector("#btn-volver-ubicaciones");
    if (backBtn) {
      backBtn.dataset.viewTarget = ubicacionDetalleReturnView;
      backBtn.innerHTML = `<span aria-hidden="true">←</span> Volver a ${ubicacionDetalleReturnView}`;
    }

    const searchInput = document.querySelector("#ubicacion-bienes-search-input");
    if (searchInput) searchInput.value = "";
    setUbicacionBienesFeedback("", false);

    setActiveView("Detalle de ubicación");

    const tableBody = document.querySelector("#ubicacion-bienes-table-body");
    const existingData = window.DashboardRenderer?.getRealData?.();
    if (existingData && typeof window.DashboardRenderer?.renderUbicacionBienesView === "function") {
      window.DashboardRenderer.renderUbicacionBienesView(existingData, locIdNum, "");
    } else if (tableBody) {
      tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">Cargando bienes de la ubicación…</td></tr>`;
    }

    try {
      const [locResp, assetsResp, catsResp] = await Promise.all([
        fetch(`/inventory/locations/${encodeURIComponent(locIdNum)}`, { credentials: "same-origin" }),
        fetch("/inventory/assets/", { credentials: "same-origin" }),
        fetch("/inventory/categories", { credentials: "same-origin" }),
      ]);

      if (locResp.status === 401 || assetsResp.status === 401 || catsResp.status === 401) {
        const msg = "Sesión expirada o no autenticada. Iniciá sesión para consultar los bienes.";
        setUbicacionBienesFeedback(msg, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
        }
        showToast(`Error: ${msg}`);
        return;
      }

      if (locResp.status === 403 || assetsResp.status === 403 || catsResp.status === 403) {
        const msg = "No tenés permisos para consultar los bienes de esta ubicación.";
        setUbicacionBienesFeedback(msg, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
        }
        showToast(`Error: ${msg}`);
        return;
      }

      if (locResp.status === 404) {
        const msg = "La ubicación seleccionada no existe o no fue encontrada.";
        setUbicacionBienesFeedback(msg, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
        }
        showToast(`Error: ${msg}`);
        return;
      }

      if (!locResp.ok || !assetsResp.ok || !catsResp.ok) {
        let errDetail = "No se pudieron obtener los bienes de la ubicación.";
        try {
          const failedResp = !locResp.ok ? locResp : (!assetsResp.ok ? assetsResp : catsResp);
          const errJson = await failedResp.json();
          errDetail = extractApiErrorMessage(errJson, errDetail);
        } catch (_) {}
        setUbicacionBienesFeedback(errDetail, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">${errDetail}</td></tr>`;
        }
        showToast(`Error: ${errDetail}`);
        return;
      }

      const [locationObj, assetsData, categoriesData] = await Promise.all([
        locResp.json(),
        assetsResp.json(),
        catsResp.json(),
      ]);

      const currentReal = window.DashboardRenderer?.getRealData?.() || { locations: [], movements: [] };
      const existingLocations = Array.isArray(currentReal.locations) ? [...currentReal.locations] : [];
      const locIdx = existingLocations.findIndex(l => Number(l.id) === Number(locationObj.id));
      if (locIdx >= 0) {
        existingLocations[locIdx] = locationObj;
      } else {
        existingLocations.push(locationObj);
      }

      const updatedRealData = {
        assets: Array.isArray(assetsData) ? assetsData : [],
        categories: Array.isArray(categoriesData) ? categoriesData : [],
        locations: existingLocations,
        movements: Array.isArray(currentReal.movements) ? currentReal.movements : [],
      };

      if (window.DashboardRenderer && typeof window.DashboardRenderer.setRealData === "function") {
        window.DashboardRenderer.setRealData(updatedRealData);
      }
      if (window.DashboardRenderer && typeof window.DashboardRenderer.renderUbicacionBienesView === "function") {
        window.DashboardRenderer.renderUbicacionBienesView(updatedRealData, locIdNum, searchInput?.value || "");
      }
    } catch (_error) {
      const msg = "Error de conexión al consultar los bienes de la ubicación.";
      setUbicacionBienesFeedback(msg, true);
      if (tableBody && !existingData) {
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
      }
      showToast(msg);
    }
  }

  async function openCategoryAssetsView(categoryId) {
    const catIdNum = Number(categoryId);
    if (!Number.isFinite(catIdNum) || catIdNum <= 0) {
      showToast("Error: Identificador de categoría inválido.");
      return;
    }

    if (window.FireNavigationController && typeof window.FireNavigationController.canAccessModule === "function") {
      const role = window.FireNavigationController.getCurrentRole?.();
      if (role && !window.FireNavigationController.canAccessModule("Detalle de categoría", role)) {
        showToast("Acceso denegado a Detalle de categoría");
        return;
      }
    }

    const searchInput = document.querySelector("#categoria-bienes-search-input");
    if (searchInput) searchInput.value = "";
    setCategoriaBienesFeedback("", false);

    setActiveView("Detalle de categoría");

    const tableBody = document.querySelector("#categoria-bienes-table-body");
    const existingData = window.DashboardRenderer?.getRealData?.();
    if (existingData && typeof window.DashboardRenderer?.renderCategoriaBienesView === "function") {
      window.DashboardRenderer.renderCategoriaBienesView(existingData, catIdNum, "");
    } else if (tableBody) {
      tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">Cargando bienes de la categoría…</td></tr>`;
    }

    try {
      const [catsResp, assetsResp, locsResp] = await Promise.all([
        fetch("/inventory/categories", { credentials: "same-origin" }),
        fetch("/inventory/assets/", { credentials: "same-origin" }),
        fetch("/inventory/locations", { credentials: "same-origin" }),
      ]);

      if (catsResp.status === 401 || assetsResp.status === 401 || locsResp.status === 401) {
        const msg = "Sesión expirada o no autenticada. Iniciá sesión para consultar los bienes.";
        setCategoriaBienesFeedback(msg, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
        }
        showToast(`Error: ${msg}`);
        return;
      }

      if (catsResp.status === 403 || assetsResp.status === 403 || locsResp.status === 403) {
        const msg = "No tenés permisos para consultar los bienes de esta categoría.";
        setCategoriaBienesFeedback(msg, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
        }
        showToast(`Error: ${msg}`);
        return;
      }

      if (catsResp.status === 404) {
        const msg = "La categoría seleccionada no existe o no fue encontrada.";
        setCategoriaBienesFeedback(msg, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
        }
        showToast(`Error: ${msg}`);
        return;
      }

      if (!catsResp.ok || !assetsResp.ok || !locsResp.ok) {
        let errDetail = "No se pudieron obtener los bienes de la categoría.";
        try {
          const failedResp = !catsResp.ok ? catsResp : (!assetsResp.ok ? assetsResp : locsResp);
          const errJson = await failedResp.json();
          errDetail = extractApiErrorMessage(errJson, errDetail);
        } catch (_) {}
        setCategoriaBienesFeedback(errDetail, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">${errDetail}</td></tr>`;
        }
        showToast(`Error: ${errDetail}`);
        return;
      }

      const [categoriesData, assetsData, locationsData] = await Promise.all([
        catsResp.json(),
        assetsResp.json(),
        locsResp.json(),
      ]);

      const categoriesList = Array.isArray(categoriesData) ? categoriesData : [];
      const categoryObj = categoriesList.find(c => Number(c.id) === catIdNum);
      if (!categoryObj) {
        const msg = "La categoría seleccionada no existe o no fue encontrada.";
        setCategoriaBienesFeedback(msg, true);
        if (tableBody) {
          tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
        }
        showToast(`Error: ${msg}`);
        return;
      }

      const currentReal = window.DashboardRenderer?.getRealData?.() || { movements: [] };
      const updatedRealData = {
        assets: Array.isArray(assetsData) ? assetsData : [],
        categories: categoriesList,
        locations: Array.isArray(locationsData) ? locationsData : [],
        movements: Array.isArray(currentReal.movements) ? currentReal.movements : [],
      };

      if (window.DashboardRenderer && typeof window.DashboardRenderer.setRealData === "function") {
        window.DashboardRenderer.setRealData(updatedRealData);
      }
      if (window.DashboardRenderer && typeof window.DashboardRenderer.renderCategoriaBienesView === "function") {
        window.DashboardRenderer.renderCategoriaBienesView(updatedRealData, catIdNum, searchInput?.value || "");
      }
    } catch (_error) {
      const msg = "Error de conexión al consultar los bienes de la categoría.";
      setCategoriaBienesFeedback(msg, true);
      if (tableBody && !existingData) {
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
      }
      showToast(msg);
    }
  }

  async function openAssetDetailView(assetId, originView = "Bienes") {
    const assetIdNum = Number(assetId);
    if (!Number.isFinite(assetIdNum) || assetIdNum <= 0) return;

    detalleBienReturnView = originView || "Bienes";
    const backBtn = document.querySelector("#btn-volver-detalle-bien");
    if (backBtn) {
      backBtn.dataset.viewTarget = detalleBienReturnView;
      const returnLabel = detalleBienReturnView === "Detalle de ubicación"
        ? "la ubicación"
        : detalleBienReturnView === "Detalle de categoría"
          ? "la categoría"
          : detalleBienReturnView;
      backBtn.innerHTML = `<span aria-hidden="true">←</span> Volver a ${returnLabel}`;
    }

    const feedbackEl = document.querySelector("#bien-detalle-feedback");
    if (feedbackEl) {
      feedbackEl.hidden = true;
      feedbackEl.textContent = "";
    }

    setActiveView("Detalle de bien");

    const currentReal = window.DashboardRenderer?.getRealData?.();
    if (currentReal && typeof window.DashboardRenderer?.renderDetalleBienView === "function") {
      window.DashboardRenderer.renderDetalleBienView(currentReal, assetIdNum);
    }

    try {
      const [assetResp, transfersResp] = await Promise.all([
        fetch(`/inventory/assets/${encodeURIComponent(assetIdNum)}`, { credentials: "same-origin" }),
        fetch(`/inventory/assets/${encodeURIComponent(assetIdNum)}/transfers`, { credentials: "same-origin" }).catch(() => ({ ok: false })),
      ]);

      if (!assetResp.ok) {
        const msg = assetResp.status === 403
          ? "No tenés permisos para consultar el detalle de este bien."
          : "No se pudo cargar el detalle actualizado del bien.";
        if (feedbackEl) {
          feedbackEl.hidden = false;
          feedbackEl.textContent = msg;
        }
        return;
      }

      const assetObj = await assetResp.json();
      let transfers = null;
      if (transfersResp && transfersResp.ok && typeof transfersResp.json === "function") {
        try {
          const tData = await transfersResp.json();
          if (Array.isArray(tData)) transfers = tData;
        } catch (_) {}
      }

      const baseReal = window.DashboardRenderer?.getRealData?.() || { assets: [], categories: [], locations: [], movements: [] };
      const assetsList = Array.isArray(baseReal.assets) ? [...baseReal.assets] : [];
      const aIdx = assetsList.findIndex(a => Number(a.id) === Number(assetObj.id));
      if (aIdx >= 0) assetsList[aIdx] = assetObj;
      else assetsList.push(assetObj);

      const mergedReal = { ...baseReal, assets: assetsList };
      if (window.DashboardRenderer && typeof window.DashboardRenderer.renderDetalleBienView === "function") {
        window.DashboardRenderer.renderDetalleBienView(mergedReal, assetIdNum, transfers);
      }
    } catch (_err) {
      if (feedbackEl) {
        feedbackEl.hidden = false;
        feedbackEl.textContent = "Error de conexión al consultar el detalle del bien.";
      }
    }
  }

  // Delegated handler ensures clicks on button, icon, or text reliably activate the target view
  document.addEventListener("click", (event) => {
    const verDotacionVehBtn = event.target.closest(".btn-ver-dotacion-vehiculo");
    if (verDotacionVehBtn && verDotacionVehBtn.dataset.locId) {
      event.preventDefault();
      openLocationAssetsView(Number(verDotacionVehBtn.dataset.locId), "Vehículos");
      return;
    }
    const verFichaVehBtn = event.target.closest(".btn-ver-ficha-vehiculo");
    if (verFichaVehBtn && verFichaVehBtn.dataset.assetId) {
      event.preventDefault();
      openAssetDetailView(Number(verFichaVehBtn.dataset.assetId), "Vehículos");
      return;
    }
    const verBienesLocBtn = event.target.closest(".btn-ver-bienes-ubicacion, button[data-loc-id]");
    if (verBienesLocBtn && verBienesLocBtn.dataset.locId) {
      event.preventDefault();
      const fromVehiculos = Boolean(verBienesLocBtn.closest?.("#view-vehiculos"));
      openLocationAssetsView(Number(verBienesLocBtn.dataset.locId), fromVehiculos ? "Vehículos" : "Ubicaciones");
      return;
    }
    const verBienesCatBtn = event.target.closest(".btn-ver-bienes-categoria, button[data-cat-id]");
    if (verBienesCatBtn && verBienesCatBtn.dataset.catId) {
      event.preventDefault();
      openCategoryAssetsView(Number(verBienesCatBtn.dataset.catId));
      return;
    }
    const verDetalleBienBtn = event.target.closest(".btn-ver-detalle-bien");
    if (verDetalleBienBtn && verDetalleBienBtn.dataset.assetId) {
      event.preventDefault();
      let originView = "Bienes";
      if (verDetalleBienBtn.closest?.("#view-ubicacion-bienes")) {
        originView = "Detalle de ubicación";
      } else if (verDetalleBienBtn.closest?.("#view-categoria-bienes")) {
        originView = "Detalle de categoría";
      } else if (verDetalleBienBtn.closest?.("#view-vehiculos")) {
        originView = "Vehículos";
      }
      openAssetDetailView(Number(verDetalleBienBtn.dataset.assetId), originView);
      return;
    }
    const volverDetalleBienBtn = event.target.closest("#btn-volver-detalle-bien");
    if (volverDetalleBienBtn) {
      event.preventDefault();
      setActiveView(detalleBienReturnView || "Bienes");
      return;
    }
    const volverUbicacionesBtn = event.target.closest("#btn-volver-ubicaciones");
    if (volverUbicacionesBtn) {
      event.preventDefault();
      setActiveView(ubicacionDetalleReturnView || "Ubicaciones");
      return;
    }
    const volverCategoriasBtn = event.target.closest("#btn-volver-categorias");
    if (volverCategoriasBtn) {
      event.preventDefault();
      setActiveView("Categorías");
      return;
    }
    const target = event.target.closest("#btn-nuevo-bien, [data-view-target='Nuevo bien'], button[data-view='Nuevo bien']");
    if (target && !target.matches("#btn-cancelar-crear-ubicacion, #btn-cancelar-ubicacion-footer")) {
      event.preventDefault();
      setActiveView("Nuevo bien");
      return;
    }
    const backTarget = event.target.closest("#btn-cancelar-crear-bien, [data-view-target='Bienes']");
    if (backTarget) {
      event.preventDefault();
      setActiveView("Bienes");
      return;
    }
    const nuevaCatTarget = event.target.closest("#btn-nueva-categoria, [data-view-target='Nueva categoría'], button[data-view='Nueva categoría']");
    if (nuevaCatTarget) {
      event.preventDefault();
      setActiveView("Nueva categoría");
      return;
    }
    const cancelCatTarget = event.target.closest("#btn-cancelar-crear-categoria, [data-view-target='Categorías']");
    if (cancelCatTarget) {
      event.preventDefault();
      setActiveView("Categorías");
      return;
    }
    const quickUbiTarget = event.target.closest("#btn-quick-nueva-ubicacion");
    if (quickUbiTarget) {
      event.preventDefault();
      configureNuevaUbicacionReturnTarget("Nuevo bien");
      setActiveView("Nueva ubicación");
      document.querySelector("#location-name")?.focus();
      return;
    }
    const nuevaUbiTarget = event.target.closest("#btn-nueva-ubicacion, [data-view-target='Nueva ubicación'], button[data-view='Nueva ubicación']");
    if (nuevaUbiTarget) {
      event.preventDefault();
      configureNuevaUbicacionReturnTarget("Ubicaciones");
      setActiveView("Nueva ubicación");
      document.querySelector("#location-name")?.focus();
      return;
    }
    const cancelUbiTarget = event.target.closest("#btn-cancelar-crear-ubicacion, #btn-cancelar-ubicacion-footer, [data-view-target='Ubicaciones']");
    if (cancelUbiTarget) {
      event.preventDefault();
      const targetView = ubicacionReturnView || "Ubicaciones";
      configureNuevaUbicacionReturnTarget("Ubicaciones");
      setActiveView(targetView);
      return;
    }
    const genericTarget = event.target.closest("[data-view-target]");
    if (genericTarget && genericTarget.dataset.viewTarget) {
      event.preventDefault();
      setActiveView(genericTarget.dataset.viewTarget);
    }
  });

  const formCrearBien = document.querySelector("#form-crear-bien");
  const groupSelectCat = document.querySelector("#group-select-category");
  const groupNewCat = document.querySelector("#group-new-category");
  const catSelect = document.querySelector("#asset-category");
  const newCatInput = document.querySelector("#asset-new-category");
  const btnModeExisting = document.querySelector("#btn-mode-existing");
  const btnModeNew = document.querySelector("#btn-mode-new");
  const btnCancelNewCat = document.querySelector("#btn-cancel-new-cat");

  function switchToNewCategoryMode() {
    if (btnModeNew) {
      btnModeNew.classList.add("is-active");
      btnModeNew.setAttribute("aria-selected", "true");
    }
    if (btnModeExisting) {
      btnModeExisting.classList.remove("is-active");
      btnModeExisting.setAttribute("aria-selected", "false");
    }
    if (groupSelectCat) {
      groupSelectCat.hidden = true;
      groupSelectCat.setAttribute("hidden", "");
      groupSelectCat.style.display = "none";
    }
    if (groupNewCat) {
      groupNewCat.hidden = false;
      groupNewCat.removeAttribute("hidden");
      groupNewCat.style.display = "flex";
      groupNewCat.style.flexDirection = "column";
    }
    if (newCatInput) {
      newCatInput.focus();
    }
  }

  function switchToSelectCategoryMode() {
    if (btnModeExisting) {
      btnModeExisting.classList.add("is-active");
      btnModeExisting.setAttribute("aria-selected", "true");
    }
    if (btnModeNew) {
      btnModeNew.classList.remove("is-active");
      btnModeNew.setAttribute("aria-selected", "false");
    }
    if (groupNewCat) {
      groupNewCat.hidden = true;
      groupNewCat.setAttribute("hidden", "");
      groupNewCat.style.display = "none";
    }
    if (newCatInput) {
      newCatInput.value = "";
    }
    if (groupSelectCat) {
      groupSelectCat.hidden = false;
      groupSelectCat.removeAttribute("hidden");
      groupSelectCat.style.display = "block";
    }
    if (catSelect && catSelect.value === "__NEW__") {
      catSelect.value = "";
    }
  }

  if (btnModeExisting) {
    btnModeExisting.addEventListener("click", () => {
      switchToSelectCategoryMode();
      catSelect?.focus();
    });
  }

  if (btnModeNew) {
    btnModeNew.addEventListener("click", () => {
      switchToNewCategoryMode();
    });
  }

  if (btnCancelNewCat) {
    btnCancelNewCat.addEventListener("click", () => {
      switchToSelectCategoryMode();
      catSelect?.focus();
    });
  }

  if (catSelect) {
    catSelect.addEventListener("change", () => {
      if (catSelect.value === "__NEW__") {
        switchToNewCategoryMode();
      }
    });
  }

  if (newCatInput) {
    newCatInput.addEventListener("input", () => {
      if (newCatInput.value.trim().length > 0) {
        if (btnModeNew && !btnModeNew.classList.contains("is-active")) {
          btnModeNew.classList.add("is-active");
          btnModeNew.setAttribute("aria-selected", "true");
        }
        if (btnModeExisting) {
          btnModeExisting.classList.remove("is-active");
          btnModeExisting.setAttribute("aria-selected", "false");
        }
      }
    });
  }

  const cancelBienBtn = document.querySelector("#btn-cancelar-crear-bien");
  if (cancelBienBtn) {
    cancelBienBtn.addEventListener("click", () => {
      formCrearBien?.reset();
      switchToSelectCategoryMode();
    });
  }

  if (formCrearBien) {
    formCrearBien.addEventListener("submit", async (e) => {
      e.preventDefault();
      const codeInput = formCrearBien.querySelector("#asset-code");
      const nameInput = formCrearBien.querySelector("#asset-name");
      const locSelect = formCrearBien.querySelector("#asset-location");
      const submitBtn = formCrearBien.querySelector("#btn-submit-bien");

      const codeVal = codeInput?.value?.trim() || "";
      const nameVal = nameInput?.value?.trim() || "";
      const newCatVal = newCatInput?.value?.trim() || "";
      const catVal = catSelect?.value;
      const isNewCat = Boolean(newCatVal) ||
        Boolean(btnModeNew?.classList.contains("is-active")) ||
        (catVal === "__NEW__") ||
        (groupNewCat && !groupNewCat.hidden && groupNewCat.style.display !== "none");

      if (!codeVal || codeVal.length < 3) {
        showToast("El código interno es obligatorio (mínimo 3 caracteres)");
        codeInput?.focus();
        return;
      }
      if (!nameVal || nameVal.length < 3) {
        showToast("La denominación / nombre es obligatoria (mínimo 3 caracteres)");
        nameInput?.focus();
        return;
      }

      const rawLocVal = String(locSelect?.value || "");
      let payload = {
        internal_code: codeVal,
        name: nameVal,
        location_id: rawLocVal && !rawLocVal.startsWith("veh:") ? Number(rawLocVal) : null,
      };
      if (rawLocVal.startsWith("veh:")) {
        payload.destination_vehicle_asset_id = Number(rawLocVal.slice(4));
      }

      if (isNewCat) {
        if (!newCatVal || newCatVal.length < 3) {
          showToast("Ingrese el nombre de la nueva categoría (mínimo 3 caracteres)");
          newCatInput?.focus();
          return;
        }
        payload.new_category_name = newCatVal;
      } else {
        if (!catVal || catVal === "__NEW__") {
          showToast("Seleccione una categoría o cree una nueva (*)");
          catSelect?.focus();
          return;
        }
        payload.category_id = Number(catVal);
      }

      const origBtnText = submitBtn ? submitBtn.innerHTML : "";
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span aria-hidden="true">⏳</span> Registrando bien…`;
      }

      try {
        const response = await fetch("/inventory/assets", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
          },
          body: JSON.stringify(payload),
          credentials: "same-origin",
        });

        if (!response.ok) {
          let errorMsg = "No se pudo registrar el bien.";
          try {
            const errData = await response.json();
            errorMsg = extractApiErrorMessage(errData, "No se pudo registrar el bien.");
          } catch (_) {}
          showToast(`Error: ${errorMsg}`);
          return;
        }

        const successMsg = isNewCat
          ? `Bien "${nameVal}" y categoría "${newCatVal}" registrados con éxito`
          : `Bien "${nameVal}" registrado correctamente`;
        showToast(successMsg);

        formCrearBien.reset();
        switchToSelectCategoryMode();
        await checkApiConnection();
        setActiveView("Bienes");
      } catch (_err) {
        const successMsg = isNewCat
          ? `Bien "${nameVal}" y categoría "${newCatVal}" registrados (modo local)`
          : `Bien "${nameVal}" registrado (modo local)`;
        showToast(successMsg);
        formCrearBien.reset();
        switchToSelectCategoryMode();
        setActiveView("Bienes");
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = origBtnText;
        }
      }
    });
  }

  const formCrearCategoria = document.querySelector("#form-crear-categoria");
  if (formCrearCategoria) {
    formCrearCategoria.addEventListener("submit", async (e) => {
      e.preventDefault();
      const nameInput = formCrearCategoria.querySelector("#category-name");
      const nameVal = nameInput?.value?.trim();
      if (!nameVal || nameVal.length < 3) {
        showToast("Complete el nombre de la categoría (mínimo 3 caracteres)");
        nameInput?.focus();
        return;
      }

      const submitBtn = formCrearCategoria.querySelector("#btn-submit-categoria, button[type='submit']");
      const origText = submitBtn ? submitBtn.innerHTML : "";
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span aria-hidden="true">⏳</span> Guardando…`;
      }

      try {
        const response = await fetch("/inventory/categories", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ name: nameVal }),
          credentials: "same-origin",
        });

        if (!response.ok) {
          let errDetail = "La categoría ya existe o no se pudo crear";
          try {
            const errJson = await response.json();
            errDetail = extractApiErrorMessage(errJson, errDetail);
          } catch (_) {}
          showToast(`Error: ${errDetail}`);
          return;
        }

        showToast(`Categoría "${nameVal}" registrada correctamente`);
        formCrearCategoria.reset();
        await checkApiConnection();
        setActiveView("Categorías");
      } catch (_err) {
        showToast(`Categoría "${nameVal}" registrada (modo local)`);
        formCrearCategoria.reset();
        setActiveView("Categorías");
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = origText;
        }
      }
    });
  }

  const bienesSearchInput = document.querySelector("#bienes-search-input");
  if (bienesSearchInput) {
    bienesSearchInput.addEventListener("input", (e) => {
      const q = e.target.value;
      if (window.DashboardRenderer && typeof window.DashboardRenderer.setBienesQuery === "function") {
        window.DashboardRenderer.setBienesQuery(q);
      }
    });
  }

  const bienesTabs = document.querySelectorAll("#view-bienes .table-tabs button");
  bienesTabs.forEach(btn => {
    btn.addEventListener("click", () => {
      bienesTabs.forEach(b => {
        b.classList.remove("is-active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("is-active");
      btn.setAttribute("aria-selected", "true");
      const filter = btn.dataset.filter || "all";
      if (window.DashboardRenderer && typeof window.DashboardRenderer.setBienesFilter === "function") {
        window.DashboardRenderer.setBienesFilter(filter);
      }
    });
  });

  const catSearchInput = document.querySelector("#categorias-search-input");
  if (catSearchInput) {
    catSearchInput.addEventListener("input", (e) => {
      const q = e.target.value;
      if (window.DashboardRenderer && typeof window.DashboardRenderer.setCategoriasQuery === "function") {
        window.DashboardRenderer.setCategoriasQuery(q);
      }
    });
  }

  // --- VISTA Y FORMULARIO: UBICACIONES Y NUEVA UBICACIÓN ---
  const assetLocationSelect = document.querySelector("#asset-location");
  if (assetLocationSelect) {
    lastValidAssetLocationValue = assetLocationSelect.value !== "__NEW__" ? assetLocationSelect.value : "";
    assetLocationSelect.addEventListener("change", () => {
      if (assetLocationSelect.value === "__NEW__") {
        assetLocationSelect.value = lastValidAssetLocationValue;
        configureNuevaUbicacionReturnTarget("Nuevo bien");
        setActiveView("Nueva ubicación");
        document.querySelector("#location-name")?.focus();
      } else {
        lastValidAssetLocationValue = assetLocationSelect.value;
      }
    });
  }

  const formCrearUbicacion = document.querySelector("#form-crear-ubicacion");
  const locationTypeSelect = document.querySelector("#location-type");
  const groupContainerAsset = document.querySelector("#group-location-container-asset");
  const locationContainerAssetSelect = document.querySelector("#location-container-asset");

  function syncLocationTypeFields() {
    const isVehiculo = locationTypeSelect?.value === "VEHICULO";
    if (groupContainerAsset) {
      groupContainerAsset.hidden = !isVehiculo;
      if (isVehiculo) {
        groupContainerAsset.removeAttribute("hidden");
        groupContainerAsset.style.display = "flex";
        groupContainerAsset.style.flexDirection = "column";
      } else {
        groupContainerAsset.setAttribute("hidden", "");
        groupContainerAsset.style.display = "none";
      }
    }
    if (locationContainerAssetSelect) {
      locationContainerAssetSelect.required = isVehiculo;
      if (!isVehiculo) {
        locationContainerAssetSelect.value = "";
      }
    }
  }

  if (locationTypeSelect) {
    locationTypeSelect.addEventListener("change", syncLocationTypeFields);
  }

  function resetLocationForm() {
    formCrearUbicacion?.reset();
    if (locationTypeSelect) {
      locationTypeSelect.value = "FISICA";
    }
    syncLocationTypeFields();
  }

  const cancelUbicacionBtn = document.querySelector("#btn-cancelar-crear-ubicacion");
  const cancelUbicacionFooterBtn = document.querySelector("#btn-cancelar-ubicacion-footer");
  if (cancelUbicacionBtn) {
    cancelUbicacionBtn.addEventListener("click", resetLocationForm);
  }
  if (cancelUbicacionFooterBtn) {
    cancelUbicacionFooterBtn.addEventListener("click", resetLocationForm);
  }

  function selectCreatedLocationInAssetForm(createdLoc) {
    const locSelect = document.querySelector("#asset-location");
    if (!locSelect || !createdLoc || createdLoc.id === undefined || createdLoc.id === null) return;
    const targetVal = String(createdLoc.id);
    const exists = Array.from(locSelect.options || []).some(opt => String(opt.value) === targetVal);
    if (!exists) {
      const opt = document.createElement("option");
      opt.value = targetVal;
      opt.textContent = createdLoc.name || `Ubicación #${targetVal}`;
      const newOpt = locSelect.querySelector("option[value='__NEW__']");
      if (newOpt && typeof locSelect.insertBefore === "function") {
        locSelect.insertBefore(opt, newOpt);
      } else if (typeof locSelect.appendChild === "function") {
        locSelect.appendChild(opt);
      }
    }
    locSelect.value = targetVal;
    lastValidAssetLocationValue = targetVal;
  }

  if (formCrearUbicacion) {
    formCrearUbicacion.addEventListener("submit", async (e) => {
      e.preventDefault();
      const nameInput = formCrearUbicacion.querySelector("#location-name");
      const typeInput = formCrearUbicacion.querySelector("#location-type");
      const containerInput = formCrearUbicacion.querySelector("#location-container-asset");
      const descInput = formCrearUbicacion.querySelector("#location-description");
      const submitBtn = formCrearUbicacion.querySelector("#btn-submit-ubicacion, button[type='submit']");

      const nameVal = nameInput?.value?.trim() || "";
      const locTypeVal = (typeInput?.value || "FISICA").toUpperCase();
      const containerVal = containerInput?.value || "";
      const descVal = descInput?.value?.trim() || "";

      if (!nameVal || nameVal.length < 3) {
        showToast("Complete el nombre de la ubicación (mínimo 3 caracteres)");
        nameInput?.focus();
        return;
      }

      if (locTypeVal === "VEHICULO" && (!containerVal || Number(containerVal) <= 0)) {
        showToast("Seleccione el bien contenedor para la ubicación vehicular");
        containerInput?.focus();
        return;
      }

      const payload = {
        name: nameVal,
        location_type: locTypeVal === "VEHICULO" ? "VEHICULO" : "FISICA",
        container_asset_id: locTypeVal === "VEHICULO" ? Number(containerVal) : null,
        description: descVal || null,
        active: true,
      };

      const origText = submitBtn ? submitBtn.innerHTML : "";
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span aria-hidden="true">⏳</span> Guardando…`;
      }

      const targetReturnView = ubicacionReturnView || "Ubicaciones";

      try {
        const response = await fetch("/inventory/locations", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify(payload),
          credentials: "same-origin",
        });

        if (!response.ok) {
          let errDetail = "La ubicación ya existe o no se pudo crear";
          try {
            const errJson = await response.json();
            errDetail = extractApiErrorMessage(errJson, errDetail);
          } catch (_) {}
          showToast(`Error: ${errDetail}`);
          return;
        }

        let createdLoc = null;
        try {
          createdLoc = await response.json();
        } catch (_) {}

        showToast(`Ubicación "${nameVal}" registrada correctamente`);
        resetLocationForm();
        await checkApiConnection();
        if (createdLoc) {
          selectCreatedLocationInAssetForm(createdLoc);
        }
        configureNuevaUbicacionReturnTarget("Ubicaciones");
        setActiveView(targetReturnView);
      } catch (_err) {
        const fallbackLoc = { id: Date.now(), name: nameVal, location_type: payload.location_type };
        showToast(`Ubicación "${nameVal}" registrada (modo local)`);
        resetLocationForm();
        selectCreatedLocationInAssetForm(fallbackLoc);
        configureNuevaUbicacionReturnTarget("Ubicaciones");
        setActiveView(targetReturnView);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = origText;
        }
      }
    });
  }

  const ubicacionesSearchInput = document.querySelector("#ubicaciones-search-input");
  if (ubicacionesSearchInput) {
    ubicacionesSearchInput.addEventListener("input", (e) => {
      const q = e.target.value || "";
      if (window.DashboardRenderer && typeof window.DashboardRenderer.setUbicacionesQuery === "function" && window.DashboardRenderer.getRealData?.()) {
        window.DashboardRenderer.setUbicacionesQuery(q);
      } else {
        const panel = ubicacionesSearchInput.closest(".panel");
        const cleanQ = q.trim().toLowerCase();
        panel?.querySelectorAll("tbody tr").forEach(row => {
          row.hidden = cleanQ ? !row.textContent.toLowerCase().includes(cleanQ) : false;
        });
      }
    });
  }

  const ubicacionBienesSearchInput = document.querySelector("#ubicacion-bienes-search-input");
  if (ubicacionBienesSearchInput) {
    ubicacionBienesSearchInput.addEventListener("input", (e) => {
      const q = e.target.value || "";
      if (window.DashboardRenderer && typeof window.DashboardRenderer.setUbicacionBienesQuery === "function") {
        window.DashboardRenderer.setUbicacionBienesQuery(q);
      }
    });
  }

  const categoriaBienesSearchInput = document.querySelector("#categoria-bienes-search-input");
  if (categoriaBienesSearchInput) {
    categoriaBienesSearchInput.addEventListener("input", (e) => {
      const q = e.target.value || "";
      if (window.DashboardRenderer && typeof window.DashboardRenderer.setCategoriaBienesQuery === "function") {
        window.DashboardRenderer.setCategoriaBienesQuery(q);
      }
    });
  }

  const vehiculosSearchInput = document.querySelector("#vehiculos-search-input");
  if (vehiculosSearchInput) {
    vehiculosSearchInput.addEventListener("input", (e) => {
      const q = e.target.value || "";
      if (window.DashboardRenderer && typeof window.DashboardRenderer.setVehiculosQuery === "function") {
        window.DashboardRenderer.setVehiculosQuery(q);
      }
    });
  }

  const ubicacionesTabs = document.querySelectorAll("#view-ubicaciones .table-tabs button");
  ubicacionesTabs.forEach(btn => {
    btn.addEventListener("click", () => {
      ubicacionesTabs.forEach(b => {
        b.classList.remove("is-active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("is-active");
      btn.setAttribute("aria-selected", "true");
      const filter = btn.dataset.filter || "all";
      if (window.DashboardRenderer && typeof window.DashboardRenderer.setUbicacionesFilter === "function" && window.DashboardRenderer.getRealData?.()) {
        window.DashboardRenderer.setUbicacionesFilter(filter);
      } else {
        const panel = btn.closest(".panel");
        panel?.querySelectorAll("tbody tr").forEach(row => {
          row.hidden = filter === "all" ? false : (row.dataset.type !== filter);
        });
      }
    });
  });

  // --- MODAL: MOVER BIEN DE UBICACIÓN ---
  const modalMover = document.querySelector("#modal-mover-bien");
  const formMoverBien = document.querySelector("#form-mover-bien");
  const moverAssetIdInput = document.querySelector("#mover-asset-id");
  const moverBienNombre = document.querySelector("#mover-bien-nombre");
  const moverBienCodigo = document.querySelector("#mover-bien-codigo");
  const moverOrigenDisplay = document.querySelector("#mover-origen-display");
  const moverDestinoSelect = document.querySelector("#mover-destino-select");
  const moverNuevoDestinoInput = document.querySelector("#mover-nuevo-destino-nombre");
  const moverMotivoInput = document.querySelector("#mover-motivo");
  const moverObsInput = document.querySelector("#mover-observaciones");
  const btnDestModeExisting = document.querySelector("#btn-dest-mode-existing");
  const btnDestModeNew = document.querySelector("#btn-dest-mode-new");
  const panelSelectDestino = document.querySelector("#panel-select-destino");
  const panelNewDestino = document.querySelector("#panel-new-destino");
  const btnCancelNewDestino = document.querySelector("#btn-cancel-new-destino");
  const btnCerrarModalMover = document.querySelector("#btn-cerrar-modal-mover");
  const btnCancelarMover = document.querySelector("#btn-cancelar-mover");
  const btnConfirmarTraslado = document.querySelector("#btn-confirmar-traslado");

  function switchToDestExistingMode() {
    if (btnDestModeExisting) {
      btnDestModeExisting.classList.add("is-active");
      btnDestModeExisting.setAttribute("aria-selected", "true");
    }
    if (btnDestModeNew) {
      btnDestModeNew.classList.remove("is-active");
      btnDestModeNew.setAttribute("aria-selected", "false");
    }
    if (panelSelectDestino) {
      panelSelectDestino.hidden = false;
      panelSelectDestino.removeAttribute("hidden");
      panelSelectDestino.style.display = "block";
    }
    if (panelNewDestino) {
      panelNewDestino.hidden = true;
      panelNewDestino.setAttribute("hidden", "");
      panelNewDestino.style.display = "none";
    }
    if (moverNuevoDestinoInput) {
      moverNuevoDestinoInput.required = false;
      moverNuevoDestinoInput.value = "";
    }
    if (moverDestinoSelect) {
      moverDestinoSelect.required = true;
      if (moverDestinoSelect.value === "__NEW__") {
        moverDestinoSelect.value = "";
      }
    }
  }

  function switchToDestNewMode() {
    if (btnDestModeNew) {
      btnDestModeNew.classList.add("is-active");
      btnDestModeNew.setAttribute("aria-selected", "true");
    }
    if (btnDestModeExisting) {
      btnDestModeExisting.classList.remove("is-active");
      btnDestModeExisting.setAttribute("aria-selected", "false");
    }
    if (panelSelectDestino) {
      panelSelectDestino.hidden = true;
      panelSelectDestino.setAttribute("hidden", "");
      panelSelectDestino.style.display = "none";
    }
    if (panelNewDestino) {
      panelNewDestino.hidden = false;
      panelNewDestino.removeAttribute("hidden");
      panelNewDestino.style.display = "flex";
      panelNewDestino.style.flexDirection = "column";
    }
    if (moverDestinoSelect) {
      moverDestinoSelect.required = false;
    }
    if (moverNuevoDestinoInput) {
      moverNuevoDestinoInput.required = true;
      moverNuevoDestinoInput.focus();
    }
  }

  function closeMoverModal() {
    if (modalMover) {
      if (typeof modalMover.close === "function") {
        modalMover.close();
      } else {
        modalMover.hidden = true;
        modalMover.removeAttribute("open");
      }
    }
    if (formMoverBien) formMoverBien.reset();
    switchToDestExistingMode();
  }

  function openMoverModalForAsset(assetId) {
    if (!modalMover) return;
    const realData = window.DashboardRenderer && typeof window.DashboardRenderer.getRealData === "function"
      ? window.DashboardRenderer.getRealData()
      : null;
    const asset = realData?.assets?.find(a => a.id === assetId);
    if (!asset) {
      showToast("No se encontró el bien seleccionado");
      return;
    }

    const locMap = new Map((realData.locations || []).map(l => [l.id, l.name]));
    const currentLocName = asset.location_id !== null
      ? (locMap.get(asset.location_id) || "Ubicación desconocida")
      : "Sin asignación fija (Depósito)";

    if (moverAssetIdInput) moverAssetIdInput.value = asset.id;
    if (moverBienNombre) moverBienNombre.textContent = asset.name;
    if (moverBienCodigo) moverBienCodigo.textContent = asset.internal_code;
    if (moverOrigenDisplay) moverOrigenDisplay.textContent = currentLocName;
    if (moverMotivoInput) moverMotivoInput.value = "";
    if (moverObsInput) moverObsInput.value = "";
    if (moverNuevoDestinoInput) moverNuevoDestinoInput.value = "";

    // Populate destination dropdown with physical locations and eligible vehicles, excluding current location and self
    if (moverDestinoSelect) {
      const destItems = buildDestinationOptionItems({
        locations: realData.locations || [],
        assets: realData.assets || [],
        categories: realData.categories || [],
        excludeLocationId: asset.location_id,
        excludeAssetId: asset.id,
      });
      const options = [
        '<option value="" disabled selected>Seleccione el destino…</option>',
        ...destItems.map(
          item =>
            `<option value="${escapeOptionHtml(item.value)}">${escapeOptionHtml(item.text)}</option>`
        ),
        '<option value="__NEW__" class="opt-new-category">+ Crear nueva ubicación…</option>'
      ];
      moverDestinoSelect.innerHTML = options.join("");
      moverDestinoSelect.value = "";
    }

    switchToDestExistingMode();

    if (typeof modalMover.showModal === "function") {
      modalMover.showModal();
    } else {
      modalMover.hidden = false;
      modalMover.setAttribute("open", "");
    }
    moverDestinoSelect?.focus();
  }

  if (btnDestModeExisting) {
    btnDestModeExisting.addEventListener("click", () => {
      switchToDestExistingMode();
      moverDestinoSelect?.focus();
    });
  }

  if (btnDestModeNew) {
    btnDestModeNew.addEventListener("click", () => {
      switchToDestNewMode();
    });
  }

  if (btnCancelNewDestino) {
    btnCancelNewDestino.addEventListener("click", () => {
      switchToDestExistingMode();
      moverDestinoSelect?.focus();
    });
  }

  if (moverDestinoSelect) {
    moverDestinoSelect.addEventListener("change", () => {
      if (moverDestinoSelect.value === "__NEW__") {
        switchToDestNewMode();
      }
    });
  }

  if (btnCerrarModalMover) {
    btnCerrarModalMover.addEventListener("click", closeMoverModal);
  }
  if (btnCancelarMover) {
    btnCancelarMover.addEventListener("click", closeMoverModal);
  }

  document.addEventListener("click", (event) => {
    const moverBtn = event.target.closest(".btn-mover-bien");
    if (moverBtn && moverBtn.dataset.assetId) {
      event.preventDefault();
      openMoverModalForAsset(Number(moverBtn.dataset.assetId));
    }
  });

  if (formMoverBien) {
    formMoverBien.addEventListener("submit", async (e) => {
      e.preventDefault();
      const assetId = Number(moverAssetIdInput?.value);
      if (!assetId) {
        showToast("Error: No se identificó el bien a mover.");
        return;
      }

      const isNew = Boolean(btnDestModeNew?.classList.contains("is-active")) ||
        (moverDestinoSelect?.value === "__NEW__") ||
        (panelNewDestino && !panelNewDestino.hidden && panelNewDestino.style.display !== "none");

      let destinationId = null;
      let destinationVehicleAssetId = null;
      let destinationName = "";
      const reasonVal = moverMotivoInput?.value?.trim() || "";
      const obsVal = moverObsInput?.value?.trim() || "";

      const origBtnText = btnConfirmarTraslado ? btnConfirmarTraslado.innerHTML : "";
      if (btnConfirmarTraslado) {
        btnConfirmarTraslado.disabled = true;
        btnConfirmarTraslado.innerHTML = `<span aria-hidden="true">⏳</span> Procesando traslado…`;
      }

      try {
        if (isNew) {
          const newName = moverNuevoDestinoInput?.value?.trim() || "";
          if (!newName || newName.length < 3) {
            showToast("Ingresá el nombre de la nueva ubicación (mínimo 3 caracteres)");
            moverNuevoDestinoInput?.focus();
            if (btnConfirmarTraslado) {
              btnConfirmarTraslado.disabled = false;
              btnConfirmarTraslado.innerHTML = origBtnText;
            }
            return;
          }

          // Step 1: Create the new location
          const createLocResponse = await fetch("/inventory/locations", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Accept": "application/json",
            },
            body: JSON.stringify({
              name: newName,
              location_type: "FISICA",
              active: true,
            }),
            credentials: "same-origin",
          });

          if (!createLocResponse.ok) {
            let errorMsg = "No se pudo crear la nueva ubicación.";
            try {
              const errData = await createLocResponse.json();
              errorMsg = extractApiErrorMessage(errData, errorMsg);
            } catch (_) {}
            showToast(`Error: ${errorMsg}`);
            if (btnConfirmarTraslado) {
              btnConfirmarTraslado.disabled = false;
              btnConfirmarTraslado.innerHTML = origBtnText;
            }
            return;
          }

          const createdLoc = await createLocResponse.json();
          destinationId = createdLoc.id;
          destinationName = createdLoc.name;
        } else {
          const destVal = String(moverDestinoSelect?.value || "");
          if (!destVal || destVal === "__NEW__") {
            showToast("Seleccione una ubicación de destino (*)");
            moverDestinoSelect?.focus();
            if (btnConfirmarTraslado) {
              btnConfirmarTraslado.disabled = false;
              btnConfirmarTraslado.innerHTML = origBtnText;
            }
            return;
          }
          if (destVal.startsWith("veh:")) {
            destinationVehicleAssetId = Number(destVal.slice(4));
          } else {
            destinationId = Number(destVal);
          }
          destinationName = moverDestinoSelect.options[moverDestinoSelect.selectedIndex]?.textContent?.replace(/^\s*-\s*/, "") || "la ubicación destino";
        }

        const transferBody = {
          reason: reasonVal || null,
          observations: obsVal || null,
        };
        if (destinationVehicleAssetId !== null) {
          transferBody.destination_vehicle_asset_id = destinationVehicleAssetId;
        } else {
          transferBody.destination_location_id = destinationId;
        }

        // Step 2: Transfer the asset to the destination
        const transferResponse = await fetch(`/inventory/assets/${assetId}/transfers`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
          },
          body: JSON.stringify(transferBody),
          credentials: "same-origin",
        });

        if (!transferResponse.ok) {
          let errorMsg = "No se pudo trasladar el bien.";
          try {
            const errData = await transferResponse.json();
            errorMsg = extractApiErrorMessage(errData, errorMsg);
          } catch (_) {}
          showToast(`Error: ${errorMsg}`);
          return;
        }

        closeMoverModal();
        showToast(`Bien trasladado exitosamente a "${destinationName}".`);
        await checkApiConnection();
      } catch (err) {
        showToast("Error de conexión al trasladar el bien.");
      } finally {
        if (btnConfirmarTraslado) {
          btnConfirmarTraslado.disabled = false;
          btnConfirmarTraslado.innerHTML = origBtnText;
        }
      }
    });
  }

  const movSearchInput = document.querySelector("#movimientos-search-input");
  if (movSearchInput) {
    movSearchInput.addEventListener("input", (e) => {
      const q = e.target.value;
      if (window.DashboardRenderer && typeof window.DashboardRenderer.setMovimientosQuery === "function") {
        window.DashboardRenderer.setMovimientosQuery(q);
      }
    });
  }

  const movTabs = document.querySelectorAll("#view-movimientos .table-tabs button");
  movTabs.forEach(btn => {
    btn.addEventListener("click", () => {
      movTabs.forEach(b => {
        b.classList.remove("is-active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("is-active");
      btn.setAttribute("aria-selected", "true");
      const filter = btn.dataset.filter || "all";
      if (window.DashboardRenderer && typeof window.DashboardRenderer.setMovimientosFilter === "function") {
        window.DashboardRenderer.setMovimientosFilter(filter);
      }
    });
  });

  // --- GESTIÓN DE ACCESOS (SOLICITUDES PENDIENTES E INVITACIONES EMITIDAS) ---
  const accessApiClient =
    window.FireApiClient && typeof window.FireApiClient.createApiClient === "function"
      ? window.FireApiClient.createApiClient()
      : null;

  const accessTabRequests = document.querySelector("#tab-access-requests");
  const accessTabInvitations = document.querySelector("#tab-access-invitations");
  const accessPanelRequests = document.querySelector("#panel-access-requests");
  const accessPanelInvitations = document.querySelector("#panel-access-invitations");
  const accessRequestsCountEl = document.querySelector("#access-requests-count");
  const accessInvitationsCountEl = document.querySelector("#access-invitations-count");
  const accessRequestsTbody = document.querySelector("#access-requests-tbody");
  const accessInvitationsTbody = document.querySelector("#access-invitations-tbody");
  const accessFeedbackBanner = document.querySelector("#access-feedback-banner");
  const accessSearchInput = document.querySelector("#access-search-input");
  const btnRefreshAccess = document.querySelector("#btn-refresh-access");

  const accessState = {
    activeTab: "requests",
    requests: [],
    invitations: [],
    loading: false,
    query: "",
  };

  function setAccessFeedback(message, type = "info") {
    if (!accessFeedbackBanner) return;
    if (!message) {
      accessFeedbackBanner.hidden = true;
      accessFeedbackBanner.textContent = "";
      delete accessFeedbackBanner.dataset.state;
      return;
    }
    accessFeedbackBanner.hidden = false;
    accessFeedbackBanner.textContent = message;
    accessFeedbackBanner.dataset.state = type;
    if (type === "error") {
      accessFeedbackBanner.style.borderColor = "rgba(229, 57, 53, 0.45)";
      accessFeedbackBanner.style.background = "rgba(229, 57, 53, 0.12)";
      accessFeedbackBanner.style.color = "var(--primary-hover)";
    } else if (type === "success") {
      accessFeedbackBanner.style.borderColor = "rgba(129, 199, 132, 0.35)";
      accessFeedbackBanner.style.background = "rgba(46, 125, 50, 0.14)";
      accessFeedbackBanner.style.color = "#81c784";
    } else {
      accessFeedbackBanner.style.borderColor = "var(--border)";
      accessFeedbackBanner.style.background = "var(--surface)";
      accessFeedbackBanner.style.color = "var(--text-soft)";
    }
  }

  function formatAccessDate(value) {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleString("es-AR", {
      dateStyle: "short",
      timeStyle: "short",
    });
  }

  function formatSourceLabel(source) {
    return source === "google" ? "Google OAuth" : "Correo y contraseña";
  }

  function formatInvitationStatusMeta(status) {
    switch (status) {
      case "active":
        return { label: "Activa (pendiente de uso)", pillClass: "status-pill warning" };
      case "consumed":
        return { label: "Utilizada", pillClass: "status-pill success" };
      case "expired":
        return { label: "Vencida", pillClass: "status-pill danger" };
      case "revoked":
        return { label: "Revocada / reemplazada", pillClass: "status-pill neutral" };
      default:
        return { label: String(status || "Desconocido"), pillClass: "status-pill neutral" };
    }
  }

  function renderSingleMessageRow(tbody, colSpan, message) {
    if (!tbody) return;
    tbody.replaceChildren();
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = colSpan;
    td.style.textAlign = "center";
    td.style.padding = "24px";
    td.style.color = "var(--text-soft)";
    td.textContent = message;
    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  function renderAccessRequests() {
    if (!accessRequestsTbody) return;
    if (accessRequestsCountEl) {
      accessRequestsCountEl.textContent = String(accessState.requests.length);
    }

    const q = accessState.query.trim().toLowerCase();
    const filtered = accessState.requests.filter((item) => {
      if (!q) return true;
      const sourceLabel = formatSourceLabel(item.source).toLowerCase();
      return (
        String(item.email || "").toLowerCase().includes(q) ||
        sourceLabel.includes(q) ||
        "pendiente".includes(q)
      );
    });

    if (!filtered.length) {
      renderSingleMessageRow(
        accessRequestsTbody,
        5,
        accessState.requests.length === 0
          ? "No hay solicitudes pendientes de revisión."
          : "Ninguna solicitud pendiente coincide con la búsqueda."
      );
      return;
    }

    accessRequestsTbody.replaceChildren();
    filtered.forEach((item) => {
      const tr = document.createElement("tr");
      tr.dataset.requestId = String(item.id);

      const emailTd = document.createElement("td");
      const emailStrong = document.createElement("strong");
      emailStrong.textContent = item.email;
      emailTd.appendChild(emailStrong);

      const sourceTd = document.createElement("td");
      const sourceBadge = document.createElement("span");
      sourceBadge.className = "status-pill neutral";
      sourceBadge.textContent = formatSourceLabel(item.source);
      sourceTd.appendChild(sourceBadge);

      const dateTd = document.createElement("td");
      dateTd.className = "table-muted";
      dateTd.textContent = formatAccessDate(item.requested_at);

      const statusTd = document.createElement("td");
      const statusBadge = document.createElement("span");
      statusBadge.className = "status-pill warning";
      statusBadge.textContent = "Pendiente de revisión";
      statusTd.appendChild(statusBadge);

      const actionsTd = document.createElement("td");
      const actionsWrap = document.createElement("div");
      actionsWrap.className = "table-actions";

      const approveBtn = document.createElement("button");
      approveBtn.type = "button";
      approveBtn.className = "action-button-sm";
      approveBtn.dataset.action = "approve-request";
      approveBtn.dataset.requestId = String(item.id);
      approveBtn.textContent = "Aprobar";

      const rejectBtn = document.createElement("button");
      rejectBtn.type = "button";
      rejectBtn.className = "action-button-sm danger";
      rejectBtn.dataset.action = "reject-request";
      rejectBtn.dataset.requestId = String(item.id);
      rejectBtn.textContent = "Rechazar";

      approveBtn.addEventListener("click", () =>
        handleReviewRequest(item.id, "approved", [approveBtn, rejectBtn])
      );
      rejectBtn.addEventListener("click", () =>
        handleReviewRequest(item.id, "rejected", [approveBtn, rejectBtn])
      );

      actionsWrap.append(approveBtn, rejectBtn);
      actionsTd.appendChild(actionsWrap);

      tr.append(emailTd, sourceTd, dateTd, statusTd, actionsTd);
      accessRequestsTbody.appendChild(tr);
    });
  }

  function renderAccessInvitations() {
    if (!accessInvitationsTbody) return;
    if (accessInvitationsCountEl) {
      accessInvitationsCountEl.textContent = String(accessState.invitations.length);
    }

    const q = accessState.query.trim().toLowerCase();
    const filtered = accessState.invitations.filter((item) => {
      if (!q) return true;
      const meta = formatInvitationStatusMeta(item.status);
      return (
        String(item.email || "").toLowerCase().includes(q) ||
        String(item.role || "").toLowerCase().includes(q) ||
        meta.label.toLowerCase().includes(q) ||
        String(item.status || "").toLowerCase().includes(q)
      );
    });

    if (!filtered.length) {
      renderSingleMessageRow(
        accessInvitationsTbody,
        6,
        accessState.invitations.length === 0
          ? "No hay invitaciones emitidas registradas."
          : "Ninguna invitación emitida coincide con la búsqueda."
      );
      return;
    }

    accessInvitationsTbody.replaceChildren();
    filtered.forEach((item) => {
      const tr = document.createElement("tr");
      tr.dataset.invitationId = String(item.id);
      tr.dataset.status = String(item.status || "");

      const emailTd = document.createElement("td");
      const emailStrong = document.createElement("strong");
      emailStrong.textContent = item.email;
      emailTd.appendChild(emailStrong);

      const roleTd = document.createElement("td");
      const roleBadge = document.createElement("span");
      roleBadge.className = "badge-role";
      roleBadge.textContent = item.role || "SUPERVISOR";
      roleTd.appendChild(roleBadge);

      const createdTd = document.createElement("td");
      createdTd.className = "table-muted";
      createdTd.textContent = formatAccessDate(item.created_at);

      const expiresTd = document.createElement("td");
      expiresTd.className = "table-muted";
      expiresTd.textContent = formatAccessDate(item.expires_at);

      const statusTd = document.createElement("td");
      const meta = formatInvitationStatusMeta(item.status);
      const statusBadge = document.createElement("span");
      statusBadge.className = meta.pillClass;
      statusBadge.textContent = meta.label;
      statusTd.appendChild(statusBadge);
      if (Number(item.reissue_count) > 0) {
        const sub = document.createElement("small");
        sub.className = "table-muted";
        sub.style.display = "block";
        sub.style.marginTop = "3px";
        sub.textContent = `Reemisiones: ${item.reissue_count}/3`;
        statusTd.appendChild(sub);
      }

      const actionsTd = document.createElement("td");
      if (item.can_reissue === true && item.registration_request_id != null) {
        const actionsWrap = document.createElement("div");
        actionsWrap.className = "table-actions";
        const reissueBtn = document.createElement("button");
        reissueBtn.type = "button";
        reissueBtn.className = "action-button-sm";
        reissueBtn.dataset.action = "reissue-invitation";
        reissueBtn.dataset.requestId = String(item.registration_request_id);
        reissueBtn.textContent = "Reemitir";
        reissueBtn.addEventListener("click", () =>
          handleReissueInvitation(item.registration_request_id, reissueBtn)
        );
        actionsWrap.appendChild(reissueBtn);
        actionsTd.appendChild(actionsWrap);
      } else {
        const info = document.createElement("small");
        info.className = "table-muted";
        if (item.status === "consumed") {
          info.textContent = "Registrado";
        } else if (item.status === "active") {
          info.textContent = "Vigente";
        } else if (Number(item.reissue_count) >= 3) {
          info.textContent = "Límite alcanzado";
        } else {
          info.textContent = "Sin acciones";
        }
        actionsTd.appendChild(info);
      }

      tr.append(emailTd, roleTd, createdTd, expiresTd, statusTd, actionsTd);
      accessInvitationsTbody.appendChild(tr);
    });
  }

  function switchAccessTab(tabName) {
    const isRequests = tabName !== "invitations";
    accessState.activeTab = isRequests ? "requests" : "invitations";

    if (accessTabRequests) {
      accessTabRequests.classList.toggle("is-active", isRequests);
      accessTabRequests.setAttribute("aria-selected", String(isRequests));
    }
    if (accessTabInvitations) {
      accessTabInvitations.classList.toggle("is-active", !isRequests);
      accessTabInvitations.setAttribute("aria-selected", String(!isRequests));
    }
    if (accessPanelRequests) {
      accessPanelRequests.hidden = !isRequests;
    }
    if (accessPanelInvitations) {
      accessPanelInvitations.hidden = isRequests;
    }
  }

  async function loadAccessManagementData(options = {}) {
    if (!accessRequestsTbody || !accessInvitationsTbody) return;
    accessState.loading = true;
    if (!options.preserveFeedback) {
      setAccessFeedback("", "info");
    }
    renderSingleMessageRow(accessRequestsTbody, 5, "Cargando solicitudes pendientes…");
    renderSingleMessageRow(accessInvitationsTbody, 6, "Cargando invitaciones emitidas…");

    try {
      let requestsData;
      let invitationsData;

      if (accessApiClient) {
        const [reqRes, invRes] = await Promise.all([
          accessApiClient.invitations.listRequests(),
          accessApiClient.invitations.listInvitations(),
        ]);
        requestsData = reqRes.data;
        invitationsData = invRes.data;
      } else {
        const [reqResp, invResp] = await Promise.all([
          fetch("/auth/registration-requests", { credentials: "same-origin" }),
          fetch("/auth/invitations", { credentials: "same-origin" }),
        ]);
        if (!reqResp.ok) {
          const errJson = await reqResp.json().catch(() => ({}));
          throw new Error(extractApiErrorMessage(errJson, "No se pudieron consultar las solicitudes."));
        }
        if (!invResp.ok) {
          const errJson = await invResp.json().catch(() => ({}));
          throw new Error(extractApiErrorMessage(errJson, "No se pudieron consultar las invitaciones."));
        }
        requestsData = await reqResp.json();
        invitationsData = await invResp.json();
      }

      accessState.requests = Array.isArray(requestsData) ? requestsData : [];
      accessState.invitations = Array.isArray(invitationsData) ? invitationsData : [];
      renderAccessRequests();
      renderAccessInvitations();
    } catch (error) {
      const msg = error?.message || "No se pudo cargar la información de Gestión de accesos.";
      setAccessFeedback(msg, "error");
      renderSingleMessageRow(accessRequestsTbody, 5, msg);
      renderSingleMessageRow(accessInvitationsTbody, 6, msg);
    } finally {
      accessState.loading = false;
    }
  }

  async function handleReviewRequest(requestId, decision, buttons = []) {
    buttons.forEach((btn) => {
      if (btn) btn.disabled = true;
    });
    setAccessFeedback("Procesando decisión administrativa…", "info");

    try {
      if (accessApiClient) {
        await accessApiClient.invitations.review(requestId, decision);
      } else {
        const resp = await fetch(`/auth/registration-requests/${requestId}/review`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ decision }),
          credentials: "same-origin",
        });
        if (!resp.ok) {
          const errJson = await resp.json().catch(() => ({}));
          throw new Error(extractApiErrorMessage(errJson, "No se pudo procesar la solicitud."));
        }
      }

      const successText =
        decision === "approved"
          ? "Solicitud aprobada e invitación enviada."
          : "Solicitud rechazada.";
      setAccessFeedback(successText, "success");
      showToast(successText);
      await loadAccessManagementData({ preserveFeedback: true });
    } catch (error) {
      const errMsg = error?.message || "No se pudo procesar la solicitud.";
      setAccessFeedback(errMsg, "error");
      showToast(`Error: ${errMsg}`);
      buttons.forEach((btn) => {
        if (btn) btn.disabled = false;
      });
    }
  }

  async function handleReissueInvitation(requestId, button) {
    if (button) button.disabled = true;
    setAccessFeedback("Reemitiendo invitación…", "info");

    try {
      let respMessage = "Invitación reemitida exitosamente.";
      if (accessApiClient) {
        const res = await accessApiClient.invitations.reissue(requestId, {
          reason: "Reemisión administrativa desde Gestión de accesos",
        });
        if (res?.data?.message) {
          respMessage = res.data.message;
        }
      } else {
        const resp = await fetch(`/auth/registration-requests/${requestId}/reissue`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Idempotency-Key": `reissue-${requestId}-${Date.now()}`,
          },
          body: JSON.stringify({
            reason: "Reemisión administrativa desde Gestión de accesos",
          }),
          credentials: "same-origin",
        });
        if (!resp.ok) {
          const errJson = await resp.json().catch(() => ({}));
          throw new Error(extractApiErrorMessage(errJson, "No se pudo reemitir la invitación."));
        }
        const dataJson = await resp.json().catch(() => ({}));
        if (dataJson?.message) respMessage = dataJson.message;
      }

      setAccessFeedback(respMessage, "success");
      showToast(respMessage);
      await loadAccessManagementData({ preserveFeedback: true });
    } catch (error) {
      const errMsg = error?.message || "No se pudo reemitir la invitación.";
      setAccessFeedback(errMsg, "error");
      showToast(`Error: ${errMsg}`);
      if (button) button.disabled = false;
    }
  }

  if (accessTabRequests) {
    accessTabRequests.addEventListener("click", () => switchAccessTab("requests"));
  }
  if (accessTabInvitations) {
    accessTabInvitations.addEventListener("click", () => switchAccessTab("invitations"));
  }
  if (btnRefreshAccess) {
    btnRefreshAccess.addEventListener("click", () => loadAccessManagementData());
  }
  if (accessSearchInput) {
    accessSearchInput.addEventListener("input", (event) => {
      accessState.query = event.target.value || "";
      renderAccessRequests();
      renderAccessInvitations();
    });
  }

  window.AccessManagementController = Object.freeze({
    loadAccessManagementData,
    switchAccessTab,
    handleReviewRequest,
    handleReissueInvitation,
    getState: () => ({
      activeTab: accessState.activeTab,
      requests: [...accessState.requests],
      invitations: [...accessState.invitations],
      loading: accessState.loading,
      query: accessState.query,
    }),
  });

  const requestedView = authParams.get("view");
  const requestedTab = authParams.get("tab");
  if (requestedView === "Invitaciones" || requestedView === "Gestión de accesos") {
    switchAccessTab(requestedTab === "invitations" ? "invitations" : "requests");
    setActiveView("Invitaciones");
  }
  if (profileMountPromise && typeof profileMountPromise.then === "function") {
    profileMountPromise.then((user) => {
      const invView = document.querySelector("#view-invitaciones");
      if (user && user.role !== "ADMINISTRADOR" && invView && !invView.hidden) {
        setActiveView("Inventario general");
      }
    });
  }

  document.addEventListener("keydown", event => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); globalSearch.focus(); } });
})();

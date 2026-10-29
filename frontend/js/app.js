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

  function populateLocationOptions(locations) {
    const locSelect = document.querySelector("#asset-location");
    if (!locSelect) return;
    const currentVal = locSelect.value;
    const hasLocations = Array.isArray(locations) && locations.length > 0;
    const options = [
      `<option value="" ${!currentVal ? "selected" : ""}>Sin asignación fija (Depósito)</option>`,
      ...(hasLocations ? locations.map(l => `<option value="${l.id}">${l.name}</option>`) : [])
    ];
    locSelect.innerHTML = options.join("");
    if (currentVal && hasLocations && locations.some(l => String(l.id) === currentVal)) {
      locSelect.value = currentVal;
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
      populateLocationOptions(locations);

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
    "Categorías": "Clasificación y catálogo de bienes del cuerpo de bomberos.",
    "Nueva categoría": "Alta y registro de nueva categoría en el catálogo operativo.",
    "Ubicaciones": "Destinos operativos, cuarteles, depósitos y móviles asignados.",
    "Invitaciones": "Revisión de solicitudes de registro e invitaciones emitidas con autorización administrativa.",
    "Vehículos": "Parque automotor, autobombas, cisternas y unidades de apoyo.",
    "Responsables": "Asignación de personal a cargo de activos y equipamiento.",
    "Movimientos": "Historial de ingresos, egresos, traslados y bajas.",
    "Auditoría": "Registro de eventos del sistema y trazabilidad de acciones.",
    "Reportes": "Informes consolidados y estadísticas de inventario.",
    "Alertas": "Monitoreo preventivo y avisos de mantenimiento técnico.",
  };

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
        (isNav && view === "Nueva categoría" && button.dataset.view === "Categorías");
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
    if (button.closest("#view-invitaciones, #view-bienes, #view-movimientos")) return;
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
    if (input.closest("#view-invitaciones, #view-bienes, #view-categorias, #view-movimientos")) return;
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

  // Delegated handler ensures clicks on button, icon, or text reliably activate the target view
  document.addEventListener("click", (event) => {
    const target = event.target.closest("#btn-nuevo-bien, [data-view-target='Nuevo bien'], button[data-view='Nuevo bien']");
    if (target) {
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

      let payload = {
        internal_code: codeVal,
        name: nameVal,
        location_id: locSelect?.value ? Number(locSelect.value) : null,
      };

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

    // Populate destination dropdown, excluding current location
    if (moverDestinoSelect) {
      const availableLocations = (realData.locations || []).filter(l => l.id !== asset.location_id);
      const options = [
        '<option value="" disabled selected>Seleccione el destino…</option>',
        ...availableLocations.map(l => `<option value="${l.id}">${l.name}</option>`),
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
          if (!newName || newName.length < 2) {
            showToast("Ingresá el nombre de la nueva ubicación (mínimo 2 caracteres)");
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
          const destVal = moverDestinoSelect?.value;
          if (!destVal || destVal === "__NEW__") {
            showToast("Seleccione una ubicación de destino (*)");
            moverDestinoSelect?.focus();
            if (btnConfirmarTraslado) {
              btnConfirmarTraslado.disabled = false;
              btnConfirmarTraslado.innerHTML = origBtnText;
            }
            return;
          }
          destinationId = Number(destVal);
          destinationName = moverDestinoSelect.options[moverDestinoSelect.selectedIndex]?.textContent || "la ubicación destino";
        }

        // Step 2: Transfer the asset to the destination
        const transferResponse = await fetch(`/inventory/assets/${assetId}/transfers`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
          },
          body: JSON.stringify({
            destination_location_id: destinationId,
            reason: reasonVal || null,
            observations: obsVal || null,
          }),
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

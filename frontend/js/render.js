(function () {
  "use strict";
  const data = window.DashboardData;
  const number = new Intl.NumberFormat("es-AR");

  let activeRealData = null;
  let activeRealFilter = "all";
  let activeRealAssetsPage = 1;
  const REAL_ASSETS_PAGE_SIZE = 6;
  let lastRealQuery = "";

  function scaled(value, multiplier) { return Math.max(1, Math.round(value * multiplier)); }
  function formatKpi(item, multiplier) {
    return number.format(scaled(item.value, multiplier));
  }

  function renderKpis(multiplier) {
    if (activeRealData) {
      renderRealKpis(activeRealData);
      return;
    }
    const kpiEl = document.querySelector("#kpi-grid");
    if (!kpiEl) return;
    kpiEl.innerHTML = data.kpis.map(item => `
      <article class="kpi-card">
        <div class="kpi-top"><span>${item.label}</span><span class="kpi-icon" aria-hidden="true">${item.icon}</span></div>
        <div class="kpi-value-row"><strong class="kpi-value">${formatKpi(item, multiplier)}</strong><span class="trend ${item.trend >= 0 ? "up" : "down"}">${item.trend >= 0 ? "↑" : "↓"} ${Math.abs(item.trend)}%</span></div>
        <p class="kpi-note">${item.note}</p>
      </article>`).join("");
  }

  function renderRealKpis(realData) {
    const kpiEl = document.querySelector("#kpi-grid");
    if (!kpiEl) return;
    const totalAssets = realData.assets.length;
    const assigned = realData.assets.filter(a => a.location_id !== null).length;
    const inStorage = realData.assets.filter(a => a.location_id === null).length;
    const catCount = realData.categories.length;
    const assignedPct = totalAssets > 0 ? ((assigned / totalAssets) * 100).toFixed(0) : "0";

    const realKpis = [
      { label: "Bienes en total", value: totalAssets, trend: "100%", isUp: true, note: "Activos en base de datos", icon: "◇" },
      { label: "Asignados en servicio", value: assigned, trend: `${assignedPct}%`, isUp: true, note: "En cuartel o unidad móvil", icon: "◎" },
      { label: "En depósito", value: inStorage, trend: `${totalAssets > 0 ? (100 - Number(assignedPct)) : 0}%`, isUp: false, note: "Sin asignación fija", icon: "⌁" },
      { label: "Categorías activas", value: catCount, trend: "Catálogo", isUp: true, note: "Familias operativas", icon: "⊘" },
    ];

    kpiEl.innerHTML = realKpis.map(item => `
      <article class="kpi-card">
        <div class="kpi-top"><span>${item.label}</span><span class="kpi-icon" aria-hidden="true">${item.icon}</span></div>
        <div class="kpi-value-row"><strong class="kpi-value">${number.format(item.value)}</strong><span class="trend ${item.isUp ? "up" : "down"}">${item.trend}</span></div>
        <p class="kpi-note">${item.note}</p>
      </article>`).join("");
  }

  function renderChart(multiplier) {
    if (activeRealData) {
      renderRealChart(activeRealData);
      return;
    }
    const summaryEl = document.querySelector("#chart-summary");
    const barEl = document.querySelector("#bar-chart");
    if (!summaryEl || !barEl) return;
    const totalAssets = data.categories.reduce((sum, category) => sum + category.inService + category.maintenance + category.retired, 0);
    const totalWithIncident = data.categories.reduce((sum, category) => sum + category.maintenance + category.retired, 0);
    summaryEl.innerHTML = `<span>Bienes<strong>${number.format(scaled(totalAssets, multiplier))}</strong></span><span>Con incidencia<strong>${number.format(scaled(totalWithIncident, multiplier))}</strong></span>`;
    barEl.innerHTML = data.categories.map((category, index) => {
      const total = category.inService + category.maintenance + category.retired;
      const labelToShow = abbreviateCategoryName(category.label);
      return `<div class="bar-group" title="${category.label}: ${number.format(scaled(total, multiplier))} bienes · Datos de demostración">
        <div class="bar-stack" style="height:${Math.min(96, total / 3.3)}%">
          <i class="bar-segment primary" style="height:${category.inService / total * 100}%;animation-delay:${index * 35}ms"></i>
          <i class="bar-segment orange" style="height:${category.maintenance / total * 100}%;animation-delay:${index * 35 + 30}ms"></i>
          <i class="bar-segment yellow" style="height:${category.retired / total * 100}%;animation-delay:${index * 35 + 60}ms"></i>
        </div><span class="bar-label" title="${category.label}">${labelToShow}</span></div>`;
    }).join("");
  }

  function abbreviateCategoryName(name) {
    if (!name || typeof name !== "string") return "";
    const clean = name.trim();

    // Specific abbreviations for known VERY LONG categories (> 14 chars or multi-word long)
    const longCategoriesMap = {
      "Material Hídrico": "Mat. Hídrico",
      "Material Hidrico": "Mat. Hídrico",
      "Protección Personal (EPP)": "EPP",
      "Protección Personal": "EPP",
      "Proteccion Personal (EPP)": "EPP",
      "Proteccion Personal": "EPP",
      "Equipos de Protección Personal": "EPP",
      "Herramientas de Corte y Fuerza": "Herramientas",
      "Herramientas de Corte": "Herramientas",
      "Herramientas de corte": "Herramientas",
      "Rescate Vehicular y Altura": "Rescate Veh.",
      "Rescate Vehicular": "Rescate Veh.",
      "Comunicaciones y Óptica": "Comunicaciones",
      "Materiales Peligrosos (HAZMAT)": "HAZMAT",
      "Materiales Peligrosos": "HAZMAT",
      "Equipos de Iluminación y Balizamiento": "Iluminación",
      "Equipos de Iluminación": "Iluminación",
      "Equipos de Respiración Autónoma (ERA)": "ERA",
      "Equipos de Respiración Autónoma": "ERA",
      "Sanidad y Primeros Auxilios": "Sanidad",
      "Vehículos y Autobombas": "Vehículos",
      "Repuestos y Mantenimiento": "Repuestos",
    };

    if (longCategoriesMap[clean]) {
      return longCategoriesMap[clean];
    }

    // Acronym in parentheses if present, e.g. "Cualquier Cosa (ABC)" -> "ABC"
    const paren = clean.match(/\(([A-Z0-9\s-]{2,8})\)/);
    if (paren && paren[1]) {
      return paren[1].trim();
    }

    // Nombres muy largos (> 14 caracteres): acortar con tres puntos suspensivos (...)
    if (clean.length > 14) {
      return clean.slice(0, 12).trim() + "...";
    }

    return clean;
  }

  function renderRealChart(realData) {
    const summaryEl = document.querySelector("#chart-summary");
    const barEl = document.querySelector("#bar-chart");
    if (!summaryEl || !barEl) return;

    const kicker = summaryEl.closest(".panel")?.querySelector(".panel-kicker");
    if (kicker) kicker.textContent = "Datos en tiempo real";

    const totalAssets = realData.assets.length;
    const activeCatsWithAssets = realData.categories.filter(c => realData.assets.some(a => a.category_id === c.id)).length;
    summaryEl.innerHTML = `<span>Bienes registrados<strong>${number.format(totalAssets)}</strong></span><span>Categorías con stock<strong>${number.format(activeCatsWithAssets)}</strong></span>`;

    if (!realData.categories.length) {
      barEl.innerHTML = `<p class="table-muted" style="padding:20px;text-align:center;">No hay categorías registradas en la base de datos.</p>`;
      return;
    }

    const counts = realData.categories.map(c => realData.assets.filter(a => a.category_id === c.id).length);
    const maxCount = Math.max(1, ...counts);

    barEl.innerHTML = realData.categories.map((category, index) => {
      const catAssets = realData.assets.filter(a => a.category_id === category.id);
      const total = catAssets.length;
      const assigned = catAssets.filter(a => a.location_id !== null).length;
      const inStorage = catAssets.filter(a => a.location_id === null).length;
      const heightPercent = total > 0 ? Math.max(12, Math.min(96, (total / maxCount) * 96)) : 6;
      const assignedPct = total > 0 ? (assigned / total) * 100 : 0;
      const storagePct = total > 0 ? (inStorage / total) * 100 : 100;
      const shortName = abbreviateCategoryName(category.name);

      return `<div class="bar-group" title="${category.name}: ${number.format(total)} bienes (${assigned} asignados, ${inStorage} en depósito)">
        <div class="bar-stack" style="height:${heightPercent}%">
          <i class="bar-segment primary" style="height:${assignedPct}%;animation-delay:${index * 35}ms"></i>
          <i class="bar-segment orange" style="height:${storagePct}%;animation-delay:${index * 35 + 30}ms"></i>
        </div><span class="bar-label" title="${category.name}">${shortName}</span></div>`;
    }).join("");
  }

  function renderStatuses(multiplier) {
    if (activeRealData) {
      renderRealStatuses(activeRealData);
      return;
    }
    const totalsEl = document.querySelector("#channel-totals");
    const listEl = document.querySelector("#channel-list");
    const stripEl = document.querySelector("#signal-strip");
    if (!totalsEl || !listEl || !stripEl) return;
    totalsEl.innerHTML = data.statuses.map(status => `<div class="channel-total"><small><i class="channel-dot" style="background:${status.color}"></i>${status.name}</small><strong>${status.share.toFixed(1)}%</strong></div>`).join("");
    listEl.innerHTML = data.statuses.map(status => `<li class="channel-row"><span class="channel-name"><i class="channel-symbol" style="--channel-color:${status.color}">${status.short}</i>${status.name}</span><span>${status.share.toFixed(0)}%</span><span>${number.format(scaled(status.total, multiplier))}</span></li>`).join("");
    stripEl.innerHTML = data.statuses.map(status => `<i class="signal-segment" title="${status.name}: ${status.share.toFixed(1)}%" style="--signal-share:${status.share};background:${status.color}"></i>`).join("");
  }

  function renderRealStatuses(realData) {
    const totalsEl = document.querySelector("#channel-totals");
    const listEl = document.querySelector("#channel-list");
    const stripEl = document.querySelector("#signal-strip");
    if (!totalsEl || !listEl || !stripEl) return;

    const kicker = totalsEl.closest(".panel")?.querySelector(".panel-kicker");
    if (kicker) kicker.textContent = "Datos en tiempo real";

    const colorService = (data.statuses && data.statuses[0]?.color) || "#E53935";
    const colorMaintenance = (data.statuses && data.statuses[1]?.color) || "#ef741d";
    const colorRetired = (data.statuses && data.statuses[2]?.color) || "#f6c548";

    const total = realData.assets.length;
    const assigned = realData.assets.filter(a => a.location_id !== null).length;
    const inStorage = realData.assets.filter(a => a.location_id === null).length;
    const assignedPct = total > 0 ? (assigned / total) * 100 : 0;
    const inStoragePct = total > 0 ? (inStorage / total) * 100 : 0;

    totalsEl.innerHTML = `
      <div class="channel-total"><small><i class="channel-dot" style="background:${colorService}"></i>En servicio</small><strong>${assignedPct.toFixed(1)}%</strong></div>
      <div class="channel-total"><small><i class="channel-dot" style="background:${colorMaintenance}"></i>Depósito</small><strong>${inStoragePct.toFixed(1)}%</strong></div>
      <div class="channel-total"><small><i class="channel-dot" style="background:${colorRetired}"></i>Ubicaciones</small><strong>${realData.locations.length}</strong></div>`;

    stripEl.innerHTML = `
      <i class="signal-segment" title="En servicio / Asignados: ${assignedPct.toFixed(1)}%" style="--signal-share:${Math.max(1, assignedPct)};background:${colorService}"></i>
      <i class="signal-segment" title="En depósito: ${inStoragePct.toFixed(1)}%" style="--signal-share:${Math.max(1, inStoragePct)};background:${colorMaintenance}"></i>`;

    listEl.innerHTML = `
      <li class="channel-row">
        <span class="channel-name"><i class="channel-symbol" style="--channel-color:${colorService}">S</i>En servicio / Asignados</span>
        <span>${assignedPct.toFixed(0)}%</span>
        <span>${number.format(assigned)}</span>
      </li>
      <li class="channel-row">
        <span class="channel-name"><i class="channel-symbol" style="--channel-color:${colorMaintenance}">M</i>En depósito central</span>
        <span>${inStoragePct.toFixed(0)}%</span>
        <span>${number.format(inStorage)}</span>
      </li>
      <li class="channel-row">
        <span class="channel-name"><i class="channel-symbol" style="--channel-color:${colorRetired}">B</i>Ubicaciones registradas</span>
        <span>100%</span>
        <span>${number.format(realData.locations.length)}</span>
      </li>`;
  }

  function renderMovements(query, multiplier) {
    if (activeRealData) {
      renderRealMovements(activeRealData, query, activeRealFilter);
      return;
    }
    const tableBody = document.querySelector("#country-table-body");
    if (!tableBody) return;
    const cleanQuery = query.trim().toLowerCase();
    const movements = data.movements.filter(movement => `${movement.name} ${movement.code} ${movement.action}`.toLowerCase().includes(cleanQuery));
    tableBody.innerHTML = movements.length ? movements.map(movement => `<tr><td><span class="country-name"><span class="flag" aria-hidden="true">•</span>${movement.name} · ${movement.code}</span></td><td>${movement.action}</td><td>${number.format(scaled(movement.quantity, multiplier))}</td><td><span class="sparkline" aria-label="Actividad reciente ilustrativa">${movement.trend.map(value => `<i style="height:${value}px"></i>`).join("")}</span></td></tr>`).join("") : `<tr><td colspan="4">No hay movimientos de demostración que coincidan con la búsqueda.</td></tr>`;

    const paginationEl = document.querySelector("#country-table-pagination");
    const infoEl = document.querySelector("#assets-pagination-info");
    const prevBtn = document.querySelector("#btn-prev-assets");
    const nextBtn = document.querySelector("#btn-next-assets");
    if (paginationEl) {
      if (infoEl) infoEl.textContent = `Mostrando ${movements.length} de ${movements.length} movimientos`;
      if (prevBtn) prevBtn.disabled = true;
      if (nextBtn) nextBtn.disabled = true;
    }
  }

  function renderRealMovements(realData, query = "", filter = "all") {
    const tableBody = document.querySelector("#country-table-body");
    if (!tableBody) return;

    const panel = tableBody.closest(".panel");
    const kicker = panel?.querySelector(".panel-kicker");
    if (kicker) kicker.textContent = "Datos en tiempo real";

    const titleH2 = panel?.querySelector("h2");
    if (titleH2) titleH2.textContent = "Activos registrados";

    const cleanQuery = query.trim().toLowerCase();
    if (cleanQuery !== lastRealQuery) {
      lastRealQuery = cleanQuery;
      activeRealAssetsPage = 1;
    }

    const catMap = new Map(realData.categories.map(c => [c.id, c.name]));
    const locMap = new Map(realData.locations.map(l => [l.id, l.name]));

    const filtered = realData.assets.filter(asset => {
      const catName = catMap.get(asset.category_id) || "Sin categoría";
      const locName = locMap.get(asset.location_id) || "Depósito Central";
      const searchMatch = !cleanQuery || `${asset.name} ${asset.internal_code} ${catName} ${locName}`.toLowerCase().includes(cleanQuery);
      if (!searchMatch) return false;
      if (filter === "assigned") return asset.location_id !== null;
      if (filter === "storage") return asset.location_id === null;
      return true;
    });

    const totalItems = filtered.length;
    const totalPages = Math.max(1, Math.ceil(totalItems / REAL_ASSETS_PAGE_SIZE));
    if (activeRealAssetsPage > totalPages) {
      activeRealAssetsPage = totalPages;
    }
    if (activeRealAssetsPage < 1) {
      activeRealAssetsPage = 1;
    }

    const startIndex = (activeRealAssetsPage - 1) * REAL_ASSETS_PAGE_SIZE;
    const endIndex = Math.min(totalItems, startIndex + REAL_ASSETS_PAGE_SIZE);
    const pageItems = filtered.slice(startIndex, endIndex);

    tableBody.innerHTML = pageItems.length ? pageItems.map(asset => {
      const catName = catMap.get(asset.category_id) || "General";
      const locName = locMap.get(asset.location_id) || "Depósito Central";
      const isAssigned = asset.location_id !== null;
      return `<tr>
        <td><span class="country-name"><span class="flag" aria-hidden="true">•</span><strong>${asset.name}</strong> · <span class="table-code">${asset.internal_code}</span></span></td>
        <td>${catName}</td>
        <td>${locName}</td>
        <td><span class="status-pill ${isAssigned ? 'success' : 'warning'}">${isAssigned ? 'En servicio' : 'En depósito'}</span></td>
      </tr>`;
    }).join("") : `<tr><td colspan="4">No hay activos registrados que coincidan con los criterios.</td></tr>`;

    const paginationEl = document.querySelector("#country-table-pagination");
    const infoEl = document.querySelector("#assets-pagination-info");
    const prevBtn = document.querySelector("#btn-prev-assets");
    const nextBtn = document.querySelector("#btn-next-assets");

    if (paginationEl) {
      paginationEl.hidden = false;
      if (infoEl) {
        if (totalItems === 0) {
          infoEl.textContent = "Sin activos que coincidan";
        } else {
          infoEl.textContent = `Mostrando ${startIndex + 1}–${endIndex} de ${totalItems} (Pág. ${activeRealAssetsPage} de ${totalPages})`;
        }
      }
      if (prevBtn) {
        prevBtn.disabled = (activeRealAssetsPage <= 1);
      }
      if (nextBtn) {
        nextBtn.disabled = (activeRealAssetsPage >= totalPages);
      }
    }
  }

  // Delegated pagination click listener
  if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
    document.addEventListener("click", event => {
      const nextBtn = event.target?.closest?.("#btn-next-assets");
      if (nextBtn && !nextBtn.disabled) {
        event.preventDefault();
        window.DashboardRenderer?.nextAssetsPage();
        return;
      }
      const prevBtn = event.target?.closest?.("#btn-prev-assets");
      if (prevBtn && !prevBtn.disabled) {
        event.preventDefault();
        window.DashboardRenderer?.prevAssetsPage();
        return;
      }
    });
  }

  let activeBienesQuery = "";
  let activeBienesFilter = "all";
  let activeCategoriasQuery = "";

  function renderBienesView(realData, query = "", filter = "all") {
    const tableBody = document.querySelector("#bienes-table-body");
    if (!tableBody || !realData || !Array.isArray(realData.assets)) return;

    const catMap = new Map((realData.categories || []).map(c => [c.id, c.name]));
    const locMap = new Map((realData.locations || []).map(l => [l.id, l.name]));

    const cleanQuery = (query || "").trim().toLowerCase();
    const assets = realData.assets;

    let enServicioCount = 0;
    let enDepositoCount = 0;
    assets.forEach(a => {
      if (a.location_id !== null) enServicioCount++;
      else enDepositoCount++;
    });

    const countAllEl = document.querySelector("#bienes-count-all");
    const countServicioEl = document.querySelector("#bienes-count-servicio");
    const countDepositoEl = document.querySelector("#bienes-count-deposito");
    if (countAllEl) countAllEl.textContent = assets.length;
    if (countServicioEl) countServicioEl.textContent = enServicioCount;
    if (countDepositoEl) countDepositoEl.textContent = enDepositoCount;

    const filtered = assets.filter(asset => {
      const catName = catMap.get(asset.category_id) || "Sin categoría";
      const locName = locMap.get(asset.location_id) || "Sin asignación fija (Depósito)";
      const isAssigned = asset.location_id !== null;

      if (cleanQuery) {
        const textToSearch = `${asset.name} ${asset.internal_code} ${catName} ${locName}`.toLowerCase();
        if (!textToSearch.includes(cleanQuery)) return false;
      }

      if (filter === "servicio" && !isAssigned) return false;
      if (filter === "deposito" && isAssigned) return false;
      return true;
    });

    const sorted = [...filtered].sort((a, b) => (b.id || 0) - (a.id || 0));

    if (!sorted.length) {
      tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">No se encontraron bienes registrados.</td></tr>`;
      return;
    }

    tableBody.innerHTML = sorted.map(asset => {
      const catName = catMap.get(asset.category_id) || "General";
      const locName = locMap.get(asset.location_id) || "Sin asignación fija (Depósito)";
      const isAssigned = asset.location_id !== null;
      return `<tr data-status="${isAssigned ? 'servicio' : 'deposito'}">
        <td class="table-code">${asset.internal_code}</td>
        <td><strong>${asset.name}</strong></td>
        <td>${catName}</td>
        <td>${locName}</td>
        <td><span class="status-pill ${isAssigned ? 'success' : 'warning'}">${isAssigned ? 'En servicio' : 'En depósito'}</span></td>
        <td><div class="table-actions"><button class="action-button-sm btn-mover-bien" type="button" data-asset-id="${asset.id}">Mover</button><button class="action-button-sm" type="button" data-asset-id="${asset.id}">Detalles</button></div></td>
      </tr>`;
    }).join("");
  }

  function renderCategoriasView(realData, query = "") {
    const tableBody = document.querySelector("#categorias-table-body");
    if (!tableBody || !realData || !Array.isArray(realData.categories)) return;

    const cleanQuery = (query || "").trim().toLowerCase();
    const assets = realData.assets || [];

    const countMap = new Map();
    assets.forEach(a => {
      countMap.set(a.category_id, (countMap.get(a.category_id) || 0) + 1);
    });

    const filtered = realData.categories.filter(cat => {
      if (!cleanQuery) return true;
      return cat.name.toLowerCase().includes(cleanQuery);
    });

    const sorted = [...filtered].sort((a, b) => (b.id || 0) - (a.id || 0));

    if (!sorted.length) {
      tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 24px; color: var(--text-soft);">No se encontraron categorías registradas.</td></tr>`;
      return;
    }

    tableBody.innerHTML = sorted.map(cat => {
      const assetCount = countMap.get(cat.id) || 0;
      return `<tr>
        <td class="table-code">CAT-${String(cat.id).padStart(2, "0")}</td>
        <td><strong>${cat.name}</strong></td>
        <td class="table-muted">Categoría registrada en el catálogo de Fire Control.</td>
        <td><strong>${assetCount}</strong></td>
        <td><span class="status-pill success">Activa</span></td>
        <td><div class="table-actions"><button class="action-button-sm" type="button" data-cat-id="${cat.id}">Ver bienes</button></div></td>
      </tr>`;
    }).join("");
  }

  let activeMovimientosQuery = "";
  let activeMovimientosFilter = "all";

  function formatDateTime(isoString) {
    if (!isoString) return "-";
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return isoString;
      const day = String(d.getDate()).padStart(2, "0");
      const month = String(d.getMonth() + 1).padStart(2, "0");
      const year = d.getFullYear();
      const hours = String(d.getHours()).padStart(2, "0");
      const mins = String(d.getMinutes()).padStart(2, "0");
      return `${day}/${month}/${year} ${hours}:${mins}`;
    } catch (_) {
      return isoString;
    }
  }

  function renderMovimientosView(realData, query = "", filter = "all") {
    const tableBody = document.querySelector("#movimientos-table-body");
    if (!tableBody) return;

    const movements = (realData && Array.isArray(realData.movements)) ? realData.movements : [];
    const cleanQuery = (query || "").trim().toLowerCase();

    let trasladosCount = 0;
    let altasCount = 0;
    let bajasCount = 0;

    movements.forEach(m => {
      const type = (m.movement_type || "").toUpperCase();
      if (type === "TRASLADO") trasladosCount++;
      else if (type === "ALTA") altasCount++;
      else if (type.includes("BAJA")) bajasCount++;
    });

    const countAllEl = document.querySelector("#movimientos-count-all");
    const countTrasladosEl = document.querySelector("#movimientos-count-traslados");
    const countAltasEl = document.querySelector("#movimientos-count-altas");
    const countBajasEl = document.querySelector("#movimientos-count-bajas");
    if (countAllEl) countAllEl.textContent = movements.length;
    if (countTrasladosEl) countTrasladosEl.textContent = trasladosCount;
    if (countAltasEl) countAltasEl.textContent = altasCount;
    if (countBajasEl) countBajasEl.textContent = bajasCount;

    const filtered = movements.filter(m => {
      const type = (m.movement_type || "").toUpperCase();
      const assetCode = m.asset_code || "";
      const assetName = m.asset_name || "";
      const origin = m.origin_location_name || "Depósito Central";
      const dest = m.destination_location_name || "Depósito Central";
      const reason = m.reason || "";
      const obs = m.observations || "";
      const user = m.user_email || "";

      if (cleanQuery) {
        const textToSearch = `${assetCode} ${assetName} ${type} ${origin} ${dest} ${reason} ${obs} ${user}`.toLowerCase();
        if (!textToSearch.includes(cleanQuery)) return false;
      }

      if (filter === "TRASLADO" && type !== "TRASLADO") return false;
      if (filter === "ALTA" && type !== "ALTA") return false;
      if (filter === "BAJA" && !type.includes("BAJA")) return false;
      return true;
    });

    const sorted = [...filtered].sort((a, b) => new Date(b.occurred_at || 0) - new Date(a.occurred_at || 0));

    if (!sorted.length) {
      const msg = cleanQuery || filter !== "all"
        ? "No hay movimientos que coincidan con los filtros aplicados."
        : "No se registran movimientos en el inventario.";
      tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 24px; color: var(--text-soft);">${msg}</td></tr>`;
      return;
    }

    tableBody.innerHTML = sorted.map(m => {
      const type = (m.movement_type || "TRASLADO").toUpperCase();
      const pillClass = type === "TRASLADO" ? "primary" : (type === "ALTA" ? "success" : "danger");
      const dateStr = formatDateTime(m.occurred_at);
      const originName = m.origin_location_name || "Sin asignación (Depósito)";
      const destName = m.destination_location_name || "Sin asignación (Depósito)";
      const operatorName = m.user_email ? m.user_email.split("@")[0] : "Operador";
      const reasonText = m.reason ? `<strong>${m.reason}</strong>` : `<span class="table-muted">Sin motivo especificado</span>`;
      const obsText = m.observations ? `<br><small class="table-muted">${m.observations}</small>` : "";

      return `<tr>
        <td class="table-code">${dateStr}</td>
        <td><strong>${m.asset_name || 'Bien'}</strong> <br><span class="table-code">${m.asset_code || ''}</span></td>
        <td><span class="status-pill ${pillClass}">${type}</span></td>
        <td>${originName}</td>
        <td><strong>${destName}</strong></td>
        <td><small class="table-muted">${operatorName}</small></td>
        <td>${reasonText}${obsText}</td>
      </tr>`;
    }).join("");
  }

  window.DashboardRenderer = {
    render(period, query = "") {
      const multiplier = data.periods[period]?.multiplier || 1;
      renderKpis(multiplier);
      renderChart(multiplier);
      renderStatuses(multiplier);
      renderMovements(query, multiplier);
    },
    renderMovements(query, multiplier) {
      if (activeRealData) {
        renderRealMovements(activeRealData, query, activeRealFilter);
      } else {
        renderMovements(query, multiplier);
      }
    },
    setRealData(realData) {
      activeRealData = realData;
      activeRealAssetsPage = 1;
      const period = document.querySelector("#date-range")?.value || "90";
      const query = document.querySelector("#country-search")?.value || "";
      this.render(period, query);
      renderBienesView(realData, activeBienesQuery, activeBienesFilter);
      renderCategoriasView(realData, activeCategoriasQuery);
      renderMovimientosView(realData, activeMovimientosQuery, activeMovimientosFilter);
    },
    setRealFilter(filter) {
      activeRealFilter = filter;
      activeRealAssetsPage = 1;
      if (activeRealData) {
        renderRealMovements(activeRealData, document.querySelector("#country-search")?.value || "", activeRealFilter);
      }
    },
    setBienesQuery(query) {
      activeBienesQuery = query;
      if (activeRealData) {
        renderBienesView(activeRealData, activeBienesQuery, activeBienesFilter);
      }
    },
    setBienesFilter(filter) {
      activeBienesFilter = filter;
      if (activeRealData) {
        renderBienesView(activeRealData, activeBienesQuery, activeBienesFilter);
      }
    },
    setCategoriasQuery(query) {
      activeCategoriasQuery = query;
      if (activeRealData) {
        renderCategoriasView(activeRealData, activeCategoriasQuery);
      }
    },
    setMovimientosQuery(query) {
      activeMovimientosQuery = query;
      if (activeRealData) {
        renderMovimientosView(activeRealData, activeMovimientosQuery, activeMovimientosFilter);
      }
    },
    setMovimientosFilter(filter) {
      activeMovimientosFilter = filter;
      if (activeRealData) {
        renderMovimientosView(activeRealData, activeMovimientosQuery, activeMovimientosFilter);
      }
    },
    setAssetsPage(page) {
      const target = Number(page);
      if (!Number.isFinite(target)) return;
      activeRealAssetsPage = target;
      if (activeRealData) {
        renderRealMovements(activeRealData, document.querySelector("#country-search")?.value || "", activeRealFilter);
      }
    },
    nextAssetsPage() {
      this.setAssetsPage(activeRealAssetsPage + 1);
    },
    prevAssetsPage() {
      this.setAssetsPage(activeRealAssetsPage - 1);
    },
    getAssetsPage: () => activeRealAssetsPage,
    getAssetsPageSize: () => REAL_ASSETS_PAGE_SIZE,
    getRealData: () => activeRealData,
    renderBienesView,
    renderCategoriasView,
    renderMovimientosView,
  };
})();
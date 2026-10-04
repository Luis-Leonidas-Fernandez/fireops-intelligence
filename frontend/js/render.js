(function () {
  "use strict";
  const data = window.DashboardData;
  const number = new Intl.NumberFormat("es-AR");

  function scaled(value, multiplier) { return Math.max(1, Math.round(value * multiplier)); }
  function formatKpi(item, multiplier) {
    return number.format(scaled(item.value, multiplier));
  }

  function renderKpis(multiplier) {
    document.querySelector("#kpi-grid").innerHTML = data.kpis.map(item => `
      <article class="kpi-card">
        <div class="kpi-top"><span>${item.label}</span><span class="kpi-icon" aria-hidden="true">${item.icon}</span></div>
        <div class="kpi-value-row"><strong class="kpi-value">${formatKpi(item, multiplier)}</strong><span class="trend ${item.trend >= 0 ? "up" : "down"}">${item.trend >= 0 ? "↑" : "↓"} ${Math.abs(item.trend)}%</span></div>
        <p class="kpi-note">${item.note}</p>
      </article>`).join("");
  }

  function renderChart(multiplier) {
    const totalAssets = data.categories.reduce((sum, category) => sum + category.inService + category.maintenance + category.retired, 0);
    const totalWithIncident = data.categories.reduce((sum, category) => sum + category.maintenance + category.retired, 0);
    document.querySelector("#chart-summary").innerHTML = `<span>Bienes<strong>${number.format(scaled(totalAssets, multiplier))}</strong></span><span>Con incidencia<strong>${number.format(scaled(totalWithIncident, multiplier))}</strong></span>`;
    document.querySelector("#bar-chart").innerHTML = data.categories.map((category, index) => {
      const total = category.inService + category.maintenance + category.retired;
      return `<div class="bar-group" title="${category.label}: ${number.format(scaled(total, multiplier))} bienes · Datos de demostración">
        <div class="bar-stack" style="height:${Math.min(96, total / 3.3)}%">
          <i class="bar-segment primary" style="height:${category.inService / total * 100}%;animation-delay:${index * 35}ms"></i>
          <i class="bar-segment orange" style="height:${category.maintenance / total * 100}%;animation-delay:${index * 35 + 30}ms"></i>
          <i class="bar-segment yellow" style="height:${category.retired / total * 100}%;animation-delay:${index * 35 + 60}ms"></i>
        </div><span class="bar-label">${category.label}</span></div>`;
    }).join("");
  }

  function renderStatuses(multiplier) {
    document.querySelector("#channel-totals").innerHTML = data.statuses.map(status => `<div class="channel-total"><small><i class="channel-dot" style="background:${status.color}"></i>${status.name}</small><strong>${status.share.toFixed(1)}%</strong></div>`).join("");
    document.querySelector("#channel-list").innerHTML = data.statuses.map(status => `<li class="channel-row"><span class="channel-name"><i class="channel-symbol" style="--channel-color:${status.color}">${status.short}</i>${status.name}</span><span>${status.share.toFixed(0)}%</span><span>${number.format(scaled(status.total, multiplier))}</span></li>`).join("");
    document.querySelector("#signal-strip").innerHTML = data.statuses.map(status => `<i class="signal-segment" title="${status.name}: ${status.share.toFixed(1)}%" style="--signal-share:${status.share};background:${status.color}"></i>`).join("");
  }

  function renderMovements(query, multiplier) {
    const cleanQuery = query.trim().toLowerCase();
    const movements = data.movements.filter(movement => `${movement.name} ${movement.code} ${movement.action}`.toLowerCase().includes(cleanQuery));
    document.querySelector("#country-table-body").innerHTML = movements.length ? movements.map(movement => `<tr><td><span class="country-name"><span class="flag" aria-hidden="true">•</span>${movement.name} · ${movement.code}</span></td><td>${movement.action}</td><td>${number.format(scaled(movement.quantity, multiplier))}</td><td><span class="sparkline" aria-label="Actividad reciente ilustrativa">${movement.trend.map(value => `<i style="height:${value}px"></i>`).join("")}</span></td></tr>`).join("") : `<tr><td colspan="4">No hay movimientos de demostración que coincidan con la búsqueda.</td></tr>`;
  }

  window.DashboardRenderer = {
    render(period, query = "") {
      const multiplier = data.periods[period].multiplier;
      renderKpis(multiplier); renderChart(multiplier); renderStatuses(multiplier); renderMovements(query, multiplier);
    },
    renderMovements
  };
})();

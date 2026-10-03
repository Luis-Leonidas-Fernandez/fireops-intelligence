window.DashboardData = {
  periods: {
    "30": { multiplier: 0.42, label: "Últimos 30 días" },
    "90": { multiplier: 1, label: "Últimos 90 días" },
    "180": { multiplier: 1.74, label: "Últimos 6 meses" }
  },
  kpis: [
    { label: "Bienes", value: 1264, format: "number", trend: 2.4, note: "Datos de demostración", icon: "◇" },
    { label: "En servicio", value: 1087, format: "number", trend: 1.8, note: "Datos de demostración", icon: "◎" },
    { label: "En mantenimiento", value: 143, format: "number", trend: -0.9, note: "Datos de demostración", icon: "⌁" },
    { label: "Bajas", value: 34, format: "number", trend: -0.3, note: "Datos de demostración", icon: "⊘" }
  ],
  categories: [
    { label: "Extinción", inService: 214, maintenance: 32, retired: 7 },
    { label: "Protección", inService: 263, maintenance: 41, retired: 9 },
    { label: "Rescate", inService: 144, maintenance: 23, retired: 4 },
    { label: "Comunic.", inService: 96, maintenance: 12, retired: 3 },
    { label: "Herram.", inService: 128, maintenance: 17, retired: 5 },
    { label: "Iluminac.", inService: 77, maintenance: 7, retired: 2 },
    { label: "Sanidad", inService: 68, maintenance: 6, retired: 1 },
    { label: "Vehículos", inService: 38, maintenance: 4, retired: 2 },
    { label: "Repuestos", inService: 59, maintenance: 1, retired: 1 }
  ],
  statuses: [
    { name: "En servicio", short: "S", share: 86.0, total: 1087, color: "#a46aff" },
    { name: "En mantenimiento", short: "M", share: 11.3, total: 143, color: "#ef741d" },
    { name: "Bajas", short: "B", share: 2.7, total: 34, color: "#f6c548" }
  ],
  movements: [
    { name: "Bomba sumergible", code: "FC-0248", action: "Salida a Unidad 2", quantity: 1, trend: [5, 9, 7, 13, 11, 16, 14] },
    { name: "Equipo autónomo", code: "FC-0316", action: "Ingreso por devolución", quantity: 2, trend: [6, 7, 9, 8, 12, 13, 15] },
    { name: "Manguera 45 mm", code: "FC-0187", action: "Traslado a Móvil 4", quantity: 3, trend: [4, 8, 6, 10, 9, 11, 13] },
    { name: "Radio portátil", code: "FC-0402", action: "Envío a mantenimiento", quantity: 1, trend: [3, 5, 7, 6, 9, 8, 12] },
    { name: "Casco estructural", code: "FC-0119", action: "Alta en depósito", quantity: 4, trend: [7, 6, 8, 10, 9, 12, 11] }
  ]
};

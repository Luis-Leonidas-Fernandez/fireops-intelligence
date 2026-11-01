# Arquitectura actual del frontend

La interfaz web utiliza HTML, CSS y JavaScript sin framework ni paso de compilación, servida por FastAPI en el mismo origen que la API (`127.0.0.1:8000`). [ADR-003](../adr/ADR-003-frontend-architecture.md) registra la elección tecnológica, [ADR-005](../adr/ADR-005-email-password-authentication.md) la autenticación y [ADR-007](../adr/ADR-007-automatic-vehicle-containers.md) el manejo transparente de vehículos como ubicaciones móviles.

## Páginas y archivos principales

| Ruta / Archivo | Ubicación en el repositorio | Responsabilidad |
|---|---|---|
| `/` | `frontend/index.html` | Aplicación principal con navegación lateral/móvil y vistas operativas de inventario y accesos (exige cookie de sesión válida) |
| `/registro` | `frontend/pages/registro/index.html` | Solicitud pública de acceso y creación de cuenta con token de invitación o Google |
| `/iniciar-sesion` | `frontend/pages/iniciar-sesion/index.html` | Inicio de sesión con correo/contraseña o Google OAuth |
| `/solicitudes` | `app/main.py` (`303` a `/?view=Invitaciones&tab=requests`) | Acceso directo para administradores a la gestión de solicitudes e invitaciones |
| `/css/*` | `frontend/css/` | Estilos modulares (`tokens.css`, `layout.css`, `components.css`, `theme-light.css`, `registro.css`) |
| `/js/navigation.js` | `frontend/js/navigation.js` | Controlador de navegación por vistas (`FireNavigationController`), matriz de permisos por rol (`ADMINISTRADOR`, `SUPERVISOR`) y anuncios ARIA |
| `/js/render.js` | `frontend/js/render.js` | Renderizado dinámico de tablas y vistas (`DashboardRenderer`: Bienes, Categorías, Ubicaciones, Vehículos, Movimientos y vistas de detalle) |
| `/js/app.js` | `frontend/js/app.js` | Carga de datos reales de la API, manejadores de eventos, navegación contextual, formularios de alta y modal de traslado |
| `/js/profile.js` | `frontend/js/profile.js` | Consulta `GET /auth/me`, muestra nombre/correo y rol en el app bar y propaga el rol a `FireNavigationController` |

---

## Vistas operativas y recorridos de inventario

Al cargar `/`, `frontend/js/app.js` ejecuta `checkApiConnection()`, que consulta `/health` y luego invoca `fetchAndRenderRealData()` para obtener en paralelo `GET /inventory/categories`, `GET /inventory/assets/`, `GET /inventory/locations` y `GET /inventory/movements`. Los datos se inyectan en `window.DashboardRenderer.setRealData(realData)` y alimentan las vistas operativas de `frontend/index.html`:

### 1. Ubicaciones → Ver bienes → Detalle del bien
- **Vista de listado (`#view-ubicaciones`, `data-view="Ubicaciones"`):** `renderUbicacionesView` muestra las ubicaciones reales del inventario con contadores por tipo (`Todas`, `Físicas`, `Vehículos`), buscador en tiempo real (`#ubicaciones-search-input`), filtro por tipo (`FISICA` / `VEHICULO`), cantidad de bienes actualmente asignados a cada ubicación y el botón **«Ver bienes»** (`.btn-ver-bienes-ubicacion`).
- **Vista de bienes por ubicación (`#view-ubicacion-bienes`, `data-view="Detalle de ubicación"`):** al presionar «Ver bienes», `openLocationAssetsView(locationId, returnView)` consulta la ubicación y el inventario actualizado, y `renderUbicacionBienesView` filtra estrictamente los bienes cuya ubicación actual coincide con esa ubicación (`Number(asset.location_id) === Number(loc.id)`). Incluye buscador propio (`#ubicacion-bienes-search-input`), estados de carga/vacío/error (`#ubicacion-bienes-feedback`) y acceso a **«Detalles»** (`.btn-ver-detalle-bien`) o **«Mover»** (`.btn-mover-bien`).
- **Retorno contextual:** al abrir «Detalles» desde `#view-ubicacion-bienes`, `openAssetDetailView(assetId, "Detalle de ubicación")` configura el botón `#btn-volver-detalle-bien` para regresar exactamente al listado de bienes de esa ubicación, y desde allí `#btn-volver-ubicaciones` regresa a «Ubicaciones».

### 2. Categorías → Ver bienes → Detalle del bien
- **Vista de listado (`#view-categorias`, `data-view="Categorías"`):** `renderCategoriasView` lista todas las categorías registradas con la cantidad real de bienes asociados, buscador y el botón **«Ver bienes»** (`.btn-ver-bienes-categoria`).
- **Vista de bienes por categoría (`#view-categoria-bienes`, `data-view="Detalle de categoría"`):** al presionar «Ver bienes», `openCategoryAssetsView(categoryId)` activa la vista y `renderCategoriaBienesView` filtra estrictamente por `Number(asset.category_id) === Number(cat.id)`, reutilizando la tabla acotada `renderScopedAssetsTable` con buscador en tiempo real (`#categoria-bienes-search-input`) y manejo de errores (`#categoria-bienes-feedback`).
- **Retorno contextual:** al ingresar a «Detalles» de un bien desde una categoría, `#btn-volver-detalle-bien` conserva `data-view-target="Detalle de categoría"` (`Volver a la categoría`), permitiendo retornar al listado de la categoría sin perder el contexto.

### 3. Vehículos → Ficha del móvil y Ver dotación
- **Vista del parque automotor (`#view-vehiculos`, `data-view="Vehículos"`):** accesible desde el menú lateral y desde el selector móvil (`#mobile-nav`). `renderVehiculosView` construye un listado unificado y deduplicado por `asset.id` que identifica:
  1. Ubicaciones móviles con `location_type === "VEHICULO"` y `container_asset_id` definido, vinculadas a su bien contenedor.
  2. Bienes patrimoniales cuya categoría normalizada en NFD (sin tildes, en minúsculas) coincide exactamente con `"vehiculo"` o `"vehiculos"` (`isExactVehicleCategoryName`), aunque todavía no posean una fila `Location` de tipo `VEHICULO`.
- **Presentación orientada al usuario:** para cada unidad se muestra su código interno, denominación (`Unidad: <nombre>`), categoría, **ubicación física de estacionamiento** (resuelta desde `asset.location_id`, por ejemplo `Playón delantero` o `Cuartel Central`), cantidad de equipamiento a bordo (`0 bienes a bordo` o `N bienes a bordo`), estado visual `En servicio` y las acciones funcionales disponibles:
  - **«Ficha del móvil»** (`.btn-ver-ficha-vehiculo`): disponible para todos los vehículos; invoca `openAssetDetailView(assetId, "Vehículos")` para mostrar la ficha técnica y el historial de traslados del vehículo, con retorno directo a «Vehículos».
  - **«Ver dotación»** (`.btn-ver-dotacion-vehiculo`): disponible cuando el vehículo posee ubicación móvil asociada; invoca `openLocationAssetsView(locationId, "Vehículos")` reutilizando `#view-ubicacion-bienes` para listar los bienes a bordo y configurar `#btn-volver-ubicaciones` con retorno a «Vehículos».
- **Sin pasos ni etiquetas de configuración interna:** cuando un vehículo aún no tiene bienes asignados ni fila en `ubicaciones`, la tabla muestra su ubicación física de estacionamiento, `0 bienes a bordo`, estado `En servicio` y el botón «Ficha del móvil», sin mostrar textos técnicos como *«Ubicación móvil no configurada»* ni botones de habilitación manual.

### 4. Nuevo bien → Selección de ubicación física o vehículo
- En `#view-nuevo-bien` (`#form-crear-bien`), el usuario ingresa código interno, nombre, categoría (existente o nueva en línea) y ubicación inicial en `#asset-location` (o crea una ubicación física mediante el acceso rápido `#btn-quick-nueva-ubicacion`, que preserva los datos ya escritos en el formulario y selecciona automáticamente la ubicación creada al regresar).
- `populateLocationOptions` invoca `buildDestinationOptionItems` (`frontend/js/app.js`) para poblar `#asset-location` con una **estructura jerárquica**:
  - Cada ubicación física activa (`FISICA`) se muestra como opción principal (`value="<location.id>"`).
  - Debajo de cada ubicación física se listan anidados con sangría los vehículos actualmente estacionados en ella (`  - Camioneta HGJ-875 (HGJ-875) — Playón delantero`), seguidos al final por los vehículos en depósito sin ubicación fija.
  - Si el vehículo ya cuenta con una ubicación móvil `VEHICULO`, la opción usa `value="<mobileLocation.id>"`.
  - Si el vehículo aún no tiene ubicación móvil en `ubicaciones`, la opción usa el prefijo inequívoco `value="veh:<asset.id>"`.
- Al confirmar «Registrar bien», si el valor seleccionado comienza con `veh:`, el handler envía `destination_vehicle_asset_id: Number(rawLocVal.slice(4))` y `location_id: null` a `POST /inventory/assets`. No se realiza ninguna petición `POST /inventory/locations` al abrir el formulario ni al cambiar la selección.

### 5. Mover bien → Selección de destino físico o vehicular
- El modal `#modal-mover-bien` (`openMoverModalForAsset(assetId)`) permite trasladar un bien desde el listado general de Bienes, desde el detalle de una ubicación/categoría o desde la ficha de detalle del bien (`#btn-mover-desde-detalle`).
- `#mover-destino-select` se puebla mediante `buildDestinationOptionItems` con las ubicaciones físicas y los vehículos elegibles anidados bajo su lugar de estacionamiento, excluyendo automáticamente la ubicación actual del bien (`excludeLocationId`) y al propio bien (`excludeAssetId`).
- Al confirmar el traslado (`#form-mover-bien`), si el destino seleccionado tiene formato `veh:<asset.id>`, envía `destination_vehicle_asset_id` a `POST /inventory/assets/{asset_id}/transfers`; en caso contrario envía `destination_location_id`. Tras el guardado exitoso, `checkApiConnection()` refresca todas las vistas y habilita inmediatamente «Ver dotación» en el vehículo receptor.

---

## Autenticación, navegación por roles y entrega local

- **Autenticación y sesión:** `frontend/js/validations/credentials.js` y `frontend/js/auth-form.js` gestionan el inicio de sesión y el flujo de registro por invitación/solicitud. El servidor establece la cookie `fire_control_access` (`HttpOnly`, `SameSite=Lax`). Si falta una cookie válida, `/` redirige con `303` a `/iniciar-sesion`.
- **Control de vistas por rol (`FireNavigationController`):** `frontend/js/navigation.js` define las vistas permitidas para `ADMINISTRADOR` y `SUPERVISOR` (incluyendo `Dashboard`, `Bienes`, `Categorías`, `Ubicaciones`, `Vehículos`, `Movimientos`, `Nuevo bien`, `Nueva categoría`, `Nueva ubicación`, `Detalle de ubicación`, `Detalle de categoría` y `Detalle de bien`, reservando `Invitaciones` para `ADMINISTRADOR`).
- **Caché y ejecución de pruebas:** `app/main.py` aplica `Cache-Control: no-store` a HTML/CSS/JS y `/auth/*`. Las pruebas automatizadas del frontend se ejecutan sin dependencias externas mediante el test runner nativo de Node (`node --test frontend/tests/*.test.cjs`), contando con **85 pruebas aprobadas** que verifican los flujos de autenticación, navegación, renderizado real de ubicaciones/categorías/vehículos y registro/traslado transparente hacia vehículos.

---

## Limitaciones conocidas en la interfaz

1. **Indicador visual «En servicio»:** en las vistas de Vehículos y Detalle de bien, la etiqueta `En servicio` refleja que la ubicación móvil está activa (`active !== false`) o que el bien tiene ubicación asignada; no representa un módulo de mantenimiento mecánico ni de disponibilidad operativa en tiempo real.
2. **Métricas superiores del panel general (`Dashboard`):** mientras que las vistas de `Bienes`, `Categorías`, `Ubicaciones`, `Vehículos` y `Movimientos` operan íntegramente con datos reales de PostgreSQL, algunos indicadores y series comparativas por período (`90/180/365 días`) de la portada inicial (`frontend/js/data.js`) conservan valores ilustrativos.
3. **Preferencia de tema visual:** el conmutador claro/oscuro modifica `html[data-theme]` durante la sesión actual en memoria, sin persistir la preferencia tras recargar la página.

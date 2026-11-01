# ADR-007 — Habilitación automática y transaccional de vehículos como contenedores móviles

- **Estado:** aceptado; implementado.
- **Fecha de registro:** 2026-11-01.
- **Alcance:** registro de bienes (`POST /inventory/assets`), transferencia de bienes (`POST /inventory/assets/{asset_id}/transfers`), servicio compartido de contenedores vehiculares (`app/modules/inventory/shared/vehicle_container.py`) y selectores/vistas del frontend (`frontend/js/app.js`, `frontend/js/render.js`).

## Contexto

En el esquema relacional de Fire Control (revisión `e42c7910b6af`), un vehículo del cuartel interviene bajo dos facetas distintas:

1. **Vehículo patrimonial (`Asset` en la tabla `bienes`):** el rodado como activo inventariable (por ejemplo, `Camioneta HGJ-875`), con su propio código interno, categoría y ubicación física de estacionamiento (`bienes.ubicacion_id`, como `Playón delantero` o `Cuartel Central`).
2. **Vehículo como contenedor móvil (`Location` en la tabla `ubicaciones`):** una ubicación con `tipo_ubicacion = 'VEHICULO'` vinculada al bien mediante `ubicaciones.bien_contenedor_id = bienes.id`, en la cual se asignan o trasladan las herramientas y equipos transportados a bordo (`bienes.ubicacion_id = ubicacion_vehiculo.id`).

Cuando un usuario registraba una camioneta como bien patrimonial dentro de la categoría «Vehículo», el rodado existía en `bienes`, pero todavía no tenía una fila asociada en `ubicaciones`. Exigir que el operador creara manualmente una ubicación de tipo `VEHICULO` antes de poder cargarle un equipo obligaba a realizar dos altas manuales, exponía conceptos internos del esquema relacional en la interfaz y dificultaba la operación cotidiana del personal de bomberos.

## Decisión

**Permitir que un vehículo patrimonial actúe automáticamente como contenedor móvil cuando sea seleccionado como destino de un bien**, tanto durante el alta inicial (`POST /inventory/assets`) como durante un traslado (`POST /inventory/assets/{asset_id}/transfers`), de manera completamente transparente para el usuario y dentro de una única transacción SQLAlchemy.

- **Motivación:** simplificar la operación del personal de bomberos sin comprometer la integridad referencial, la unicidad ni la prevención de ciclos de datos.
- **Mecanismo implementado:**
  1. Los contratos `RegisterAssetRequest` y `TransferAssetRequest` aceptan el campo explícito `destination_vehicle_asset_id` (mutuamente excluyente con `location_id` / `destination_location_id`) para evitar toda ambigüedad entre el ID de una ubicación (`ubicaciones.id`) y el ID de un bien vehicular (`bienes.id`).
  2. La función `resolve_or_create_vehicle_location(session, vehicle_asset_id)` en `app/modules/inventory/shared/vehicle_container.py` bloquea la fila del vehículo con `SELECT ... FOR UPDATE`:
     - Si ya existe una fila en `ubicaciones` con `bien_contenedor_id = vehicle_asset_id`, verifica que esté activa y la reutiliza.
     - Si no existe, valida que el bien pertenezca a una categoría elegible (`is_exact_vehicle_category_name`, coincidencia exacta normalizada NFD con `"vehiculo"` o `"vehiculos"`) e inserta `Location(tipo_ubicacion="VEHICULO", bien_contenedor_id=vehicle_asset.id, ...)` mediante `INSERT ... ON CONFLICT (bien_contenedor_id) WHERE bien_contenedor_id IS NOT NULL DO NOTHING RETURNING id` sin ejecutar `commit()`.
  3. El alta del bien o el registro del movimiento `TRASLADO` y la creación del contenedor móvil se confirman juntos en un único `await session.commit()`, o se revierten íntegramente con `await session.rollback()` ante cualquier error.
  4. El `ubicacion_id` del propio vehículo patrimonial (su lugar de estacionamiento físico) no se modifica al crear ni al utilizar su contenedor móvil.
  5. En el frontend, los selectores de «Nuevo bien» y «Mover bien» muestran los vehículos elegibles anidados bajo su ubicación física de estacionamiento (`value="<location.id>"` si ya tienen contenedor móvil o `value="veh:<asset.id>"` si aún no lo tienen), sin mostrar avisos técnicos ni botones de habilitación manual.

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| **Exigir dos altas manuales (primero en Bienes y luego en Ubicaciones)** | Fricción operativa innecesaria y propensa a omisiones: los vehículos registrados solo como bienes no podían recibir dotación directamente. |
| **Crear la ubicación móvil desde el frontend mediante `POST /inventory/locations` antes de guardar el bien o traslado** | Rompe la atomicidad: si la segunda petición (`POST /inventory/assets` o `/transfers`) falla por código duplicado o validación, quedaría persistida una ubicación móvil huérfana en la base de datos. |
| **Crear contenedores móviles automáticamente durante consultas `GET`** | Viola la semántica de solo lectura de `GET` y genera escrituras colaterales no solicitadas por el usuario. |
| **Reutilizar el mismo campo `location_id` para enviar indistintamente IDs de `ubicaciones` o de `bienes`** | Introduce ambigüedad crítica de claves primarias: un mismo entero (por ejemplo, `5`) puede existir tanto en `ubicaciones.id` como en `bienes.id`. |

## Consecuencias

- **Positivas:**
  - Automatización transparente en el backend: el usuario selecciona directamente el vehículo como destino al registrar o mover un bien.
  - Atomicidad transaccional garantizada: ante cualquier fallo de validación o restricción, el `rollback` revierte tanto el bien/movimiento como el contenedor móvil creado en esa transacción.
  - Seguridad ante concurrencia: la combinación de `SELECT ... FOR UPDATE` sobre `Asset`, el índice único parcial `uq_ubicaciones_bien_contenedor_id` y `ON CONFLICT DO NOTHING` evita duplicados y abortos de transacción bajo peticiones simultáneas.
  - Separación clara entre la ubicación física donde está estacionado el vehículo (`vehicle_asset.ubicacion_id`) y la dotación transportada dentro de su contenedor móvil (`equipment_asset.ubicacion_id`).
- **Límites actuales:**
  - Para vehículos que aún no tienen una fila `Location(VEHICULO)`, la elegibilidad depende actualmente de que el nombre de su categoría normalizado coincida exactamente con `"vehiculo"` o `"vehiculos"` (`is_exact_vehicle_category_name`). En una evolución futura del esquema puede incorporarse un atributo booleano o tipo estructural en la tabla `categorias`.

## Evidencia

- Backend: `app/modules/inventory/shared/vehicle_container.py`, `app/modules/inventory/register_asset/schemas.py`, `app/modules/inventory/register_asset/service.py`, `app/modules/inventory/register_asset/router.py`, `app/modules/inventory/transfer_asset/schemas.py`, `app/modules/inventory/transfer_asset/service.py`, `app/modules/inventory/transfer_asset/router.py`.
- Frontend: `frontend/index.html`, `frontend/js/app.js`, `frontend/js/render.js`.
- Pruebas automatizadas: `tests/modules/inventory/test_location_endpoints.py`, `frontend/tests/modal-mover-bien.test.cjs`, `frontend/tests/dashboard-real-data.test.cjs`.

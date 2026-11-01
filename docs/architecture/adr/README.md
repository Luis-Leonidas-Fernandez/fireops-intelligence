# Registro de decisiones arquitectónicas

Un ADR documenta una decisión concreta, su contexto, alternativas y consecuencias. **No** reemplaza las guías que explican el comportamiento actual ni convierte una propuesta en código existente.

| ADR | Estado | Tema |
|---|---|---|
| [ADR-001](ADR-001-backend-architecture.md) | Registro retrospectivo del estado inicial | Organización de FastAPI y routers de inventario |
| [ADR-002](ADR-002-database-persistence.md) | Registro retrospectivo del estado inicial | PostgreSQL, SQLAlchemy asíncrono y Alembic |
| [ADR-003](ADR-003-frontend-architecture.md) | Registro retrospectivo del estado inicial | Web HTML/CSS/JS servida por FastAPI; React diferido |
| [ADR-004](ADR-004-testing-database-isolation.md) | Aceptado; implementado | Transacción, SAVEPOINT y rollback por test en autenticación e inventario |
| [ADR-005](ADR-005-email-password-authentication.md) | Aceptado; implementado | Registro/login con Argon2, JWT en cookie y límites de autorización |
| [ADR-006](ADR-006-google-oauth-identity.md) | Aceptado; implementado | Identidad Google, vinculación explícita y sesión local |
| [ADR-007](ADR-007-automatic-vehicle-containers.md) | Aceptado; implementado | Habilitación automática y transaccional de vehículos como contenedores móviles |

## Historial cronológico de decisiones recientes

- **2026-10-03 ([ADR-001](ADR-001-backend-architecture.md) a [ADR-004](ADR-004-testing-database-isolation.md)):** consolidación inicial del monolito modular en FastAPI, persistencia relacional asíncrona con PostgreSQL/Alembic, frontend HTML/CSS/JS servido en el mismo origen y estrategia de aislamiento transaccional con `SAVEPOINT` para las pruebas automatizadas sobre `fireassets_test` (`tests/modules/inventory/conftest.py` y `tests/modules/auth/conftest.py`).
- **2026-10-04 ([ADR-005](ADR-005-email-password-authentication.md) y [ADR-006](ADR-006-google-oauth-identity.md)):** autenticación local con Argon2 y JWT HS256 en cookie `HttpOnly` e integración de identidad con Google OAuth en el servidor.
- **2026-11-01 ([ADR-007](ADR-007-automatic-vehicle-containers.md)):**
  - **Decisión:** permitir que un vehículo patrimonial actúe automáticamente como contenedor móvil cuando sea seleccionado como destino de un bien.
  - **Motivación:** simplificar la operación del personal de bomberos sin comprometer la integridad de datos.
  - **Consecuencias:** automatización en backend (`resolve_or_create_vehicle_location`), transacciones atómicas, reutilización de contenedores y separación entre ubicación física de estacionamiento y dotación transportada.

## Convención para próximos ADR

Use el siguiente número correlativo y un nombre específico. Indique **estado**, **fecha**, **contexto**, **decisión**, **alternativas**, **consecuencias** y **evidencia en el repositorio**. Si todavía no se implementó, márquelo como propuesto; al implementar o cambiar la decisión, actualice su estado con evidencia. No copie las propuestas de los Word históricos como si fueran comportamiento vigente.

Para recorrer los componentes reales, consulte [backend](../backend/backend-architecture.md) y [frontend](../frontend/frontend-architecture.md).

# Registro de decisiones arquitectónicas

Un ADR documenta una decisión concreta, su contexto, alternativas y consecuencias. **No** reemplaza las guías que explican el comportamiento actual ni convierte una propuesta en código existente.

| ADR | Estado | Tema |
|---|---|---|
| [ADR-001](ADR-001-backend-architecture.md) | Registro retrospectivo del estado actual | Organización de FastAPI y routers de inventario |
| [ADR-002](ADR-002-database-persistence.md) | Registro retrospectivo del estado actual | PostgreSQL, SQLAlchemy asíncrono y Alembic |
| [ADR-003](ADR-003-frontend-architecture.md) | Registro retrospectivo del estado actual | Web HTML/CSS/JS servida por FastAPI; React diferido |
| [ADR-004](ADR-004-testing-database-isolation.md) | **Propuesto; no implementado** | Transacción, SAVEPOINT y rollback por test de Task 06 |

## Convención para próximos ADR

Use el siguiente número correlativo y un nombre específico. Indique **estado**, **fecha**, **contexto**, **decisión**, **alternativas**, **consecuencias** y **evidencia en el repositorio**. Si todavía no se implementó, márquelo como propuesto; al implementar o cambiar la decisión, actualice su estado con evidencia. No copie las propuestas de los Word históricos como si fueran comportamiento vigente.

Para recorrer los componentes reales, consulte [backend](../backend/backend-architecture.md) y [frontend](../frontend/frontend-architecture.md).

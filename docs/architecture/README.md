# Arquitectura del proyecto

Este índice distingue el **sistema que existe** de las **decisiones que lo explican** y de las propuestas históricas de la fase inicial.

## Estado actual

- [Backend](backend/backend-architecture.md): FastAPI, arquitectura de inventario (bienes, categorías, ubicaciones físicas y contenedores vehiculares automáticos), integridad y concurrencia, contratos de API, diagramas técnicos y persistencia.
- [Frontend](frontend/frontend-architecture.md): vistas operativas de Bienes, Categorías, Ubicaciones, Vehículos y Movimientos, navegación contextual, selectores jerárquicos de destino y control por roles.

## Decisiones

El [índice de ADR](adr/README.md) reúne los registros de decisiones arquitectónicas vigentes ([ADR-001](adr/ADR-001-backend-architecture.md) a [ADR-007](adr/ADR-007-automatic-vehicle-containers.md)), incluyendo el aislamiento transaccional de pruebas ([ADR-004](adr/ADR-004-testing-database-isolation.md)) y la habilitación automática y transaccional de vehículos como contenedores móviles ([ADR-007](adr/ADR-007-automatic-vehicle-containers.md)).

## Diagramas

Los diagramas técnicos de la implementación actual (modelo conceptual Bien–Ubicación–Vehículo, flujos transaccionales de alta y traslado hacia vehículos y resolución concurrente de contenedores móviles) se encuentran integrados en [Arquitectura del backend](backend/backend-architecture.md#diagramas-técnicos). Los modelos gráficos iniciales de la Fase 01 permanecen en [`Phase_01/data-modeling/modelado`](../Phase_01/data-modeling/modelado/).

Los informes de análisis inicial convertidos desde Word se conservan como referencia histórica en [`history/architecture-history`](history/architecture-history/). No agregue ADR nuevos allí.

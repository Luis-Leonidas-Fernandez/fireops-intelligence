# Arquitectura del proyecto

Este índice distingue el **sistema que existe** de las **decisiones que lo explican** y de las propuestas que todavía requieren implementación.

## Estado actual

- [Backend](backend/backend-architecture.md): FastAPI, routers de inventario, schemas, sesiones y endpoints registrados.
- [Frontend](frontend/frontend-architecture.md): páginas HTML/CSS/JS, datos de demostración, navegación y límites de autenticación.

## Decisiones

El [índice de ADR](adr/README.md) reúne registros concretos. ADR-001, ADR-002 y ADR-003 documentan decisiones observables en el código actual; ADR-004 es una **propuesta** para la Task 06, no una fixture ya disponible.

## Diagramas

`diagrams/` está reservado para diagramas futuros y permanece vacío por ahora (salvo `.gitkeep` para que Git conserve la carpeta). Los modelos de datos de la fase inicial permanecen en [`Phase_01/data-modeling/modelado`](../Phase_01/data-modeling/modelado/), no se movieron aquí.

Los informes históricos se encuentran en [`history/architecture-history`](history/architecture-history/). No agregue ADR nuevos allí.

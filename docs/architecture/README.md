# Arquitectura del proyecto

Este índice distingue el **sistema que existe** de las **decisiones que lo explican** y de las propuestas que todavía requieren implementación.

## Estado actual

- [Backend](backend/backend-architecture.md): FastAPI, inventario, autenticación, persistencia y endpoints registrados.
- [Frontend](frontend/frontend-architecture.md): páginas HTML/CSS/JS, formularios conectados y datos de demostración.

## Decisiones

El [índice de ADR](adr/README.md) reúne registros concretos. ADR-001, ADR-002, ADR-003, ADR-005 y ADR-006 documentan decisiones observables en el código actual. ADR-004 sigue siendo una **propuesta para Task 06**, aunque la suite de autenticación ya usa una fixture transaccional de alcance propio.

## Diagramas

`diagrams/` está reservado para diagramas futuros y permanece vacío por ahora (salvo `.gitkeep` para que Git conserve la carpeta). Los modelos de datos de la fase inicial permanecen en [`Phase_01/data-modeling/modelado`](../Phase_01/data-modeling/modelado/), no se movieron aquí.

Los informes históricos se encuentran en [`history/architecture-history`](history/architecture-history/). No agregue ADR nuevos allí.

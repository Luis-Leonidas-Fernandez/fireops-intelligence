**PROPUESTA TÉCNICA**

> Documento histórico convertido desde el archivo Word. Su contenido refleja el análisis original y no necesariamente el estado implementado del proyecto.

# Requisitos no funcionales

**Sistema web de inventario patrimonial para una unidad de Bomberos**

Documento inicial para análisis, validación y planificación del MVP

| **Objetivo del documento**  
Definir las cualidades técnicas y operativas que deberá cumplir el sistema, priorizando integridad de datos, trazabilidad, simplicidad, capacidad de evolución y facilidad de mantenimiento. |
| --- |

Base conceptual: capítulo 2 de Designing Data-Intensive Applications, 2.ª edición

Fecha: julio de 2026

## 1. Propósito y alcance

Este documento convierte los conceptos de rendimiento, confiabilidad, escalabilidad y mantenibilidad en requisitos verificables para la primera versión del sistema de inventario patrimonial de la unidad de Bomberos.

El sistema deberá registrar bienes, altas, bajas, estado de conservación, situación operativa, ubicaciones, responsables, fotografías, documentación y movimientos históricos. También deberá permitir que personal autorizado configure categorías y campos adicionales sin modificar la estructura esencial de la base de datos.

## 2. Criterios de prioridad

| **Prioridad** | **Interpretación** | **Aplicación en el MVP** |
| --- | --- | --- |
| Obligatorio | Debe existir para considerar utilizable y seguro el sistema. | Se implementa antes de la puesta en producción. |
| Deseable | Aporta calidad operativa, pero puede incorporarse durante la estabilización. | Se incluye si el tiempo y presupuesto del MVP lo permiten. |
| Futuro | Se reserva para una fase posterior, cuando exista uso real y métricas. | No debe complicar la arquitectura inicial. |

## 3. Rendimiento

| **ID** | **Prioridad** | **Tema** | **Requisito** | **Criterio de aceptación** |
| --- | --- | --- | --- | --- |
| **RNF-REN-01** | Obligatorio | Búsquedas comunes | La búsqueda por código, nombre, categoría, estado, ubicación o responsable deberá responder en un tiempo percibido como inmediato bajo la carga prevista del MVP. | Medir p50 y p95 en pruebas con datos representativos. |
| **RNF-REN-02** | Obligatorio | Apertura de fichas | La ficha de un bien deberá cargar sus datos principales sin esperar la descarga completa de fotografías o documentos pesados. | Los adjuntos se cargarán de forma diferida o progresiva. |
| **RNF-REN-03** | Obligatorio | Guardado de cambios | El usuario deberá recibir confirmación clara de éxito o error al registrar altas, bajas, movimientos o modificaciones. | No se mostrará éxito hasta confirmar la transacción principal. |
| **RNF-REN-04** | Deseable | Medición de tiempos | El backend deberá registrar duración, ruta, método y código de respuesta de las operaciones relevantes. | Los registros permitirán identificar consultas lentas y errores. |
| **RNF-REN-05** | Futuro | Exportaciones pesadas | Las exportaciones grandes podrán procesarse de manera asincrónica para no bloquear el uso normal del sistema. | Aplicar cuando el volumen real lo justifique. |

## 4. Confiabilidad e integridad de datos

| **ID** | **Prioridad** | **Tema** | **Requisito** | **Criterio de aceptación** |
| --- | --- | --- | --- | --- |
| **RNF-CON-01** | Obligatorio | Fuente oficial | PostgreSQL será la fuente oficial y autoritativa de los datos patrimoniales. | Las planillas, PDF, paneles y copias serán datos derivados. |
| **RNF-CON-02** | Obligatorio | Atomicidad de operaciones | Las operaciones críticas deberán ejecutarse mediante transacciones. | El alta de un bien y su movimiento inicial se guardarán juntos o no se guardará ninguno. |
| **RNF-CON-03** | Obligatorio | Baja lógica | Los bienes no se eliminarán físicamente desde la interfaz ordinaria. | La baja conservará identificación, fecha, motivo, responsable y antecedentes. |
| **RNF-CON-04** | Obligatorio | Historial de movimientos | Toda modificación sensible deberá generar un registro histórico. | Debe incluir usuario, fecha, tipo de movimiento, motivo y valores anteriores/nuevos. |
| **RNF-CON-05** | Obligatorio | Prevención de duplicados | El sistema deberá impedir códigos patrimoniales duplicados y aplicar restricciones de unicidad donde corresponda. | La validación se realizará en aplicación y base de datos. |
| **RNF-CON-06** | Obligatorio | Copias de seguridad | Se realizarán respaldos automáticos periódicos de la base de datos y archivos asociados. | Definir frecuencia, retención y ubicación separada del servidor principal. |
| **RNF-CON-07** | Obligatorio | Restauración comprobada | La existencia de una copia no se considerará suficiente sin una prueba periódica de restauración. | Documentar procedimiento y resultado de cada prueba. |
| **RNF-CON-08** | Obligatorio | Errores parciales | La falla al cargar un adjunto no deberá provocar la pérdida silenciosa del registro principal. | El sistema informará el adjunto pendiente o permitirá reintentar. |
| **RNF-CON-09** | Deseable | Control de concurrencia | El sistema deberá evitar que dos usuarios sobrescriban silenciosamente cambios simultáneos. | Usar versión del registro, fecha de actualización o bloqueo optimista. |

## 5. Seguridad, permisos y auditoría

| **ID** | **Prioridad** | **Tema** | **Requisito** | **Criterio de aceptación** |
| --- | --- | --- | --- | --- |
| **RNF-SEG-01** | Obligatorio | Autenticación | Toda persona que modifique información deberá ingresar con una cuenta individual. | No usar cuentas compartidas para operaciones patrimoniales. |
| **RNF-SEG-02** | Obligatorio | Roles | Los permisos deberán separarse por función. | Como mínimo: usuario de carga, responsable de patrimonio y administrador. |
| **RNF-SEG-03** | Obligatorio | Configuración restringida | Solo personal autorizado podrá crear categorías, campos personalizados, estados u opciones de listas. | El usuario común solo podrá utilizar formularios aprobados. |
| **RNF-SEG-04** | Obligatorio | Auditoría | Las operaciones sensibles deberán ser atribuibles a una cuenta y una fecha. | Registrar altas, bajas, cambios de estado, asignaciones y modificaciones de configuración. |
| **RNF-SEG-05** | Obligatorio | Protección de credenciales | Las contraseñas no deberán almacenarse en texto plano. | Usar algoritmos de hash adecuados y variables de entorno para secretos. |
| **RNF-SEG-06** | Deseable | Sesiones y bloqueo | Las sesiones deberán expirar y podrán revocarse ante pérdida de acceso o cambio de funciones. | Definir duración y política administrativa. |

## 6. Escalabilidad y capacidad

| **ID** | **Prioridad** | **Tema** | **Requisito** | **Criterio de aceptación** |
| --- | --- | --- | --- | --- |
| **RNF-ESC-01** | Obligatorio | Carga prevista | La arquitectura se dimensionará con base en bienes, movimientos, usuarios simultáneos, adjuntos y exportaciones esperadas. | Evitar diseñar para millones de usuarios sin evidencia. |
| **RNF-ESC-02** | Obligatorio | Arquitectura inicial | El MVP se implementará como monolito modular con una base PostgreSQL. | No incorporar microservicios, sharding o colas sin necesidad demostrada. |
| **RNF-ESC-03** | Obligatorio | Adjuntos externos | Las fotografías y documentos se almacenarán fuera de las filas principales de la base. | La base conservará referencias, metadatos e integridad de relación. |
| **RNF-ESC-04** | Deseable | Escalado vertical | El sistema deberá poder migrarse a un servidor con más CPU, RAM o almacenamiento sin rediseño completo. | Documentar dependencias y configuración. |
| **RNF-ESC-05** | Futuro | Procesamiento distribuido | La distribución en múltiples servidores solo se evaluará si las métricas reales muestran necesidad. | No forma parte de la primera versión. |

## 7. Mantenibilidad y operabilidad

| **ID** | **Prioridad** | **Tema** | **Requisito** | **Criterio de aceptación** |
| --- | --- | --- | --- | --- |
| **RNF-MAN-01** | Obligatorio | Monolito modular | El código se organizará en módulos claros y con responsabilidades separadas. | Bienes, categorías, campos, movimientos, usuarios, archivos y reportes. |
| **RNF-MAN-02** | Obligatorio | Documentación técnica | El proyecto deberá incluir instrucciones de instalación, configuración, despliegue, respaldo y restauración. | Otro programador debe poder continuar el mantenimiento. |
| **RNF-MAN-03** | Obligatorio | Configuración externa | Credenciales, rutas y parámetros de entorno no deberán quedar codificados en el repositorio. | Utilizar variables de entorno y archivo de ejemplo sin secretos. |
| **RNF-MAN-04** | Obligatorio | Migraciones | Los cambios estructurales de base de datos deberán registrarse mediante migraciones versionadas. | No modificar manualmente producción sin historial reproducible. |
| **RNF-MAN-05** | Obligatorio | Pruebas mínimas | Las reglas críticas deberán contar con pruebas automatizadas. | Códigos únicos, permisos, bajas, transacciones y validaciones. |
| **RNF-MAN-06** | Deseable | Observabilidad básica | El sistema deberá ofrecer logs comprensibles y una verificación de salud. | Permitir diagnosticar errores sin depender de la memoria del desarrollador. |
| **RNF-MAN-07** | Deseable | Reversión | Una actualización deberá poder revertirse o restaurarse ante fallos graves. | Respaldar antes de cambios importantes y documentar rollback. |

## 8. Evolución del modelo de datos

| **ID** | **Prioridad** | **Tema** | **Requisito** | **Criterio de aceptación** |
| --- | --- | --- | --- | --- |
| **RNF-EVO-01** | Obligatorio | Núcleo estable | Los datos comunes de todos los bienes se almacenarán en campos relacionales estables. | Código, nombre, categoría, condición, situación, ubicación, fechas y responsable. |
| **RNF-EVO-02** | Obligatorio | Campos variables | Los atributos específicos se configurarán por categoría sin crear columnas físicas desde la interfaz. | Usar definiciones de campos y almacenamiento flexible controlado. |
| **RNF-EVO-03** | Obligatorio | Compatibilidad histórica | Agregar o desactivar un campo no deberá impedir la lectura de registros anteriores. | Los campos se marcarán activos, inactivos u obsoletos en lugar de borrarse sin control. |
| **RNF-EVO-04** | Obligatorio | Identificador estable de campo | Cada campo personalizado deberá tener una clave técnica estable independiente de su etiqueta visible. | Cambiar “Nro. de serie” por “Número de serie” no debe perder valores. |
| **RNF-EVO-05** | Obligatorio | Tipos y validación | Cada campo deberá declarar tipo, obligatoriedad, opciones y reglas de validación. | Texto, número, fecha, sí/no, lista y archivo en el MVP. |
| **RNF-EVO-06** | Deseable | Versionado de formularios | El sistema podrá conservar la versión de la definición utilizada al registrar cada bien. | Útil cuando cambien requisitos patrimoniales. |

## 9. Usabilidad y prevención de errores humanos

| **ID** | **Prioridad** | **Tema** | **Requisito** | **Criterio de aceptación** |
| --- | --- | --- | --- | --- |
| **RNF-USA-01** | Obligatorio | Confirmación de acciones | Las bajas y acciones destructivas deberán exigir confirmación explícita. | Mostrar el bien, el efecto y el motivo antes de aceptar. |
| **RNF-USA-02** | Obligatorio | Listas normalizadas | Los estados, situaciones y categorías se seleccionarán desde opciones controladas. | Evitar variantes como “Bueno”, “OK” o “Funciona”. |
| **RNF-USA-03** | Obligatorio | Mensajes comprensibles | Los errores deberán explicar qué ocurrió y qué puede hacer el usuario. | No mostrar únicamente mensajes técnicos o códigos internos. |
| **RNF-USA-04** | Obligatorio | Validación temprana | Fechas, cantidades, códigos y campos obligatorios se validarán antes del envío y nuevamente en el servidor. | La base de datos conservará restricciones críticas. |
| **RNF-USA-05** | Deseable | Ayuda contextual | Los campos configurables podrán incluir una descripción o ejemplo. | Reducir errores de carga y dependencia del programador. |

## 10. Requisitos excluidos del MVP

- Funcionamiento completo sin conexión y sincronización posterior.

- Microservicios, Kubernetes, Kafka, sharding o replicación multi-región.

- Analítica avanzada, data warehouse o procesamiento en tiempo real.

- Firma digital con validez jurídica e integración contable o provincial.

- Aplicación móvil nativa independiente, salvo que el uso real demuestre su necesidad.

## 11. Decisión arquitectónica inicial

| **El sistema será una aplicación web monolítica modular, con PostgreSQL como fuente oficial de datos. Priorizará integridad, trazabilidad, simplicidad operativa y capacidad de evolución por encima de la escalabilidad distribuida. Los cambios importantes se registrarán mediante movimientos históricos y operaciones transaccionales. Los campos variables se configurarán por categoría sin alterar el núcleo estable de los bienes.** |
| --- |

## 12. Validación con la unidad de Bomberos

Antes de cerrar estos requisitos, deberán validarse con al menos un responsable de patrimonio y un usuario que realizará la carga diaria. La validación deberá confirmar:

- cantidad aproximada de bienes y usuarios;

- flujo real de altas, bajas, préstamos, mantenimiento y asignaciones;

- estados y situaciones oficiales utilizados por la unidad;

- documentos obligatorios para justificar movimientos;

- frecuencia de respaldo y responsables de autorizar restauraciones;

- nivel de conectividad disponible en la sede;

- roles y personas autorizadas para modificar formularios.

## Referencia

Kleppmann, Martin y Chris Riccomini. Designing Data-Intensive Applications: The Big Ideas Behind Reliable, Scalable, and Maintainable Systems, 2.ª edición. O’Reilly Media, 2026. Capítulo 2: “Defining Nonfunctional Requirements”.

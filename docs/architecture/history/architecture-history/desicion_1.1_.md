# INFORME TÉCNICO DE DECISIONES ARQUITECTÓNICAS

> Documento histórico convertido desde el archivo Word. Su contenido refleja el análisis original y no necesariamente el estado implementado del proyecto.

**Sistema web de inventario patrimonial para una unidad de Bomberos**

*Documento vivo para diseño, implementación y revisión técnica*

| **Versión** | 1.0 |
| --- | --- |
| **Estado** | Propuesta técnica para validación |
| **Fecha** | 30 de julio de 2026 |
| **Base conceptual** | Designing Data-Intensive Applications, 2.ª edición |
| **Base de datos objetivo** | PostgreSQL |
| **Arquitectura propuesta** | Monolito modular con modelo relacional + JSONB |

# Resumen ejecutivo

La unidad de Bomberos necesita digitalizar el inventario de todo su patrimonio: altas, bajas, estado de conservación, situación operativa, ubicación, responsables, archivos y detalles particulares de elementos muy diferentes entre sí. Al momento del relevamiento inicial no existe una lista cerrada de categorías ni de campos requeridos.

| **Decisión central**  
Usar PostgreSQL como fuente oficial y aplicar un modelo híbrido: tablas relacionales para la información estable y relacionada; JSONB para atributos variables definidos mediante metadatos configurables. |
| --- |

El sistema se diseñará como un monolito modular. Las operaciones sensibles conservarán trazabilidad, las correcciones registrarán quién cambió qué y por qué, y la eliminación habitual será lógica. El diseño prioriza integridad, mantenibilidad y capacidad de evolución por encima de la complejidad distribuida.

## Contenido del informe

- Contexto, alcance y supuestos.

- Principios rectores.

- Arquitectura general.

- Decisiones de modelado y persistencia.

- Campos dinámicos y evolución del esquema.

- Transacciones, concurrencia y auditoría.

- Índices, consultas y rendimiento.

- Confiabilidad, seguridad y privacidad.

- Decisiones pendientes, riesgos y hoja de ruta.

# 1. Contexto y problema

La primera necesidad priorizada por la unidad es digitalizar el inventario patrimonial. Entre los elementos observados se encuentran cascos, chaquetas, pantalones, tubos de aire, motores portátiles, camiones, camionetas, televisores, heladeras, cámaras, computadoras, mesas y sillas.

La dificultad principal es que cada categoría requiere datos diferentes. Un vehículo puede necesitar dominio, número de motor y kilometraje; un tubo puede requerir capacidad, presión y fecha de prueba; una prenda puede necesitar talle y estado; una computadora puede requerir número de serie y especificaciones técnicas.

El sistema no debe obligar a modificar la base de datos cada vez que aparece una nueva necesidad, pero tampoco debe permitir que cualquier información sea guardada sin estructura ni validación.

## 1.1 Alcance del MVP

- Administración de usuarios y roles.

- Categorías simples, sin subcategorías.

- Alta, modificación, baja y eliminación lógica de bienes.

- Bienes individuales y una solución provisional para bienes agrupados.

- Múltiples responsables por bien.

- Ubicaciones físicas y vehículos que también funcionan como ubicaciones.

- Campos personalizados por categoría.

- Fotografías y documentos asociados.

- Movimientos e historial de auditoría.

- Búsqueda, filtros y exportación inicial.

## 1.2 Fuera del alcance inicial

- Microservicios, Kubernetes o arquitectura distribuida.

- Sharding, consenso o operación multi-región.

- Event Sourcing completo.

- Data warehouse y analítica avanzada.

- Funcionamiento offline/local-first.

- Gestión avanzada de lotes y series para bienes agrupados.

- Mantenimiento predictivo, visión artificial o sensores.

# 2. Principios rectores

| **Principio** | **Aplicación** |
| --- | --- |
| **Integridad antes que flexibilidad irrestricta** | Los campos dinámicos se permiten, pero bajo definiciones y validaciones controladas. |
| **Una fuente oficial** | PostgreSQL será el sistema de registro; Excel, PDF y paneles serán datos derivados. |
| **Trazabilidad** | Toda baja, corrección, asignación, traslado o eliminación deberá identificar usuario, fecha y motivo. |
| **Simplicidad operativa** | Se prefiere un monolito modular antes que componentes distribuidos innecesarios. |
| **Evolución segura** | Los cambios futuros deben preservar la interpretación de los datos históricos. |
| **Separación de responsabilidades** | El dominio no dependerá directamente del ORM ni de filas SQL sin procesar. |

# 3. Arquitectura general

Se propone una aplicación web monolítica modular. Esto significa una sola aplicación desplegable, organizada internamente en módulos claros, con PostgreSQL como base principal y almacenamiento externo para fotografías y documentos.

| **Arquitectura propuesta**  
Frontend web + API REST + servicios de aplicación + repositorios + PostgreSQL + almacenamiento de archivos. |
| --- |

## 3.1 Módulos iniciales

- Usuarios y roles.

- Categorías y definiciones de campos.

- Bienes y responsables.

- Ubicaciones.

- Movimientos.

- Archivos.

- Auditoría.

- Reportes y exportaciones.

## 3.2 Motivo para no usar microservicios

El volumen esperado, la cantidad de usuarios y el equipo de desarrollo no justifican coordinación distribuida. Separar prematuramente servicios aumentaría despliegues, fallos de red, observabilidad y mantenimiento sin aportar una ventaja proporcional.

# 4. Decisiones principales de arquitectura

| **Decisión** | **Motivo** | **Alternativa considerada** | **Consecuencia** |
| --- | --- | --- | --- |
| **PostgreSQL como base principal** | Ofrece relaciones, claves foráneas, restricciones, transacciones, índices y JSONB. | MongoDB, SQLite o archivos JSON como fuente oficial. | Mayor integridad y mejores consultas; requiere migraciones y administración de PostgreSQL. |
| **Modelo híbrido relacional + JSONB** | Los datos centrales son estables, pero los atributos varían por categoría. | Todo relacional con columnas dinámicas o todo documental. | Equilibra consistencia y flexibilidad; exige validación estricta del JSONB. |
| **Monolito modular** | El dominio puede separarse por módulos sin distribuir el sistema. | Microservicios. | Menos complejidad operativa y despliegue más simple. |
| **API REST para el MVP** | Las operaciones son previsibles y REST es suficiente para el frontend. | GraphQL. | Contrato simple y fácil de documentar; GraphQL puede evaluarse más adelante. |
| **Repositorio como frontera de persistencia** | Los servicios no deben depender de Prisma, Kysely o filas SQL. | Acceso directo desde controladores o servicios. | Permite cambiar la estrategia de acceso sin afectar todo el backend. |

# 5. Modelo de datos

El modelo físico incluye roles, usuarios, categorías, definiciones de campo, ubicaciones, bienes, responsables, movimientos, archivos y auditoría.

![Modelo físico del inventario](../../../Phase_01/data-modeling/modelado/modelo-fisico-II.png)

*Figura 1. Modelo físico corregido propuesto.*

## 5.1 Entidades principales

- **roles**: Define permisos generales.

- **usuarios**: Personas que acceden, asignan, corrigen o quedan responsables.

- **categorias**: Clasificación simple de bienes.

- **definiciones_campo**: Metadatos de los campos personalizados permitidos.

- **ubicaciones**: Lugares físicos o vehículos contenedores.

- **bienes**: Estado actual del patrimonio.

- **bienes_responsables**: Relación muchos-a-muchos con atributos propios.

- **movimientos**: Historia operativa de cada bien.

- **archivos**: Documentación y fotografías.

- **auditoria_cambios**: Correcciones, eliminaciones y acciones transversales.

## 5.2 Normalización

Categoría, ubicación, responsable y rol se guardan una sola vez y se referencian mediante claves foráneas. No se duplicarán sus nombres dentro de bienes ni dentro de datos_especificos.

| **Regla de normalización**  
Los datos compartidos o sujetos a cambios globales se almacenan en tablas. La desnormalización se reserva para respuestas de API, vistas, reportes y exportaciones. |
| --- |

## 5.3 Relaciones

- Muchos usuarios pertenecen a un rol.

- Muchos bienes pertenecen a una categoría.

- Muchos bienes pueden estar en una ubicación.

- Un bien puede tener muchos movimientos y archivos.

- Bienes y responsables se relacionan muchos-a-muchos mediante bienes_responsables.

# 6. Campos dinámicos y JSONB

Los usuarios autorizados no crearán columnas físicas. Crearán definiciones de campo desde un panel, similar a crear preguntas en un formulario.

## 6.1 Datos mínimos de una definición

- Categoría.

- Clave técnica única.

- Etiqueta visible.

- Tipo de dato.

- Obligatoriedad.

- Opciones permitidas.

- Orden de visualización.

- Estado activo o inactivo.

## 6.2 Política de evolución

- Un campo sin datos puede editarse libremente.

- Un campo ya utilizado puede cambiar etiqueta u orden.

- No debe cambiarse destructivamente la clave o el tipo de un campo utilizado.

- Para reemplazarlo, se desactiva la definición anterior y se crea una nueva.

- Los registros históricos conservan los datos previos.

## 6.3 Riesgos controlados

Sin validación podrían aparecer claves como marca, Marca, fabricante o marcaDelEquipo. El backend validará que cada clave exista, que el tipo sea correcto y que los obligatorios estén presentes.

# 7. Identidad, códigos y agrupación

## 7.1 Identificadores

- id: identificador técnico interno de PostgreSQL.

- codigo_interno: obligatorio y único, generado por el sistema.

- codigo_patrimonial: opcional y único cuando exista.

## 7.2 Bien individual y agrupado

La versión inicial usará tipo_registro = INDIVIDUAL o AGRUPADO. Un bien individual debe tener cantidad 1; un bien agrupado mantiene cantidad_actual positiva.

| **Decisión provisional**  
La gestión avanzada de lotes queda pendiente. Si distintas unidades del mismo grupo terminan con estados, ubicaciones o responsables diferentes, el registro deberá dividirse o incorporarse una entidad lote. |
| --- |

# 8. Vehículos como bienes y ubicaciones

Un vehículo tiene una ficha patrimonial y, al mismo tiempo, puede contener equipamiento. ubicaciones.bien_contenedor_id permite vincular una ubicación de tipo VEHICULO con el bien que la representa.

- Cada vehículo tendrá como máximo una ubicación asociada.

- Una ubicación VEHICULO debe tener bien_contenedor_id.

- Una ubicación FISICA no debe tener bien_contenedor_id.

- Un vehículo no puede contenerse a sí mismo.

- Deben evitarse ciclos de contención.

# 9. Responsables

Un bien puede tener varios responsables y un usuario puede ser responsable de varios bienes. La tabla bienes_responsables guarda además el tipo de responsabilidad, período, estado y usuario asignador.

## 9.1 Regla de unicidad

Se usará un índice único parcial para impedir asignaciones activas duplicadas, pero permitir múltiples períodos históricos.

| CREATE UNIQUE INDEX uq_bien_responsable_activo  
ON bienes_responsables (bien_id, usuario_id, tipo_responsabilidad)  
WHERE activo = TRUE; |
| --- |

# 10. Ciclo de vida: alta, baja y eliminación

## 10.1 Alta

Crear un bien, asignar responsables, registrar el movimiento de alta y crear la auditoría deben ejecutarse en una misma transacción cuando formen parte de una única acción.

## 10.2 Baja

La baja es administrativa. Conserva ubicación, responsables, archivos y movimientos. Debe exigir fecha, motivo y usuario.

## 10.3 Eliminación

La eliminación estándar será lógica mediante estado_registro = ELIMINADO. La eliminación física se reserva para pruebas, duplicados o situaciones excepcionales autorizadas.

- La eliminación masiva exige selección explícita, confirmación y motivo.

- Debe registrar usuario, fecha y operacion_id.

- La auditoría no se elimina.

- La restauración debe quedar auditada.

# 11. Movimientos y auditoría

## 11.1 Movimientos operativos

- ALTA.

- BAJA_TOTAL.

- BAJA_PARCIAL.

- TRASLADO.

- ASIGNACION.

- DESASIGNACION.

- CAMBIO_ESTADO.

- AJUSTE_CANTIDAD.

- RESTAURACION.

- CORRECCION.

Los tipos serán controlados mediante CHECK o catálogo. Algunas operaciones requieren reglas específicas: un traslado exige destino; una baja parcial exige cantidad positiva; un cambio de estado exige estado nuevo.

## 11.2 Auditoría transversal

auditoria_cambios guardará entidad, acción, datos anteriores, datos nuevos, motivo, usuario, fecha y operacion_id. operacion_id agrupa cambios de una misma acción masiva.

| **Diferencia entre movimiento y auditoría**  
El movimiento describe un hecho operativo del bien. La auditoría registra quién modificó datos del sistema, incluidas correcciones, eliminaciones y restauraciones. |
| --- |

# 12. Frontera entre dominio y persistencia

El resto del backend no debe recibir filas sin procesar ni estructuras propias de un ORM. Los repositorios transformarán los datos en contratos estables del dominio.

| interface BienDetalle {  
  id: number;  
  codigoInterno: string;  
  nombre: string;  
  categoria: { id: number; nombre: string };  
  ubicacion: { id: number; nombre: string } \| null;  
  responsables: ResponsableResumen[];  
  datosEspecificos: Record<string, unknown>;  
} |
| --- |

El repositorio puede usar ORM, query builder o SQL directo según la consulta. Los servicios consumen el mismo contrato aunque cambie la implementación.

# 13. Estrategia de acceso a datos

| **Herramienta** | **Uso recomendado** | **Ventaja** | **Riesgo** |
| --- | --- | --- | --- |
| ORM | CRUD y relaciones comunes. | Reduce código repetitivo. | Puede ocultar SQL o producir N+1. |
| Query builder | Filtros dinámicos y consultas configurables. | Mantiene control y composición. | Requiere conocer SQL. |
| SQL directo | Reportes, JSONB, auditoría y consultas complejas. | Control total y rendimiento previsible. | Más mapeo manual. |

La decisión es combinarlas, pero centralizadas dentro de repositorios. No se permitirá que cada controlador elija libremente su propia forma de acceder a la base.

# 14. Transacciones y concurrencia

Las operaciones administrativas importantes deben ser atómicas: o se completan todos sus pasos o no se guarda ninguno.

## 14.1 Operaciones transaccionales

- Alta de bien + responsables + movimiento + auditoría.

- Baja + cambio de estado + movimiento + auditoría.

- Traslado + actualización de ubicación + movimiento.

- Eliminación masiva + auditorías agrupadas.

- Corrección de cantidad + motivo + auditoría.

## 14.2 Actualizaciones simultáneas

Dos usuarios pueden editar el mismo bien al mismo tiempo. Se recomienda incorporar control optimista mediante updated_at o un campo version, y rechazar una escritura si el registro cambió desde que fue leído.

# 15. Índices y consultas

Los índices se crearán en función de las consultas reales y no solo porque una columna exista.

- Índice único para codigo_interno.

- Índice único parcial para codigo_patrimonial no nulo.

- Índices para claves foráneas: categoria_id, ubicacion_id, bien_id y usuario_id.

- Índice parcial para responsables activos.

- Índices compuestos solo para filtros frecuentes confirmados.

- Índices GIN sobre JSONB únicamente si las búsquedas reales lo justifican.

| **Regla de rendimiento**  
Cada índice acelera lecturas, pero aumenta espacio y costo de escritura. Primero se medirán consultas y luego se agregarán índices específicos. |
| --- |

# 16. Confiabilidad y operación

- Copia automática diaria de PostgreSQL.

- Conservación de varias versiones de respaldo.

- Pruebas periódicas de restauración.

- Logs de errores y de operaciones sensibles.

- Migraciones versionadas.

- Ambiente de prueba separado de producción.

- Exportación completa para evitar dependencia del proveedor.

- Credenciales y secretos fuera del repositorio.

La copia de seguridad no se considera válida hasta que se haya probado una restauración.

# 17. Seguridad, privacidad y responsabilidad

- Aplicar permisos por rol y principio de mínimo privilegio.

- Limitar la creación de categorías y campos dinámicos a usuarios autorizados.

- Proteger el acceso a auditorías y exportaciones.

- Minimizar datos personales de responsables.

- No exponer hash de contraseña, metadatos internos ni datos sensibles en la API.

- Registrar descargas o exportaciones sensibles si la unidad lo requiere.

- Definir conservación y eliminación de archivos personales o administrativos.

El sistema administra patrimonio, pero también registra personas y acciones. La trazabilidad debe equilibrarse con el acceso limitado y la minimización de datos.

# 18. Riesgos y decisiones pendientes

| **Tema** | **Decisión pendiente o riesgo** |
| --- | --- |
| **Bienes agrupados** | Validar si cantidad_actual es suficiente o si se requieren lotes. |
| **Campos dinámicos** | Definir reglas de versionado y migración cuando cambien requisitos. |
| **Vehículos como ubicaciones** | Evitar ciclos y autoubicación. |
| **Auditoría genérica** | Asegurar que se escriba en la misma transacción que el cambio. |
| **Archivos** | Elegir proveedor, límites, tipos permitidos y política de respaldo. |
| **Catálogos** | Decidir qué estados serán fijos y cuáles configurables. |
| **Conectividad** | Evaluar necesidad de modo offline después del piloto. |

# 19. Hoja de ruta recomendada

**1.** Validar el modelo físico con la unidad mediante ejemplos reales.

**2.** Cerrar los valores de estados, situaciones y tipos de movimiento.

**3.** Crear migraciones PostgreSQL.

**4.** Escribir pruebas de restricciones, claves foráneas e índices únicos.

**5.** Implementar repositorios y contratos del dominio.

**6.** Desarrollar alta de bienes como primer corte vertical.

**7.** Agregar responsables, movimientos y auditoría transaccional.

**8.** Implementar campos dinámicos y validación JSONB.

**9.** Probar baja, corrección, eliminación masiva y restauración.

**10.** Realizar carga piloto y revisar el tratamiento de bienes agrupados.

# 20. Matriz resumida de ADR

| **Identificador** | **Decisión** | **Estado** |
| --- | --- | --- |
| ADR-001 | PostgreSQL como sistema de registro | Aprobada |
| ADR-002 | Modelo híbrido relacional + JSONB | Aprobada |
| ADR-003 | Monolito modular | Aprobada |
| ADR-004 | Campos dinámicos por metadatos | Aprobada |
| ADR-005 | Responsables mediante entidad asociativa | Aprobada |
| ADR-006 | Vehículos como bienes y ubicaciones | Aprobada |
| ADR-007 | Eliminación lógica por defecto | Aprobada |
| ADR-008 | Auditoría con operacion_id | Aprobada |
| ADR-009 | ORM + query builder + SQL en repositorios | Aprobada |
| ADR-010 | Bienes agrupados mediante cantidad_actual | Provisional |
| ADR-011 | REST para el MVP | Aprobada |
| ADR-012 | Event Sourcing completo | Descartada para el MVP |

# 21. Relación con el libro

El informe usa como marco conceptual las partes más relevantes de Designing Data-Intensive Applications, 2.ª edición. No pretende aplicar todos los mecanismos del libro, sino seleccionar los que corresponden al tamaño y riesgo del proyecto.

- **Capítulo 2**: Confiabilidad, mantenibilidad, simplicidad y evolución.

- **Capítulo 3**: Modelo relacional frente a documental, normalización, relaciones y frontera objeto-relacional.

- **Capítulo 4**: Índices, almacenamiento y recuperación.

- **Capítulo 5**: Esquemas, JSON y evolución de datos.

- **Capítulo 8**: Transacciones, aislamiento y actualizaciones perdidas.

- **Capítulo 14**: Privacidad, responsabilidad y uso de datos.

Replicación, sharding, consenso, streaming avanzado y operación multi-región se consideran formación futura, no requisitos del MVP.

# 22. Conclusión

La arquitectura propuesta es suficiente para comenzar el desarrollo sin cerrar prematuramente las áreas donde todavía falta información real. El sistema se apoya en PostgreSQL, relaciones normalizadas, campos JSONB controlados, transacciones, auditoría y eliminación lógica.

La principal condición para avanzar es probar el modelo con una muestra representativa del patrimonio. Esa carga piloto permitirá confirmar la estructura de bienes agrupados, las categorías iniciales y los campos dinámicos antes de consolidar el resto del backend.

# Anexo A. Casos mínimos de validación

**1.** Camión con código patrimonial, responsables y ubicación física.

**2.** Camión registrado también como ubicación de tubos y herramientas.

**3.** Casco individual sin código patrimonial.

**4.** Computadora con número de serie en datos_especificos.

**5.** Treinta sillas agrupadas con baja parcial.

**6.** Cambio de ubicación de un motor portátil.

**7.** Corrección de cantidad con datos anteriores y nuevos.

**8.** Baja que conserve ubicación y responsables.

**9.** Eliminación masiva y posterior restauración.

**10.** Cambio de definición de campo sin romper registros antiguos.

# Anexo B. Glosario breve

| **Término** | **Significado** |
| --- | --- |
| **ADR** | Registro de una decisión arquitectónica y sus consecuencias. |
| **Dominio** | Conceptos y reglas del negocio que la aplicación representa. |
| **Persistencia** | Forma concreta en que los datos se almacenan y consultan. |
| **JSONB** | Tipo de PostgreSQL para almacenar JSON de forma consultable e indexable. |
| **Normalización** | Guardar datos compartidos una sola vez y relacionarlos mediante identificadores. |
| **Entidad asociativa** | Tabla que representa una relación muchos-a-muchos y contiene atributos propios. |
| **Eliminación lógica** | Ocultar un registro sin borrarlo físicamente. |
| **Transacción** | Grupo de cambios que se confirma completo o se revierte. |
| **Índice parcial** | Índice aplicado solo a filas que cumplen una condición. |
| **DTO** | Contrato de datos usado para entrada o salida de la API. |

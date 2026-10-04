# CAMBIOS SUGERIDOS AL MODELO FÍSICO

> Documento histórico convertido desde el archivo Word. Su contenido refleja el análisis original y no necesariamente el estado implementado del proyecto.

**Sistema de Inventario Patrimonial para Bomberos**

*Explicación práctica de qué conviene modificar y por qué*

| **Documento** | Revisión técnica del modelo físico v1.0 |
| --- | --- |
| **Objetivo** | Evitar inconsistencias antes de crear migraciones PostgreSQL |
| **Estado** | Propuesta de mejora |
| **Alcance** | Base de datos y reglas de integridad |

# 1. Resumen

El modelo físico está bien encaminado y ya contiene las tablas principales, claves, relaciones, auditoría, eliminación lógica, campos JSONB e índices. Antes de comenzar a programar las migraciones, conviene ajustar algunas reglas para que la base de datos no permita estados contradictorios o historiales incompletos.

Las propuestas de este documento no cambian la idea central del sistema. Buscan reforzarla: mantener trazabilidad, permitir correcciones, evitar duplicados y garantizar que la base siga siendo coherente incluso si una validación del frontend o del backend falla.

# 2. Matriz general de cambios

| **Cambio sugerido** | **Problema actual** | **Por qué conviene** | **Resultado esperado** |
| --- | --- | --- | --- |
| Índice único parcial para responsables activos | UNIQUE (bien_id, usuario_id, activo) impediría guardar varios períodos históricos inactivos. | Una persona puede dejar de ser responsable y volver a serlo en otro período. | Se evita la duplicación activa sin destruir el historial. |
| Usar una sola fuente de verdad para la eliminación | estado_registro y eliminado pueden contradecirse. | Dos campos que expresan lo mismo pueden quedar desincronizados. | El estado de eliminación queda claro y consistente. |
| Restricciones para bajas y eliminaciones | Podría existir un bien en BAJA sin fecha o un ELIMINADO sin usuario responsable. | La base debe exigir los datos mínimos administrativos. | No habrá bajas o eliminaciones incompletas. |
| Regla condicional para cantidad | Un bien INDIVIDUAL podría terminar con cantidad distinta de 1. | La base debe respetar la definición del tipo de registro. | Los bienes individuales y agrupados conservan lógica coherente. |
| Fortalecer vehículo como ubicación | El mismo vehículo podría tener varias ubicaciones asociadas o una ubicación VEHÍCULO sin bien. | La relación debe ser inequívoca. | Cada vehículo tendrá, como máximo, una ubicación asociada válida. |
| Definir tipos de movimiento permitidos | tipo_movimiento es texto libre. | El texto libre genera variantes e inconsistencias. | Los movimientos se registran con valores controlados. |
| Agregar identificador de operación a auditoría | Una acción masiva genera muchos registros sin una forma simple de agruparlos. | Es útil rastrear todos los cambios de una misma operación. | Una eliminación masiva o importación puede auditarse como una sola operación. |
| Controlar la evolución de campos configurables | Cambiar una clave o tipo puede invalidar datos históricos en JSONB. | Los datos antiguos deben seguir siendo interpretables. | Los campos usados se desactivan y reemplazan, en vez de modificarse destructivamente. |

# 3. Responsables activos e historial

**Problema.** En la tabla bienes_responsables aparece una restricción del tipo UNIQUE (bien_id, usuario_id, activo). Esa regla permitiría una sola fila activa y una sola fila inactiva por combinación. Si una persona fue responsable en 2026, dejó de serlo y volvió a asumir en 2027, al cerrar el segundo período existirían dos filas con activo = false y la base podría rechazar la segunda.

**Cambio recomendado.** Reemplazar esa restricción por un índice único parcial que solo controle las asignaciones activas. La combinación debería incluir bien_id, usuario_id y tipo_responsabilidad, pero únicamente cuando activo sea true.

**Por qué.** La base evita duplicaciones simultáneas, pero permite conservar todos los períodos históricos.

| CREATE UNIQUE INDEX uq_bien_responsable_activo  
ON bienes_responsables (bien_id, usuario_id, tipo_responsabilidad)  
WHERE activo = TRUE; |
| --- |

# 4. Estado de eliminación: evitar información duplicada

**Problema.** La tabla bienes usa estado_registro con valores ACTIVO, BAJA o ELIMINADO y, al mismo tiempo, un booleano eliminado. Ambos campos expresan parte de la misma situación. Podría quedar estado_registro = 'ACTIVO' y eliminado = true.

**Cambio recomendado.** Usar estado_registro como única fuente de verdad y conservar eliminado_en y eliminado_por_usuario_id como metadatos. Si se decide mantener el booleano, debe existir una restricción que obligue a que ambos campos coincidan.

**Por qué.** Una sola fuente de verdad reduce errores y simplifica filtros, reportes y lógica de negocio.

| CHECK (  
  (estado_registro = 'ELIMINADO' AND eliminado = TRUE)  
  OR  
  (estado_registro <> 'ELIMINADO' AND eliminado = FALSE)  
); |
| --- |

# 5. Bajas y eliminaciones completas

**Problema.** Sin restricciones adicionales, la base podría aceptar una baja sin fecha o una eliminación lógica sin identificar quién la realizó.

**Cambio recomendado.** Agregar restricciones condicionales para exigir fecha y motivo en las bajas, y fecha y usuario en las eliminaciones.

**Por qué.** Estas reglas son parte de la trazabilidad administrativa. No deberían depender solo del formulario.

| CHECK (  
  estado_registro <> 'BAJA'  
  OR (fecha_baja IS NOT NULL AND motivo_baja IS NOT NULL)  
);  
  
CHECK (  
  estado_registro <> 'ELIMINADO'  
  OR (eliminado_en IS NOT NULL AND eliminado_por_usuario_id IS NOT NULL)  
); |
| --- |

# 6. Cantidad según el tipo de bien

**Problema.** El modelo distingue bienes INDIVIDUALES y AGRUPADOS, pero la base podría permitir un bien individual con cantidad 3.

**Cambio recomendado.** Agregar una restricción condicional que obligue a los bienes individuales a tener cantidad 1 y a los agrupados una cantidad positiva.

**Por qué.** La regla expresa directamente el significado del dominio y evita errores durante importaciones o scripts.

| CHECK (  
  (tipo_registro = 'INDIVIDUAL' AND cantidad_actual = 1)  
  OR  
  (tipo_registro = 'AGRUPADO' AND cantidad_actual >= 1)  
); |
| --- |

# 7. Vehículos que también funcionan como ubicaciones

**Problema.** Una ubicación de tipo VEHÍCULO podría no tener bien_contenedor_id, o un mismo vehículo podría quedar asociado a varias ubicaciones.

**Cambio recomendado.** Crear una restricción UNIQUE sobre bien_contenedor_id cuando exista y exigir coherencia entre tipo_ubicacion y bien_contenedor_id.

**Por qué.** Cada ubicación vehicular debe representar un vehículo concreto y no debe existir ambigüedad.

| CREATE UNIQUE INDEX uq_ubicacion_bien_contenedor  
ON ubicaciones (bien_contenedor_id)  
WHERE bien_contenedor_id IS NOT NULL;  
  
CHECK (  
  (tipo_ubicacion = 'VEHICULO' AND bien_contenedor_id IS NOT NULL)  
  OR  
  (tipo_ubicacion = 'FISICA' AND bien_contenedor_id IS NULL)  
); |
| --- |

# 8. Tipos de movimiento controlados

**Problema.** tipo_movimiento como VARCHAR libre permite variantes como BAJA, baja, BAJA_TOTAL o BAJA TOTAL.

**Cambio recomendado.** Definir una lista inicial de valores permitidos mediante CHECK o una tabla catálogo.

**Por qué.** Los reportes, filtros y reglas de negocio dependen de que cada operación tenga un nombre estable.

| Valores iniciales sugeridos:  
ALTA  
BAJA_TOTAL  
BAJA_PARCIAL  
TRASLADO  
ASIGNACION  
DESASIGNACION  
CAMBIO_ESTADO  
AJUSTE_CANTIDAD  
RESTAURACION  
CORRECCION |
| --- |

# 9. Auditoría de operaciones masivas

**Problema.** Una eliminación de veinte bienes genera veinte registros separados sin una forma directa de demostrar que pertenecen a la misma acción.

**Cambio recomendado.** Agregar operacion_id o request_id a auditoria_cambios y usar el mismo valor para todos los cambios de una acción.

**Por qué.** Facilita investigar, revertir o explicar operaciones masivas.

| Ejemplo:  
operacion_id = 8c43-...  
  - bien 1 eliminado  
  - bien 2 eliminado  
  - bien 3 eliminado |
| --- |

# 10. Evolución de definiciones de campo

**Problema.** Si un campo ya utilizado cambia de TEXTO a NUMERO, los valores antiguos dentro de datos_especificos pueden quedar inválidos.

**Cambio recomendado.** No permitir cambiar directamente la clave o el tipo de un campo que ya tenga datos. Debe desactivarse y crearse una nueva definición.

**Por qué.** La información histórica debe seguir siendo legible y validable.

| Regla propuesta:  
- campo sin datos: puede editarse;  
- campo con datos: etiqueta y orden pueden ajustarse;  
- clave o tipo: desactivar y crear un campo nuevo. |
| --- |

# 11. Cambios que no son urgentes para el MVP

- Convertir todos los estados y tipos en tablas catálogo. Los CHECK son suficientes mientras los valores sean fijos.

- Implementar triggers complejos para cada regla. Primero puede combinarse restricción de base con validación del servicio.

- Diseñar lotes avanzados para bienes agrupados. Conviene probar antes con datos reales.

- Aplicar Event Sourcing completo. El modelo actual de estado presente + movimientos + auditoría es más simple.

# 12. Orden recomendado de implementación

**1.** Actualizar el diagrama físico a una versión 1.1.

**2.** Definir los valores permitidos para tipo_movimiento.

**3.** Elegir si se elimina el booleano eliminado o se mantiene con una restricción.

**4.** Generar las migraciones PostgreSQL.

**5.** Crear pruebas de integridad para cada CHECK, UNIQUE y FK.

**6.** Probar el modelo con casos reales: vehículo, casco, bien sin código, baja, corrección y eliminación masiva.

# 13. Conclusión

El modelo físico puede avanzar a codificación después de estos ajustes. La mayoría de los cambios no agrega complejidad innecesaria: transforma reglas ya decididas en restricciones concretas de PostgreSQL. De ese modo, la base protege el patrimonio incluso cuando una pantalla, una importación o una parte del backend cometa un error.

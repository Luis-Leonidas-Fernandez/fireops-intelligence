# Desajuste objeto-relacional

> Documento histórico convertido desde el archivo Word. Su contenido refleja el análisis original y no necesariamente el estado implementado del proyecto.

**Aplicación al sistema de inventario patrimonial de Bomberos**

*Documento* *d**etallado*

| **Idea central:** el código de la aplicación suele trabajar con objetos anidados, mientras que PostgreSQL organiza la información en tablas, filas, columnas y relaciones. La traducción entre ambos modelos genera el desajuste objeto-relacional. |
| --- |

## 1. Qué significa el desajuste objeto-relacional

El libro explica que muchas aplicaciones se desarrollan con lenguajes orientados a objetos. Cuando esos objetos deben persistirse en una base relacional, aparece una capa de traducción entre la estructura usada en el código y el modelo de tablas, filas y columnas. A esta desconexión se la denomina impedance mismatch o desajuste de impedancia.

La expresión proviene de la electrónica: dos componentes transfieren mejor la señal cuando sus impedancias coinciden. Por analogía, cuando el modelo de objetos y el modelo relacional no encajan naturalmente, aparecen conversiones, decisiones adicionales y posibles ineficiencias.

## 2. Ejemplo aplicado al inventario

En el backend, una ficha completa podría representarse como un objeto anidado:

const bien = {  
  id: 25,  
  codigoInterno: "BOM-000025",  
  nombre: "Tubo de aire 014",  
  categoria: {  
    id: 3,  
    nombre: "Equipos respiratorios"  
  },  
  ubicacion: {  
    id: 8,  
    nombre: "Autobomba 2"  
  },  
  responsables: [  
    { id: 4, nombre: "Responsable operativo" },  
    { id: 7, nombre: "Responsable de mantenimiento" }  
  ],  
  datosEspecificos: {  
    capacidadLitros: 6.8,  
    presionMaximaBar: 300  
  }  
};

|   |
| --- |

En PostgreSQL, la misma información estaría distribuida entre varias tablas:

- **bienes**

- **categorias**

- **ubicaciones**

- **usuarios**

- **bienes_responsables**

- **definiciones_campo**

Por lo tanto, el backend debe reconstruir el objeto final mediante JOIN, consultas adicionales o una herramienta que mapee las filas y relaciones a objetos de JavaScript o TypeScript.

## 3. Qué hace un ORM y qué no resuelve

Frameworks ORM como ActiveRecord e Hibernate. Su función principal es reducir el código repetitivo necesario para convertir objetos en filas y filas en objetos.

| **Lo que un ORM facilita** | **Lo que no puede ocultar completamente** |
| --- | --- |
| Altas, lecturas, actualizaciones y bajas comunes. | Las relaciones siguen existiendo y deben diseñarse correctamente. |
| Mapeo de tipos y nombres de campos. | El esquema relacional continúa siendo importante para analítica y consultas directas. |
| Carga de relaciones desde el código. | El ORM puede generar consultas ineficientes si se usa sin comprender SQL. |
| Migraciones y tipado, según la herramienta. | Funciones específicas de PostgreSQL, como JSONB o consultas complejas, pueden requerir SQL manual. |

El punto no es que los ORM deban evitarse, sino entender que no eliminan la necesidad de comprender el modelo relacional. El programador sigue necesitando pensar en ambas representaciones.

## 4. Problema N+1

Uno de los riesgos que el libro destaca es el problema N+1. Ocurre cuando una consulta obtiene N registros y luego el ORM ejecuta una consulta adicional por cada registro para recuperar datos relacionados.

**Ejemplo:** se cargan 100 bienes y luego se consulta por separado la categoría de cada uno.

| Consulta inicial de bienes | 1 |
| --- | --- |
| Consultas adicionales de categoría | 100 |
| **Total** | **101 consultas** |

Una consulta con JOIN puede resolver el mismo caso en una sola operación:

SELECT b.id, b.nombre, c.nombre AS categoria  
FROM bienes AS b  
JOIN categorias AS c ON c.id = b.categoria_id  
WHERE b.eliminado = false;

## 5. Decisión para el proyecto

| **Decisión:** usar una estrategia combinada: ORM o query builder para operaciones comunes y SQL directo para consultas complejas, reportes, operaciones masivas y usos avanzados de PostgreSQL. |
| --- |

La decisión se toma por estas razones:

- El CRUD cotidiano puede implementarse con menos código repetitivo.

- Las consultas complejas conservan control explícito sobre JOIN, filtros e índices.

- Los campos JSONB pueden aprovechar funciones específicas de PostgreSQL cuando sea necesario.

- Se reduce el riesgo de depender completamente de abstracciones que oculten consultas ineficientes.

- El equipo mantiene la posibilidad de inspeccionar y optimizar el SQL real.

## 6. Distribución propuesta de responsabilidades

| **Necesidad** | **Enfoque preferente** | **Motivo** |
| --- | --- | --- |
| Crear o actualizar un bien | ORM o query builder | Operación transaccional común y repetitiva. |
| Asignar responsables | ORM o query builder | Relación muchos-a-muchos conocida. |
| Registrar movimiento y auditoría | ORM/query builder dentro de una transacción | Permite agrupar escrituras relacionadas. |
| Filtros dinámicos del listado | Query builder | Resulta cómodo agregar condiciones opcionales. |
| Reportes y agregaciones | SQL directo | Mayor claridad y control del plan de consulta. |
| Consultas avanzadas sobre JSONB | SQL directo o extensión específica | Aprovecha operadores propios de PostgreSQL. |
| Eliminación lógica masiva | SQL directo o query builder transaccional | Evita cargar cada registro y reduce consultas. |

## 7. Reglas de implementación derivadas

- No permitir que el ORM diseñe automáticamente el dominio sin revisar el esquema resultante.

- Revisar el SQL generado en consultas críticas.

- Evitar cargas perezosas que produzcan N+1.

- Usar eager loading o JOIN cuando una pantalla necesita relaciones conocidas.

- Mantener repositorios o servicios que oculten la herramienta concreta al resto de la aplicación.

- Escribir pruebas para contar consultas en rutas sensibles.

- Encapsular transacciones que creen o modifiquen bien, movimiento y auditoría juntos.

- Documentar cuándo una consulta usa SQL directo y por qué.

## 8. Ejemplo de frontera entre dominio y persistencia

El resto de la aplicación no debería recibir filas sin procesar ni depender directamente del ORM. Una capa de repositorio puede traducir la persistencia a una estructura estable del dominio.  
  
Un contrato estructurado define como se construira la informacion en el backend para devolverlo al  frontend.

// Dominio esperado por la aplicación  
interface BienDetalle {  
  id: number;  
  codigoInterno: string;  
  nombre: string;  
  categoria: { id: number; nombre: string };  
  ubicacion: { id: number; nombre: string } | null;  
  responsables: ResponsableResumen[];  
  datosEspecificos: Record<string, unknown>;  
}

Así, si en el futuro se cambia de ORM, query builder o estrategia de consulta, la mayor parte del backend no debería necesitar cambios.

## 9. Conclusión

El desajuste objeto-relacional no es un error del sistema, sino una consecuencia natural de usar dos modelos distintos: objetos en el código y relaciones en la base de datos. La solución no consiste en ocultar por completo PostgreSQL, sino en usar abstracciones donde simplifican el trabajo y SQL explícito donde se necesita control.

Para el inventario de Bomberos, la estrategia combinada equilibra productividad, claridad, capacidad de optimización y aprovechamiento del modelo híbrido relacional + JSONB ya definido.

## 10. Fuente

Kleppmann, Martin; Riccomini, Chris. Designing Data-Intensive Applications: The Big Ideas Behind Reliable, Scalable, and Maintainable Systems. 2.ª edición. O’Reilly Media, 2026. Capítulo 3, sección “The Object-Relational Mismatch”, especialmente la discusión sobre ORM y el problema N+1.  
  
*Nota metodológica: las definiciones y críticas generales a los ORM se basan en el libro. Los ejemplos de tablas, consultas y decisiones específicas para Bomberos son una* *aplicación* *al* *proyecto* *en* *desarrollo**.*

# Task 02 — Crear categorías y bienes

En esta tarea vamos a crear las primeras tablas reales del módulo de inventario:

```text
categorias
bienes
```

No vamos a crear todo el modelo patrimonial todavía. Vamos a empezar con una unidad pequeña pero real.

## Por qué empezamos con estas dos tablas

Un bien necesita una categoría.

Ejemplos:

```text
Categoría: Mangueras
Bien: Manguera forestal 30m

Categoría: Cascos
Bien: Casco estructural rojo
```

La relación es:

```text
categorias 1 ─── N bienes
```

Esto significa:

> Una categoría puede tener muchos bienes, pero cada bien pertenece a una categoría.

## Objetivo

Crear o modificar:

```text
app/modules/inventory/shared/models.py
migrations/env.py
migrations/versions/<revision>_create_categories_and_assets_tables.py
```

## Flujo

```text
modelo Category + modelo Asset
  ↓
Base.metadata
  ↓
Alembic detecta los modelos
  ↓
migración crea tablas categorias y bienes
  ↓
PostgreSQL tiene tablas relacionadas
```

## Antes de empezar

Antes de tocar código, creá o activá tu rama siguiendo:

```text
GIT_WORKFLOW.md
```

No trabajes directo sobre `main`.

---

# Paso 1 — Crear los modelos

Abrir:

```text
app/modules/inventory/shared/models.py
```

Copiar:

```python
from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Category(Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class Asset(Base):
    __tablename__ = "bienes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    codigo_interno: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("categorias.id"),
        nullable=False,
    )
```

## Qué hace `Category`

`Category` representa la tabla:

```text
categorias
```

Tiene:

| Campo | Significado |
|---|---|
| `id` | identificador único |
| `nombre` | nombre de la categoría |

Ejemplos de categorías:

```text
Mangueras
Cascos
Radios
Vehículos
```

## Qué hace `Asset`

`Asset` representa la tabla:

```text
bienes
```

Tiene:

| Campo | Significado |
|---|---|
| `id` | identificador único |
| `codigo_interno` | código interno del bien |
| `nombre` | nombre del bien |
| `categoria_id` | categoría a la que pertenece |

## Qué significa `ForeignKey`

Esta línea:

```python
ForeignKey("categorias.id")
```

significa:

> `categoria_id` debe apuntar a una categoría existente.

Eso evita que un bien quede asociado a una categoría inexistente.

---

# Paso 2 — Conectar metadata con Alembic

Abrir:

```text
migrations/env.py
```

Buscar:

```python
target_metadata = None
```

Reemplazar por:

```python
from app.infrastructure.database.base import Base
from app.modules.inventory.shared import models  # noqa: F401

target_metadata = Base.metadata
```

## Qué hace

Alembic necesita ver `Base.metadata` para saber qué tablas existen en Python.

El import de `models` hace que Python cargue `Category` y `Asset`.

---

# Paso 3 — Crear la migración

Ejecutar:

```powershell
alembic revision --autogenerate -m "create categories and assets tables"
```

Esto debe crear un archivo en:

```text
migrations/versions/
```

Abrilo y verificá que aparezcan dos tablas:

```python
op.create_table("categorias", ...)
op.create_table("bienes", ...)
```

También debería aparecer una clave foránea desde `bienes.categoria_id` hacia `categorias.id`.

---

# Paso 4 — Aplicar la migración

Ejecutar:

```powershell
alembic upgrade head
```

Resultado esperado: no debe mostrar error.

---

# Paso 5 — Verificar en PostgreSQL

Entrar:

```powershell
psql -U postgres -d fireassets
```

Listar tablas:

```sql
\dt
```

Deberías ver:

```text
categorias
bienes
```

Ver estructura de `bienes`:

```sql
\d bienes
```

Buscá que exista:

```text
categoria_id
```

Y que tenga una relación con:

```text
categorias(id)
```

Salir:

```sql
\q
```

---

# Paso 6 — Insertar datos de prueba manualmente

Para entender la relación, podés probar esto dentro de PostgreSQL:

```sql
INSERT INTO categorias (nombre)
VALUES ('Mangueras')
RETURNING id, nombre;
```

Supongamos que devuelve:

```text
id | nombre
1  | Mangueras
```

Ahora insertá un bien usando esa categoría:

```sql
INSERT INTO bienes (codigo_interno, nombre, categoria_id)
VALUES ('BOM-001', 'Manguera forestal 30m', 1)
RETURNING id, codigo_interno, nombre, categoria_id;
```

Si funciona, la relación está bien.

## Prueba de error esperada

Ahora intentá insertar un bien con una categoría que no existe:

```sql
INSERT INTO bienes (codigo_interno, nombre, categoria_id)
VALUES ('BOM-999', 'Bien con categoría inexistente', 99999);
```

Esto debería fallar.

¿Por qué?

Porque `99999` no existe en `categorias.id`.

Ese error demuestra que la clave foránea está protegiendo los datos.

---

# Paso 7 — Ver las tablas desde Visual Studio Code

Después de verificar las tablas con terminal, también podés verlas de forma visual en Visual Studio Code.

Esto es útil para entender mejor qué se creó en PostgreSQL.

## Extensión recomendada

Instalar esta extensión en Visual Studio Code:

```text
PostgreSQL
```

ID de la extensión:

```text
ms-ossdata.vscode-pgsql
```

Marketplace:

```text
https://marketplace.visualstudio.com/items?itemName=ms-ossdata.vscode-pgsql
```

## Datos de conexión en Windows

Usar estos datos:

```text
Host: localhost
Port: 5432
Database: fireassets
Username: postgres
Password: la contraseña que configuraste al instalar PostgreSQL
```

Esto equivale a esta URL:

```env
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets
```

## Qué deberías ver

Después de conectarte, buscá algo parecido a:

```text
fireassets
  └── schemas
      └── public
          └── tables
              ├── categorias
              └── bienes
```

## Para qué usamos esta extensión

La extensión sirve para mirar visualmente:

- qué bases existen;
- qué tablas existen;
- qué columnas tiene cada tabla;
- qué datos se insertaron.

Pero ojo:

> La extensión ayuda a visualizar. No reemplaza entender los comandos SQL.

Primero verificamos por terminal. Después usamos la extensión como apoyo visual.

---

# Uso de mensajes para aprender

En esta tarea trabajamos dentro de PostgreSQL. En SQL no usamos `print()` como en Python, pero podemos usar consultas para ver qué está pasando.

Después de insertar una categoría, ejecutá:

```sql
SELECT 'Categoría creada o encontrada' AS mensaje;
SELECT id, nombre FROM categorias WHERE nombre = 'Mangueras';
```

Después de insertar un bien, ejecutá:

```sql
SELECT 'Bien creado' AS mensaje;
SELECT id, codigo_interno, nombre, categoria_id FROM bienes WHERE codigo_interno = 'BOM-001';
```

Estos mensajes son sólo para aprender y mirar el flujo.

> Antes de subir la Pull Request, no hace falta guardar estos comandos en archivos del proyecto. Sólo usalos en la terminal durante la práctica.

---

# Qué entregar

Entregá:

- archivo `models.py` actualizado;
- archivo de migración creado;
- resultado de `alembic upgrade head`;
- captura o texto mostrando `\dt` con `categorias` y `bienes`;
- explicación breve de qué significa esta relación:

```text
categorias 1 ─── N bienes
```

---

# Qué aprendiste

Aprendiste a crear dos tablas relacionadas.

Eso es más importante que crear muchas tablas sin entenderlas.

Primero construimos una relación real. Después agregaremos ubicaciones, movimientos, responsables, archivos y auditoría.

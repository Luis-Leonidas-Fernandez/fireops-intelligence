# Task 02 — Crear categorías y bienes

En esta tarea vamos a crear las primeras tablas reales del módulo de inventario:

```text
categorias
bienes
```

No vamos a crear todo el sistema patrimonial todavía. Vamos a empezar con una relación pequeña, real y fácil de entender.

---

# Objetivo de la clase

Al terminar esta tarea, la base de datos `fireassets` debe tener estas tablas:

```text
categorias
bienes
```

Y la relación debe ser:

```text
categorias 1 ─── N bienes
```

Eso significa:

> Una categoría puede tener muchos bienes, pero cada bien pertenece a una sola categoría.

Ejemplo:

```text
Categoría: Mangueras
  ├── Bien: Manguera forestal 30m
  └── Bien: Manguera estructural 25m
```

---

# Reparto de responsabilidades

## Responsable / instructor

El instructor deja preparado:

```text
migrations/env.py
```

Ese archivo debe estar conectado a:

- `.env`;
- `DATABASE_URL`;
- `Base.metadata`;
- modelos de inventario.

Los participantes NO deben modificar `migrations/env.py` en esta etapa.

## Participantes

Los participantes trabajan principalmente sobre:

```text
app/modules/inventory/shared/models.py
```

Después ejecutan la migración guiados por el instructor.

La idea no es aprender todo Alembic de golpe. Primero deben entender:

- qué es una tabla;
- qué es una columna;
- qué es un `id`;
- qué significa `unique`;
- qué significa `nullable`;
- qué significa `ForeignKey`;
- qué significa una relación 1 a N.

---

# Archivos involucrados

| Archivo | Quién lo toca | Para qué sirve |
|---|---|---|
| `app/modules/inventory/shared/models.py` | Participante | Define los modelos `Category` y `Asset` |
| `migrations/env.py` | Instructor | Le dice a Alembic dónde encontrar modelos y `DATABASE_URL` |
| `migrations/versions/<revision>.py` | Instructor o grupo guiado | Contiene la migración que crea las tablas |
| PostgreSQL | Todos verifican | Lugar donde finalmente aparecen las tablas |

---

# Flujo general

```text
models.py
  ↓ define Category y Asset
Base.metadata
  ↓ registra los modelos
migrations/env.py
  ↓ entrega metadata y DATABASE_URL a Alembic
migración
  ↓ crea instrucciones para PostgreSQL
alembic upgrade head
  ↓ aplica esas instrucciones
PostgreSQL
  ↓ muestra categorias y bienes
```

---

# Antes de empezar

Antes de tocar código, verificá:

- [ ] PostgreSQL está corriendo.
- [ ] La base `fireassets` existe.
- [ ] El archivo `.env` existe.
- [ ] `DATABASE_URL` apunta a `fireassets`.
- [ ] El entorno virtual `.venv` está activo.
- [ ] Las dependencias están instaladas.
- [ ] Estás en tu rama, no en `main`.

Para la rama, seguí:

```text
GIT_WORKFLOW.md
```

---

# Paso 1 — Crear los modelos

Abrí:

```text
app/modules/inventory/shared/models.py
```

Copiá este código:

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

---

# Paso 2 — Entender el código del modelo

No copies sin entender. Este bloque define cómo Python representa las tablas que después existirán en PostgreSQL.

## Imports

| Import | Para qué sirve |
|---|---|
| `BigInteger` | Define columnas numéricas grandes, como los `id`. |
| `ForeignKey` | Crea una relación entre dos tablas. |
| `String` | Define columnas de texto con un largo máximo. |
| `Mapped` | Indica que un atributo Python está conectado a una columna de base de datos. |
| `mapped_column` | Crea una columna real de la tabla. |
| `Base` | Clase base que registra los modelos para SQLAlchemy y Alembic. |

Idea clave:

```text
Los imports no son decoración.
Cada import habilita una herramienta que usamos después.
```

## `Category`

```python
class Category(Base):
```

Crea un modelo SQLAlchemy. Al heredar de `Base`, SQLAlchemy puede registrar esta clase como tabla.

```python
__tablename__ = "categorias"
```

Define el nombre real de la tabla en PostgreSQL.

```python
id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
```

Define el identificador único de cada categoría.

- `Mapped[int]`: en Python será un número entero.
- `mapped_column(...)`: será una columna de la tabla.
- `BigInteger`: será un número grande en PostgreSQL.
- `primary_key=True`: identifica cada fila.
- `autoincrement=True`: PostgreSQL genera el número automáticamente.

```python
nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
```

Define el nombre de la categoría.

- `Mapped[str]`: en Python será texto.
- `String(100)`: máximo 100 caracteres.
- `unique=True`: no se puede repetir.
- `nullable=False`: es obligatorio.

Ejemplos válidos:

```text
Mangueras
Cascos
Radios
Vehículos
```

## `Asset`

```python
class Asset(Base):
```

Crea el modelo que representa un bien.

```python
__tablename__ = "bienes"
```

Define que la tabla real se llamará `bienes`.

```python
id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
```

Identificador único del bien.

```python
codigo_interno: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
```

Código interno del bien.

- `String(30)`: máximo 30 caracteres.
- `unique=True`: no puede repetirse.
- `nullable=False`: es obligatorio.

Ejemplo:

```text
BOM-001
```

Esto es importante porque dos bienes distintos no deberían tener el mismo código interno.

```python
nombre: Mapped[str] = mapped_column(String(150), nullable=False)
```

Nombre descriptivo del bien.

Ejemplo:

```text
Manguera forestal 30m
```

```python
categoria_id: Mapped[int] = mapped_column(
    BigInteger,
    ForeignKey("categorias.id"),
    nullable=False,
)
```

Conecta el bien con una categoría.

- `categoria_id`: guarda el `id` de una categoría.
- `ForeignKey("categorias.id")`: obliga a que esa categoría exista.
- `nullable=False`: todo bien debe tener categoría.

Ejemplo correcto:

```text
categorias
id: 1
nombre: Mangueras

bienes
codigo_interno: BOM-001
nombre: Manguera forestal 30m
categoria_id: 1
```

Ejemplo incorrecto:

```text
codigo_interno: BOM-999
nombre: Bien sin categoría real
categoria_id: 99999
```

Si no existe una categoría con `id = 99999`, PostgreSQL debe rechazar ese registro.

---

# Paso 3 — Verificar que Alembic está preparado

Este paso es sólo de lectura. Los participantes no deben modificar este archivo ahora.

Abrí:

```text
migrations/env.py
```

Debe existir una parte parecida a esta:

```python
from app.config.settings import get_settings
from app.infrastructure.database.base import Base
from app.modules.inventory.shared import models  # noqa: F401

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata
```

Qué significa:

| Línea | Significado |
|---|---|
| `get_settings()` | Lee la configuración del proyecto, incluyendo `.env`. |
| `Base` | Trae el registro de modelos SQLAlchemy. |
| `models` | Carga `Category` y `Asset`. |
| `config.set_main_option(...)` | Le pasa `DATABASE_URL` a Alembic. |
| `target_metadata = Base.metadata` | Le dice a Alembic qué tablas debe mirar. |

Si eso no está, no sigas. Avisá al instructor.

---

# Paso 4 — Ejecutar migración y verificar tablas

Este es el único bloque de comandos de migración de esta tarea.

Ejecutalo desde la raíz del proyecto, con `.venv` activo.

## 4.1 Verificar ubicación

```powershell
Get-Location
Get-ChildItem
```

Tenés que ver archivos como:

```text
app
alembic.ini
migrations
requirements.txt
```

## 4.2 Verificar Alembic

```powershell
python -m alembic --version
```

## 4.3 Crear la migración

Este paso puede hacerlo el instructor o el grupo junto al instructor.

```powershell
python -m alembic revision --autogenerate -m "create categories and assets tables"
```

Esto crea un archivo nuevo dentro de:

```text
migrations/versions/
```

No sigas si la migración sale vacía. Avisá al instructor.

## 4.4 Revisar la migración creada

Abrí el archivo nuevo dentro de `migrations/versions/`.

Debe contener algo parecido a:

```python
op.create_table("categorias", ...)
op.create_table("bienes", ...)
```

También debe aparecer la relación entre:

```text
bienes.categoria_id
categorias.id
```

Idea clave:

```text
Alembic propone instrucciones.
Nosotros revisamos antes de ejecutarlas.
```

## 4.5 Aplicar la migración

```powershell
python -m alembic upgrade head
```

Esto aplica la migración en PostgreSQL.

## 4.6 Entrar a PostgreSQL

```powershell
psql -U postgres -d fireassets
```

## 4.7 Verificar tablas

```sql
\dt
```

Deberías ver:

```text
categorias
bienes
```

## 4.8 Ver estructura de `bienes`

```sql
\d bienes
```

Buscá:

```text
categoria_id
```

Y una referencia hacia:

```text
categorias(id)
```

## 4.9 Salir de PostgreSQL

```sql
\q
```

---

# Paso 5 — Insertar datos de prueba

Ahora vamos a probar la relación manualmente en PostgreSQL.

Entrá a la base:

```powershell
psql -U postgres -d fireassets
```

Crear una categoría:

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

Crear un bien usando esa categoría:

```sql
INSERT INTO bienes (codigo_interno, nombre, categoria_id)
VALUES ('BOM-001', 'Manguera forestal 30m', 1)
RETURNING id, codigo_interno, nombre, categoria_id;
```

Si funciona, la relación está bien.

---

# Paso 6 — Probar un error esperado

Intentá crear un bien con una categoría inexistente:

```sql
INSERT INTO bienes (codigo_interno, nombre, categoria_id)
VALUES ('BOM-999', 'Bien con categoría inexistente', 99999);
```

Esto debería fallar.

¿Por qué?

Porque `99999` no existe en `categorias.id`.

Ese error es bueno para aprender: demuestra que `ForeignKey` protege los datos.

Salir:

```sql
\q
```

---

# Paso 7 — Ver tablas desde Visual Studio Code

Después de verificar por terminal, podés usar la extensión de PostgreSQL en VS Code.

Extensión recomendada:

```text
PostgreSQL
```

ID:

```text
ms-ossdata.vscode-pgsql
```

Datos de conexión en Windows:

```text
Host: localhost
Port: 5432
Database: fireassets
Username: postgres
Password: la contraseña configurada al instalar PostgreSQL
```

Deberías ver algo parecido a:

```text
fireassets
  └── schemas
      └── public
          └── tables
              ├── categorias
              └── bienes
```

La extensión ayuda a mirar visualmente, pero no reemplaza entender SQL.

---

# Uso de mensajes para aprender

En SQL no usamos `print()` como en Python, pero podemos hacer consultas que nos muestren qué pasó.

Después de insertar una categoría:

```sql
SELECT 'Categoría creada o encontrada' AS mensaje;
SELECT id, nombre FROM categorias WHERE nombre = 'Mangueras';
```

Después de insertar un bien:

```sql
SELECT 'Bien creado' AS mensaje;
SELECT id, codigo_interno, nombre, categoria_id FROM bienes WHERE codigo_interno = 'BOM-001';
```

Estos comandos son sólo para practicar en la terminal. No se guardan en archivos del proyecto.

---

# Checklist final

Antes de cerrar la tarea, confirmá:

- [ ] `models.py` tiene `Category`.
- [ ] `models.py` tiene `Asset`.
- [ ] `migrations/env.py` tiene `target_metadata = Base.metadata`.
- [ ] Existe una migración nueva en `migrations/versions/`.
- [ ] `python -m alembic upgrade head` terminó sin error.
- [ ] `\dt` muestra `categorias` y `bienes`.
- [ ] `\d bienes` muestra `categoria_id`.
- [ ] Pudiste insertar una categoría.
- [ ] Pudiste insertar un bien con una categoría válida.
- [ ] La prueba con categoría inexistente falló como esperábamos.

---

# Qué entregar

Entregá:

- archivo `models.py` actualizado;
- archivo de migración creado;
- resultado de `python -m alembic upgrade head`;
- captura o texto mostrando `\dt` con `categorias` y `bienes`;
- explicación breve de qué significa:

```text
categorias 1 ─── N bienes
```

---

# Qué aprendiste

Aprendiste a crear dos tablas relacionadas desde código.

Eso es más importante que crear muchas tablas sin entenderlas.

Primero construimos una relación real. Después agregaremos ubicaciones, movimientos, responsables, archivos y auditoría.

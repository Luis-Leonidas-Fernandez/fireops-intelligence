# Visual Studio Code: PostgreSQL con SQLTools

Guía completa para **instalar, configurar, conectar y consultar** la base `fireassets` desde Visual Studio Code.


Esta guía explica cómo instalar, habilitar y usar Visual Studio Code para conectarse visualmente a PostgreSQL, ejecutar consultas y consultar las tablas del proyecto sin confundirse con otras extensiones.

> **Regla principal:** antes de ejecutar una consulta, verificá que la conexión activa diga `fireassets`.

## Ruta rápida

1. Instalá y habilitá SQLTools y su driver de PostgreSQL.
2. Creá la conexión `FireAssets` con base `fireassets`.
3. Confirmá el árbol `public > Tables`.
4. Ejecutá `SELECT current_database(), current_user;`.
5. Consultá las tablas desde SQLTools.


La base de datos del proyecto se llama:

```text
fireassets
```

Las tablas iniciales del proyecto son:

```text
categorias
bienes
```

---

## 1. Objetivo de esta guía

Al terminar esta guía, deberías poder:

- ver la base de datos desde Visual Studio Code;
- inspeccionar tablas y columnas;
- ver registros guardados;
- ejecutar consultas SQL desde SQLTools;
- evitar ejecutar consultas en una conexión equivocada.

---

## 2. Extensiones necesarias

Instalá estas dos extensiones en Visual Studio Code.

| Extensión | Autor | Para qué sirve |
|---|---|---|
| SQLTools | Matheus Teixeira | Es la herramienta principal para ver bases de datos y ejecutar consultas SQL desde VS Code. |
| SQLTools PostgreSQL/Cockroach Driver | Matheus Teixeira | Es el conector que permite que SQLTools se comunique con PostgreSQL. |

> Importante: SQLTools solo funciona con PostgreSQL si también está instalado el driver de PostgreSQL.

---


## 2.1. Instalación y habilitación

Abrí **Extensions** (`Cmd + Shift + X` en macOS o `Ctrl + Shift + X` en Windows) y buscá exactamente:

- `SQLTools` — identificador `mtxr.sqltools`.
- `SQLTools PostgreSQL/Cockroach Driver` — identificador `mtxr.sqltools-driver-pg`.
- `Material Icon Theme` — identificador `pkief.material-icon-theme` (opcional, solo para iconos).

Después de instalar cada una, el botón debe decir **Disable**; eso confirma que está habilitada. Si dice **Enable**, hacé clic en **Enable**.

Para aplicar los iconos: ejecutá `Preferences: File Icon Theme`, elegí `Material Icon Theme` y, si no cambia, ejecutá `Developer: Reload Window`.

## 2.2. Extensiones que pueden confundir

Para este proyecto usamos SQLTools. No ejecutes consultas desde otra conexión que diga `sql_learning`, `Local SQL Learning` o desde el comando de otra extensión PostgreSQL. La extensión `ms-ossdata.vscode-pgsql` no es necesaria para este proyecto; deshabilitala solo si interfiere, sin afectar otros repositorios.

## 3. Qué debe estar listo antes de conectarse

Antes de configurar SQLTools, confirmá que ya tenés esto funcionando:

- PostgreSQL instalado.
- La base de datos `fireassets` creada.
- El proyecto descargado desde GitHub.
- Las dependencias de Python instaladas.
- Las migraciones ejecutadas.
- Las tablas `categorias` y `bienes` creadas.

Para verificar desde terminal:

### macOS

```bash
psql fireassets
```

### Windows

```powershell
psql -U postgres -d fireassets
```

Dentro de `psql`, podés ver las tablas con:

```sql
\dt
```

Deberías ver algo parecido a:

```text
alembic_version
bienes
categorias
```

Para salir de `psql`:

```sql
\q
```

---

## 4. Crear la conexión en SQLTools

Abrí Visual Studio Code y seguí este flujo:

1. Abrí el panel de SQLTools desde la barra lateral.
2. Elegí crear una nueva conexión.
3. Seleccioná PostgreSQL.
4. Completá los datos de conexión.

### Datos recomendados para macOS

Si PostgreSQL está configurado con tu usuario local, como en la máquina principal del proyecto:

| Campo | Valor |
|---|---|
| Connection name | FireAssets |
| Server Address | localhost |
| Port | 5432 |
| Database | fireassets |
| Username | tu usuario de macOS, por ejemplo `luis` |
| Password | dejar vacío si tu PostgreSQL local no usa password |
| SSL | Disabled |

Ejemplo:

```text
Connection name: FireAssets
Server Address: localhost
Port: 5432
Database: fireassets
Username: luis
Password: vacío
SSL: Disabled
```

### Datos recomendados para Windows

Si PostgreSQL fue instalado con el usuario `postgres`:

| Campo | Valor |
|---|---|
| Connection name | FireAssets |
| Server Address | localhost |
| Port | 5432 |
| Database | fireassets |
| Username | postgres |
| Password | la contraseña creada al instalar PostgreSQL |
| SSL | Disabled |

Ejemplo:

```text
Connection name: FireAssets
Server Address: localhost
Port: 5432
Database: fireassets
Username: postgres
Password: TU_PASSWORD_DE_POSTGRESQL
SSL: Disabled
```

> La contraseña no es la de GitHub ni la de Windows. Es la contraseña que se definió durante la instalación de PostgreSQL.

---

## 5. Cómo saber si la conexión está bien

En el panel de SQLTools deberías ver una conexión parecida a esta:

```text
FireAssets usuario@localhost:5432/fireassets
```

Al expandirla, deberías ver:

```text
fireassets database
└── Schemas
    └── public
        └── Tables
            ├── alembic_version
            ├── bienes
            └── categorias
```

Si ves `categorias` y `bienes`, la conexión está apuntando a la base correcta.

---

## 6. Crear una categoría de prueba

Para poder crear bienes después, primero necesitamos al menos una categoría.

Podés crearla desde `psql` o desde SQLTools.

Consulta SQL:

```sql
INSERT INTO categorias (nombre)
VALUES ('Mangueras')
ON CONFLICT (nombre) DO NOTHING;
```

Después verificá:

```sql
SELECT * FROM categorias;
```

Resultado esperado:

```text
id | nombre
1  | Mangueras
```

> El `id` puede variar. Lo importante es que exista una categoría.

---

## 7. Ejecutar una query desde SQLTools

Este es el flujo recomendado para ejecutar consultas con SQLTools.

1. Abrí o creá un archivo `.sql` en Visual Studio Code.
2. Escribí una consulta.
3. Abrí la paleta de comandos:
   - macOS: `Cmd + Shift + P`
   - Windows: `Ctrl + Shift + P`
4. Buscá este comando:

```text
SQLTools Connection: Run Current Query
```

5. Presioná Enter.
6. Revisá el panel de resultados de SQLTools.

Consulta de prueba:

```sql
SELECT * FROM categorias;
```

Resultado esperado:

```text
id | nombre
1  | Mangueras
```

---


## 7.1. Validar la conexión antes de consultar

En un archivo SQL conectado a `FireAssets`, ejecutá primero:

```sql
SELECT current_database(), current_user;
```

El primer resultado debe ser `fireassets`. Si aparece `sql_learning`, seleccionaste otra conexión.

Para ejecutar desde SQLTools:

1. Abrí un archivo `.sql`.
2. Usá **Connect to PostgreSQL** o **Change Active Connection**.
3. Seleccioná `FireAssets`.
4. Ejecutá **Run Current SQL** o **Run Query** desde SQLTools.
5. Revisá el panel de resultados.

No uses una barra que muestre `Local SQL Learning | sql_learning`.

## 8. Error común: ejecutar contra otra base de datos

Puede pasar que Visual Studio Code muestre otro botón de otra extensión PostgreSQL, por ejemplo:

```text
Run on active connection
```

Si esa barra muestra algo como:

```text
Local SQL Learning | sql_learning
```

no la uses para este proyecto.

Ese botón puede pertenecer a otra extensión y puede ejecutar la consulta en otra base de datos que no es `fireassets`.

Para este proyecto, usá este comando:

```text
SQLTools Connection: Run Current Query
```

---

## 9. Diferencia entre ver tablas y ejecutar queries

| Acción | Herramienta recomendada |
|---|---|
| Ver tablas visualmente | SQLTools |
| Ver registros guardados | SQLTools |
| Ejecutar una consulta rápida | SQLTools Connection: Run Current Query |
| Aprender SQL desde cero | Terminal con `psql` |
| Diagnosticar problemas de conexión | Terminal con `psql` |

La idea no es abandonar la terminal. La idea es usar ambas herramientas:

```text
psql      -> ayuda a entender qué está pasando
SQLTools  -> ayuda a ver la base más rápido
```

---

## 10. Checklist final

Antes de avanzar con los endpoints, confirmá esto:

- [ ] PostgreSQL está instalado.
- [ ] La base `fireassets` existe.
- [ ] El archivo `.env` del proyecto apunta a `fireassets`.
- [ ] Las migraciones fueron ejecutadas.
- [ ] Existen las tablas `categorias` y `bienes`.
- [ ] SQLTools muestra la conexión `FireAssets`.
- [ ] SQLTools muestra las tablas dentro de `public > Tables`.
- [ ] La query `SELECT * FROM categorias;` funciona.
- [ ] Existe al menos una categoría para poder crear bienes.

---

## 12. Errores frecuentes

- **Password is required:** SQLTools necesita la contraseña del usuario PostgreSQL; no es la de GitHub.
- **role postgres does not exist (macOS):** usá tu usuario local de PostgreSQL, por ejemplo `luis`.
- **psql no se reconoce (Windows):** agregá la carpeta `bin` de PostgreSQL al PATH y reabrí VS Code.
- **No data:** la tabla existe pero está vacía; insertá una categoría o ejecutá el endpoint.
- **Aparece sql_learning:** cambiá la conexión activa a `FireAssets` antes de ejecutar.

## 13. Próximo paso

Cuando la conexión esté funcionando, el próximo paso es probar el endpoint de creación de bienes desde Swagger:

```text
http://127.0.0.1:8000/docs
```

Ejemplo de JSON para crear un bien:

```json
{
  "internal_code": "BOM-001",
  "name": "Manguera forestal",
  "category_id": 1
}
```

Después se puede verificar en SQLTools con:

```sql
SELECT * FROM bienes;
```

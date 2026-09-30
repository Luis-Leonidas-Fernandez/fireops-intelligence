# Guía de base de datos en Windows

Esta guía explica cómo preparar PostgreSQL en Windows para que el proyecto pueda conectarse a la base de datos `fireassets`.

No necesitás entender todo PostgreSQL ahora. El objetivo de esta guía es que puedas verificar si tu computadora está lista para trabajar con el proyecto.

---

# Qué vamos a lograr

Al terminar, deberías tener:

```text
PostgreSQL instalado
PostgreSQL corriendo
base de datos fireassets creada
archivo .env configurado
proyecto listo para conectarse a la base
```

El flujo completo es:

```text
Windows
  ↓
PostgreSQL instalado
  ↓
servicio PostgreSQL corriendo
  ↓
base fireassets creada
  ↓
.env con DATABASE_URL
  ↓
FastAPI puede conectarse a PostgreSQL
```

---

# Antes de empezar

Vamos a usar **PowerShell**.

Para abrirlo:

1. Abrí el menú de Windows.
2. Buscá `PowerShell`.
3. Abrilo normalmente.

Si más adelante necesitás iniciar un servicio, puede hacer falta abrirlo como administrador.

---

# Paso 1 — Verificar si PostgreSQL está instalado

Ejecutá:

```powershell
psql --version
```

## Resultado esperado

Algo parecido a:

```text
psql (PostgreSQL) 18.x
```

Si ves una versión, PostgreSQL está instalado y `psql` funciona.

## Si aparece un error

Si ves algo como:

```text
psql no se reconoce como un comando interno o externo
```

puede significar una de estas dos cosas:

1. PostgreSQL no está instalado.
2. PostgreSQL está instalado, pero Windows no sabe dónde está `psql`.

En ese caso, pedí ayuda y enviá una captura del error.

---

# Paso 2 — Verificar si el servicio de PostgreSQL está corriendo

Ejecutá:

```powershell
Get-Service *postgres*
```

## Resultado esperado

Algo parecido a:

```text
Status   Name                DisplayName
------   ----                -----------
Running  postgresql-x64-18   postgresql-x64-18
```

La palabra importante es:

```text
Running
```

Eso significa que PostgreSQL está encendido.

## Si aparece `Stopped`

Si aparece detenido, abrí PowerShell como administrador y ejecutá:

```powershell
Start-Service postgresql-x64-18
```

> El nombre puede cambiar según la versión instalada. Si tu servicio no se llama `postgresql-x64-18`, copiá el nombre que aparece en tu computadora.

---

# Paso 3 — Entrar a PostgreSQL

Ejecutá:

```powershell
psql -U postgres
```

PostgreSQL puede pedirte una contraseña.

Esa contraseña es la que se eligió al instalar PostgreSQL.

## Resultado esperado

Si entra correctamente, vas a ver algo parecido a:

```text
postgres=#
```

Eso significa que estás dentro de PostgreSQL.

---

# Paso 4 — Ver las bases de datos existentes

Dentro de PostgreSQL, ejecutá:

```sql
\l
```

Este comando lista las bases de datos.

Buscá si existe una base llamada:

```text
fireassets
```

---

# Paso 5 — Crear la base de datos si no existe

Si `fireassets` NO aparece en la lista, creala con:

```sql
CREATE DATABASE fireassets;
```

El resultado esperado es:

```text
CREATE DATABASE
```

Después volvé a listar:

```sql
\l
```

Ahora debería aparecer:

```text
fireassets
```

---

# Paso 6 — Entrar a la base fireassets

Dentro de PostgreSQL, ejecutá:

```sql
\c fireassets
```

## Resultado esperado

Algo parecido a:

```text
Ahora está conectado a la base de datos «fireassets»
```

El prompt debería cambiar a:

```text
fireassets=#
```

Eso significa que estás dentro de la base de datos correcta.

---

# Paso 7 — Salir de PostgreSQL

Para salir, ejecutá:

```sql
\q
```

Volverás a PowerShell.

---

# Paso 8 — Crear el archivo .env del proyecto

Entrá a la carpeta del proyecto.

Ejemplo:

```powershell
cd C:\ruta\a\fire-control
```

> La ruta exacta depende de dónde tengas el proyecto en tu computadora.

Si existe `.env.example`, podés copiarlo:

```powershell
Copy-Item .env.example .env
```

Si no existe o está vacío, creá un archivo llamado:

```text
.env
```

En ese archivo colocá:

```env
APP_NAME=FireOps Intelligence
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets
SECRET_KEY=replace-this-value
```

Reemplazá:

```text
TU_PASSWORD
```

por la contraseña real del usuario `postgres`.

> Importante: no uses `postgresql+asyncpg://TU_PASSWORD@localhost:5432/fireassets`. Eso pone la contraseña en el lugar del usuario. La forma correcta en Windows es `postgres:TU_PASSWORD`.

---

# Paso 9 — Entender DATABASE_URL

Esta línea:

```env
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets
```

se lee así:

```text
postgresql       → tipo de base de datos
asyncpg          → driver async que usa Python
postgres         → usuario de PostgreSQL
TU_PASSWORD      → contraseña del usuario
localhost        → la base está en tu computadora
5432             → puerto típico de PostgreSQL
fireassets       → nombre de la base de datos
```

---

# Paso 10 — Cuidado con contraseñas con símbolos

Si tu contraseña tiene caracteres como:

```text
@  #  :  /  %
```

puede romper la URL.

Para aprender y trabajar localmente, conviene usar una contraseña simple.

Ejemplo:

```text
postgres123
```

Entonces la URL sería:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres123@localhost:5432/fireassets
```

---

# Paso 11 — Verificar que el proyecto tenga entorno virtual

Desde la carpeta del proyecto, verificá si existe:

```text
.venv
```

Si existe, activalo con:

```powershell
.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación, ejecutá:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Después intentá activar de nuevo:

```powershell
.venv\Scripts\Activate.ps1
```

Cuando está activo, normalmente ves algo así:

```text
(.venv) PS C:\ruta\a\fire-control>
```

---

# Paso 12 — Instalar dependencias si hace falta

Con el entorno virtual activo, ejecutá:

```powershell
pip install -r requirements.txt
```

Esto instala las herramientas que usa el proyecto, incluyendo:

```text
FastAPI
SQLAlchemy
asyncpg
Alembic
Pydantic Settings
pytest
```

---

# Paso 13 — Verificación rápida desde Python

Cuando el proyecto ya tenga creado el archivo de conexión a base de datos, se podrá probar desde Python.

Por ahora, lo importante es verificar:

```text
PostgreSQL corre
fireassets existe
.env tiene DATABASE_URL
```

---

# Qué enviar si algo falla

Si un paso falla, no pruebes comandos al azar.

Enviá esta información:

```text
Paso donde falló:
Comando que ejecuté:
Resultado esperado:
Error que apareció:
Captura o texto completo del error:
```

Ejemplo:

```text
Paso donde falló: Paso 3
Comando que ejecuté: psql -U postgres
Resultado esperado: entrar a PostgreSQL
Error que apareció: password authentication failed for user postgres
```

Esto permite ayudarte rápido.

---

# Resumen de comandos principales

```powershell
psql --version
Get-Service *postgres*
psql -U postgres
```

Dentro de PostgreSQL:

```sql
\l
CREATE DATABASE fireassets;
\c fireassets
\q
```

En el proyecto:

```powershell
Copy-Item .env.example .env
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

# Señal de éxito

Todo está bien si podés confirmar esto:

```text
psql --version funciona
Get-Service muestra PostgreSQL en Running
podés entrar con psql -U postgres
la base fireassets existe
el archivo .env tiene DATABASE_URL
```

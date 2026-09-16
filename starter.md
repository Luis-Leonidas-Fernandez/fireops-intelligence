# Starter — levantar el proyecto y la base de datos

Esta guía sirve para arrancar el proyecto localmente sin tener que recordar todos los comandos.

> Importante: el proyecto **no levanta PostgreSQL automáticamente**. Primero debe estar corriendo PostgreSQL y después se levanta la API con FastAPI/Uvicorn.

---

## 1. Ubicarse en la raíz del proyecto

### macOS / Linux

```bash
cd /Users/luis/Desktop/fire-control
```

### Windows / PowerShell

Entrar a la carpeta donde clonaste el proyecto. Ejemplo:

```powershell
cd "D:\Proyectos\fireops-intelligence"
```

Si tu carpeta tiene otro nombre, usá tu ruta real.

---

## 2. Activar el entorno virtual

### macOS / Linux

```bash
source .venv/bin/activate
```

### Windows / PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación, ejecutar una vez:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Después cerrar y abrir la terminal, y volver a probar:

```powershell
.\.venv\Scripts\Activate.ps1
```

Cuando el entorno está activo, deberías ver algo parecido a:

```text
(.venv)
```

---

## 3. Instalar dependencias

Con el entorno virtual activo:

```bash
python -m pip install -r requirements.txt
```

Este comando instala FastAPI, Uvicorn, SQLAlchemy, asyncpg, Alembic, pytest y otras herramientas del proyecto.

---

## 4. Verificar que PostgreSQL esté corriendo

### macOS con Homebrew

Ver servicios:

```bash
brew services list
```

Si PostgreSQL no está iniciado:

```bash
brew services start postgresql@18
```

Verificar conexión:

```bash
psql fireassets
```

Si entrás a PostgreSQL, salí con:

```sql
\q
```

### Windows

Primero verificar que `psql` responda:

```powershell
psql --version
```

Después probar conexión:

```powershell
psql -U postgres -d fireassets
```

PostgreSQL va a pedir la contraseña que se configuró durante la instalación.

Si entrás a PostgreSQL, salí con:

```sql
\q
```

> Si `psql` no se reconoce como comando, falta agregar la carpeta `bin` de PostgreSQL al `Path` de Windows.

---

## 5. Verificar archivo `.env`

En la raíz del proyecto debe existir un archivo llamado:

```text
.env
```

Ejemplo para macOS cuando el usuario local se conecta sin contraseña:

```env
DATABASE_URL=postgresql+asyncpg://luis@localhost:5432/fireassets
SECRET_KEY=dev-secret-key
ENVIRONMENT=development
```

Ejemplo para Windows con usuario `postgres` y contraseña:

```env
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets
SECRET_KEY=dev-secret-key
ENVIRONMENT=development
```

Reemplazar `TU_PASSWORD` por la contraseña real de PostgreSQL.

---

## 6. Verificar que existan las tablas

Entrar a PostgreSQL:

### macOS

```bash
psql fireassets
```

### Windows

```powershell
psql -U postgres -d fireassets
```

Dentro de PostgreSQL, listar tablas:

```sql
\dt
```

Deberían existir al menos:

```text
categorias
bienes
```

Salir:

```sql
\q
```

---

## 7. Levantar la API

Con PostgreSQL corriendo y el entorno virtual activo:

```bash
python -m uvicorn app.main:app --reload
```

Si todo está bien, la terminal debería mostrar que Uvicorn está corriendo en:

```text
http://127.0.0.1:8000
```

---

## 8. URLs útiles

Con la API levantada, abrir en el navegador:

| URL | Para qué sirve |
|---|---|
| `http://127.0.0.1:8000/` | Verifica que la API responde |
| `http://127.0.0.1:8000/health` | Verifica salud básica del servicio |
| `http://127.0.0.1:8000/docs` | Abre Swagger UI para probar endpoints |

Cuando la Task 03 esté implementada, también debería aparecer:

```text
POST /inventory/assets
```

---

## 9. Apagar la API

En la terminal donde corre Uvicorn, presionar:

```text
CTRL + C
```

Eso baja la API.

---

## 10. Desactivar el entorno virtual

```bash
deactivate
```

Funciona tanto en macOS/Linux como en Windows cuando el entorno está activo.

---

## Checklist rápido para empezar a trabajar

- [ ] Estoy en la raíz del proyecto.
- [ ] Activé `.venv`.
- [ ] Instalé dependencias.
- [ ] PostgreSQL está corriendo.
- [ ] El archivo `.env` existe.
- [ ] `DATABASE_URL` apunta a `fireassets`.
- [ ] Las tablas `categorias` y `bienes` existen.
- [ ] Levanté la API con `python -m uvicorn app.main:app --reload`.
- [ ] Abrí `http://127.0.0.1:8000/docs`.


# Plan de clases para preparar FireOps Intelligence en Windows

*Guía para instalar herramientas, configurar PostgreSQL, trabajar con ramas y construir el primer flujo de inventario*

## Propósito del documento

Este documento organiza las clases para cuatro participantes que están aprendiendo a programar. La idea es que todos avancen juntos, con el mismo ejercicio, usando Windows, PostgreSQL, Git, FastAPI, SQLAlchemy, Alembic y pruebas automáticas.

El objetivo no es memorizar comandos. El objetivo es entender el flujo completo: preparar la computadora, clonar el proyecto, crear una rama, conectar con la base, crear tablas, registrar un bien, probarlo y subir una Pull Request para revisión.

## Principio de trabajo

Todos hacen la misma tarea al mismo tiempo. Cada participante trabaja en su propia rama. Todos suben Pull Request. El responsable revisa todas, comenta aprendizajes y mergea una sola versión a main.

| **Regla** | **Motivo** |
| --- | --- |
| No trabajar directo en main | main representa la versión limpia del proyecto. |
| Crear una rama por tarea | Evita pisarse y permite revisar cada práctica por separado. |
| Subir PR aunque no se mergee | La PR sirve para practicar, recibir feedback y aprender. |
| Mergear una sola PR | Como todos hacen la misma tarea, mergear todas generaría conflictos y duplicación. |
| No improvisar comandos | Si algo falla, se copia el error completo y se pide ayuda. |

## Ruta general de clases

| **Etapa** | **Resultado esperado** |
| --- | --- |
| Clase 0 Preparación | Python, Git, PostgreSQL y VS Code instalados. |
| Clase 1 Proyecto local | Repositorio clonado, entorno virtual creado y dependencias instaladas. |
| Clase 2 Base de datos | PostgreSQL corriendo, base fireassets creada y .env configurado. |
| Task 01 | Conexión existente verificada desde Python. |
| Task 02 | Tablas categorias y bienes creadas con Alembic. |
| Task 03 | Endpoint POST /inventory/assets guardando en PostgreSQL. |
| Task 04 | Test automático verificando el registro de bienes. |
| Cierre | Cada participante sube PR y explica lo que hizo. |

## Clase 0 Preparar Windows

Esta clase se hace antes de programar. Si la computadora no está preparada, programar se vuelve frustrante. Primero se verifica el terreno.

### Herramientas necesarias

| **Herramienta** | **Para qué sirve** | **Verificación** |
| --- | --- | --- |
| Python | Ejecutar el backend FastAPI y las herramientas del proyecto. | python --version o py --version |
| Git | Clonar el repositorio, crear ramas, hacer commits y subir PRs. | git --version |
| PostgreSQL | Base de datos donde se guardarán categorias y bienes. | psql --version |
| Visual Studio Code | Editor de código para trabajar en el proyecto. | Abrir el proyecto desde VS Code |
| Extensión PostgreSQL VS Code | Ver bases y tablas de forma visual después de crearlas. | ms-ossdata.vscode-pgsql |

### Comandos iniciales de verificación

```text
python --version
git --version
psql --version
```

Si python no funciona, probar py --version. Si psql no funciona, probablemente PostgreSQL no está instalado o falta agregarlo al PATH.

## Clase 1 Configurar PostgreSQL en Windows

PostgreSQL debe instalarse con el usuario postgres y puerto 5432. Durante la instalación, cada participante debe anotar la contraseña del usuario postgres. Esa contraseña se usará en el archivo .env.

### Verificar el servicio

```text
Get-Service *postgres*
```

El resultado esperado debe mostrar Running. Si aparece Stopped, abrir PowerShell como administrador y ejecutar Start-Service con el nombre real del servicio.

```text
Start-Service postgresql-x64-18
```

### Crear la base fireassets

```text
psql -U postgres
```

Dentro de PostgreSQL ejecutar:

```text
\l
CREATE DATABASE fireassets;
\c fireassets
\q
```

Si la base ya existe, no hay que crearla de nuevo. Sólo conectarse con \\c fireassets.

## Clase 2 Clonar proyecto e instalar dependencias

### Clonar o abrir el proyecto

```text
git clone <REPOSITORY_URL>
cd fire-control
```

Si el repositorio ya está descargado, entrar a la carpeta correspondiente con cd.

### Crear y activar entorno virtual

```text
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación, ejecutar una sola vez:

```text
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Instalar dependencias

```text
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Verificar dependencias principales

```text
python -c "import fastapi, sqlalchemy, asyncpg, alembic; print('Environment ready')"
```

## Configurar el archivo env

El archivo .env contiene configuración local. No se sube a Git. Cada participante debe tener su propio .env.

```text
APP_NAME=FireOps Intelligence
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets
SECRET_KEY=replace-this-value
```

TU_PASSWORD debe reemplazarse por la contraseña real del usuario postgres. No debe quedar escrito literalmente.

| **Parte** | **Significado** |
| --- | --- |
| postgresql | Tipo de base de datos. |
| asyncpg | Driver async usado por Python. |
| postgres | Usuario típico de PostgreSQL en Windows. |
| TU_PASSWORD | Contraseña real elegida al instalar PostgreSQL. |
| localhost | La base está en la misma computadora. |
| 5432 | Puerto estándar de PostgreSQL. |
| fireassets | Nombre de la base del proyecto. |

No usar DATABASE_URL=postgresql+asyncpg://TU_PASSWORD@localhost:5432/fireassets. Eso pone la contraseña en el lugar del usuario.

## Flujo Git para cada tarea

Antes de cada tarea se crea una rama nueva desde main actualizado. Esta parte está detallada en GIT_WORKFLOW.md, pero el resumen operativo es el siguiente.

```text
git checkout main
git pull
git checkout -b participant-X/task-name
```

Después de terminar la tarea:

```text
git status
git diff
git add .
git commit -m "feat: describe the task"
git push -u origin participant-X/task-name
```

Luego se abre una Pull Request en GitHub. Se revisan todas las PRs, pero se mergea una sola.

## Task 01 Verificar conexión existente

La conexión ya existe en el proyecto. En esta tarea los participantes no escriben esa conexión: la leen, la entienden y verifican que funcione.

| **Archivo** | **Responsabilidad** |
| --- | --- |
| app/config/settings.py | Lee DATABASE_URL desde .env. |
| app/infrastructure/database/base.py | Define la Base de SQLAlchemy. |
| app/infrastructure/database/session.py | Crea engine y sesiones async. |
| app/infrastructure/database/metadata.py | Lugar reservado para centralizar metadata/imports. |

```text
python -c "from app.config.settings import get_settings; settings = get_settings(); print('App name:', settings.app_name)"
python -c "from app.infrastructure.database.session import engine; print('Engine type:', type(engine).__name__)"
python -c "from app.main import app; print(app.title)"
```

Resultado esperado: App name, Engine type AsyncEngine y título Fire Control.

## Task 02 Crear categorias y bienes

Se crean las primeras tablas reales. No se crea todo el modelo patrimonial todavía. Se enseña una relación simple pero real: una categoría puede tener muchos bienes.

```text
categorias 1 -> N bienes
```

| **Modelo** | **Tabla** | **Campos iniciales** |
| --- | --- | --- |
| Category | categorias | id, nombre |
| Asset | bienes | id, codigo_interno, nombre, categoria_id |

La clave importante es ForeignKey("categorias.id"), porque impide crear bienes apuntando a una categoría inexistente.

```text
alembic revision --autogenerate -m "create categories and assets tables"
alembic upgrade head
```

Luego se verifica con PostgreSQL:

```text
psql -U postgres -d fireassets
\dt
\d bienes
```

Al final de esta tarea se puede instalar y usar la extensión PostgreSQL de Visual Studio Code para ver visualmente las tablas categorias y bienes.

## Task 03 Registrar un bien usando PostgreSQL

Se crea el endpoint POST /inventory/assets. Antes de registrar un bien, debe existir una categoría. No se debe asumir que categoria_id siempre es 1.

```text
INSERT INTO categorias (nombre)
VALUES ('Mangueras')
ON CONFLICT (nombre) DO NOTHING;

SELECT id, nombre FROM categorias WHERE nombre = 'Mangueras';
```

Con ese id real se prueba el endpoint desde http://127.0.0.1:8000/docs.

```text
{
  "internal_code": "BOM-001",
  "name": "Manguera forestal",
  "category_id": 1
}
```

Si el código BOM-001 ya existe, usar otro como BOM-002. El campo codigo_interno es único.

## Task 04 Test del registro de bienes

Se crea una prueba automática que prepara o busca la categoría Mangueras, genera un código interno único con uuid4 y llama al endpoint real.

| **Concepto** | **Por qué importa** |
| --- | --- |
| pytest.mark.asyncio | Permite escribir tests async. |
| httpx.AsyncClient | Permite llamar la app FastAPI async sin levantar servidor real. |
| uuid4 | Evita repetir codigo_interno entre ejecuciones. |
| category_id real | Evita depender de que la categoría tenga id 1. |

```text
python -m pytest -v -s
```

La opción -s muestra los print de aprendizaje en consola.

## Uso de print durante las clases

Durante la clase se permite usar print para entender qué pasa. Pero los prints de práctica no deben quedar en el código final si sólo servían para mirar valores temporalmente.

| **Lugar** | **Uso permitido** |
| --- | --- |
| Task 01 | Prints desde comandos python -c. No modifican archivos. |
| Task 02 | Mensajes SELECT en PostgreSQL para ver resultados. |
| Task 03 | Prints temporales en el endpoint para ver antes y después del guardado. |
| Task 04 | Prints en el test para ver category_id y response JSON. |

Antes del commit, revisar:

```text
git diff
```

Si quedaron prints de práctica en archivos .py, borrarlos antes de subir la PR, salvo que el responsable indique lo contrario.

## Pull Request y merge

Cada participante sube una PR. La PR no significa que el código se mergea. Significa que el código está listo para revisión.

| **Paso** | **Acción** |
| --- | --- |
| 1 | Participante sube su rama. |
| 2 | Participante abre PR. |
| 3 | Responsable revisa las PRs. |
| 4 | Se comentan aprendizajes. |
| 5 | Se mergea una sola PR a main. |
| 6 | Todos vuelven a main y hacen git pull antes de la siguiente tarea. |

```text
git checkout main
git pull
```

## Checklist antes de empezar con código

- Python funciona.

- Git funciona.

- PostgreSQL funciona.

- La base fireassets existe.

- .env está configurado.

- .venv está activo.

- Las dependencias están instaladas.

- La rama de trabajo está creada.

- Nadie está trabajando directo en main.

## Cómo reportar errores

Cuando algo falla, el participante debe enviar información concreta. No alcanza con decir no anda.

```text
Paso donde falló:
Comando ejecutado:
Resultado esperado:
Error completo:
Captura si aplica:
```

## Cierre recomendado de cada clase

Cada participante debe explicar con sus palabras qué hizo, qué archivo tocó, qué comando ejecutó y qué resultado obtuvo. Si no puede explicarlo, todavía no terminó la tarea aunque el código funcione.

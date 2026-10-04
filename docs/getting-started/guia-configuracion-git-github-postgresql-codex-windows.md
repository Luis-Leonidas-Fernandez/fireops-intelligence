# Guia de configuracion para Git GitHub PostgreSQL y Codex en Windows

**Objetivo.** Este documento prepara a cada participante para poder trabajar en FireOps Intelligence sin trabarse en el entorno. Antes de escribir codigo, cada computadora debe tener Git, GitHub, PostgreSQL, Python, VS Code y Codex funcionando.

**Regla de aprendizaje.** Codex puede acelerar instalacion, diagnostico y explicacion de errores, pero no reemplaza entender los comandos. Cada participante debe poder explicar que instalo, para que sirve y como verifico que funciona.

## Resultado esperado al terminar la clase 0

| **Parte** | **Criterio de aprobacion** |
| --- | --- |
| Git | git --version responde una version |
| GitHub | La cuenta esta creada y GitHub Desktop o gh esta autenticado |
| PostgreSQL | psql --version responde y el servicio esta corriendo |
| Base de datos | Existe una base llamada fireassets |
| Python | python --version responde Python 3.12 o superior |
| Proyecto | El repo esta clonado y el entorno virtual instalado |
| Aplicacion | Uvicorn levanta sin error |

## Orden correcto de trabajo

1. Instalar herramientas base.

2. Configurar Git con nombre y email.

3. Crear o verificar la cuenta de GitHub.

4. Clonar el proyecto.

5. Instalar PostgreSQL y crear la base fireassets.

6. Crear el archivo .env con la DATABASE_URL correcta.

7. Crear entorno virtual e instalar dependencias.

8. Levantar el proyecto y ejecutar tests.

## Instalar Git en Windows

Git permite guardar cambios, crear ramas, subir codigo y abrir Pull Requests. Sin Git configurado, no se puede trabajar en equipo de forma ordenada.

Descargar desde git-scm.com. Durante la instalacion, dejar las opciones recomendadas. Luego cerrar y abrir de nuevo PowerShell.

```text
git --version
git config --global user.name "Nombre Apellido"
git config --global user.email "email-de-github@example.com"
git config --global --list
```

## Configurar GitHub

Para principiantes conviene usar GitHub Desktop al inicio. Reduce errores de autenticacion y permite visualizar ramas, commits y Pull Requests.

1. Crear cuenta en github.com.

2. Instalar GitHub Desktop.

3. Iniciar sesion.

4. Clonar el repositorio del proyecto.

5. Confirmar que el proyecto abre en VS Code.

## Instalar PostgreSQL en Windows

PostgreSQL es el motor de base de datos. Aca se guardaran las tablas categorias y bienes. Durante la instalacion, cada participante debe anotar la contrasena del usuario postgres.

1. Descargar PostgreSQL desde postgresql.org.

2. Ejecutar el instalador.

3. Elegir una contrasena para el usuario postgres.

4. Dejar el puerto 5432.

5. Instalar pgAdmin si aparece seleccionado.

6. Cerrar y abrir PowerShell despues de instalar.

```text
psql --version
```

## Crear la base de datos fireassets

Entrar a PostgreSQL con el usuario postgres. Cuando pida password, escribir la contrasena definida durante la instalacion.

```text
psql -U postgres
CREATE DATABASE fireassets;
\l
\q
```

## Configurar el archivo env del proyecto

En la raiz del proyecto se debe crear un archivo llamado .env. No se sube a GitHub porque contiene configuracion local.

```text
APP_NAME=FireOps Intelligence
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets
SECRET_KEY=replace-this-value
```

TU_PASSWORD debe reemplazarse por la contrasena real del usuario postgres. No borrar la palabra postgres antes de los dos puntos porque ese es el usuario de la base.

## Instalar Python y dependencias del proyecto

Python ejecuta la API. El entorno virtual separa las dependencias de este proyecto de otros proyectos de la computadora.

```text
python --version
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Usar Codex sin perder el aprendizaje

Codex puede ayudar a avanzar mas rapido en instalacion y diagnostico. La condicion es que cada participante le pida explicaciones antes de ejecutar comandos que no entiende.

```text
Estoy aprendiendo programacion. No me des la solucion completa de golpe. Guiame paso a paso para configurar este proyecto en Windows. Explicame que hace cada comando antes de ejecutarlo. Si aparece un error, ayudame a entender la causa.
```

| **Uso de Codex** | **Regla** |
| --- | --- |
| Permitido | Instalar dependencias, explicar errores, revisar comandos, diagnosticar PostgreSQL, verificar tests |
| No permitido | Pedir la tarea completa, copiar codigo sin entenderlo, subir una PR que no pueda explicar |

## Verificar que el proyecto funciona

```text
python -m uvicorn app.main:app --reload
```

Si levanta correctamente, abrir el navegador en http://127.0.0.1:8000/docs.

```text
python -m pytest -v
```

## Errores comunes y como reaccionar

| **Error** | **Causa probable** |
| --- | --- |
| git no se reconoce | Git no esta instalado o PowerShell se abrio antes de instalar. Cerrar y abrir terminal. |
| psql no se reconoce | PostgreSQL no esta en PATH. Usar pgAdmin o corregir PATH. |
| password authentication failed | La contrasena de postgres no coincide con la DATABASE_URL. |
| database fireassets does not exist | No se creo la base. Entrar con psql y ejecutar CREATE DATABASE fireassets. |
| ModuleNotFoundError | Faltan dependencias o no esta activado .venv. |

## Checklist final antes de empezar Task 01

- Git responde version.

- Git tiene user.name y user.email.

- GitHub Desktop esta logueado.

- Repo clonado.

- PostgreSQL instalado.

- Base fireassets creada.

- .env creado con DATABASE_URL correcta.

- Entorno virtual activado.

- Dependencias instaladas.

- API levanta.

- Tests corren.

## Criterio del instructor

No avanzar a codigo hasta que todos pasen la checklist. Si alguien queda atras por Git, GitHub o PostgreSQL, se resuelve eso primero. Configurar el entorno tambien es parte del oficio profesional.

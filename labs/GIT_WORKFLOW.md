# Flujo de Git — crear rama, subir cambios y pedir revisión

Esta guía explica el camino completo para trabajar sin pisar a tus compañeros.

La idea principal es simple:

```text
NO trabajamos directo en main.
Cada participante trabaja en su propia rama.
Después sube esa rama.
El responsable revisa y decide si se une a main.
```

---

# Antes de empezar

## Qué es `main`

`main` es la rama principal del proyecto.

Pensala como la versión oficial del sistema.

Por eso, no debemos modificarla directamente.

## Qué es una rama

Una rama es una copia de trabajo separada.

Sirve para que puedas practicar, equivocarte, corregir y subir tu trabajo sin romper la versión principal.

Ejemplo:

```text
main
  ↓
participant-1/register-asset-practice
```

Tu código vive en tu rama hasta que el responsable lo revise.

## Qué es una PR

PR significa Pull Request.

Una PR es un pedido de revisión.

No significa que tu código ya entró al proyecto principal. Significa:

> Terminé mi trabajo, por favor revisalo antes de unirlo a main.

---

# Flujo cronológico completo

Seguí estos pasos en orden.

No saltees pasos.

---

## Paso 1 — Abrir la terminal en el proyecto

Primero tenés que estar dentro de la carpeta del proyecto.

Ejemplo:

```powershell
cd "C:\Users\Usuario\Desktop\fireops-intelligence"
```

Para verificar dónde estás, ejecutá:

```powershell
Get-Location
```

Resultado esperado:

```text
C:\Users\Usuario\Desktop\fireops-intelligence
```

En Windows la ruta puede cambiar según dónde clonaste el proyecto. Lo importante es estar dentro de la carpeta donde existen `app`, `requirements.txt` y `README.md`.

---

## Paso 2 — Ver en qué rama estás

Ejecutá:

```powershell
git branch
```

La rama actual aparece marcada con `*`.

Ejemplo:

```text
* main
```

Si ves `* main`, estás en la rama principal.

---

## Paso 3 — Volver a `main`

Antes de crear tu rama, asegurate de estar en `main`:

```powershell
git checkout main
```

Esto te mueve a la rama principal.

---

## Paso 4 — Descargar la última versión

Ejecutá:

```powershell
git pull
```

Esto trae los últimos cambios del proyecto.

¿Por qué hacemos esto?

Porque tu nueva rama debe nacer desde la versión más actualizada posible.

> Si `git pull` muestra un error, frená y pedí ayuda.

---

## Paso 5 — Ver si tu rama ya existe

Antes de crear una rama nueva, revisá las ramas que ya tenés en tu máquina:

```powershell
git branch
```

Buscá una rama con tu número.

Ejemplo para participante 1:

```text
participant-1/register-asset-practice
```

---

# Si la rama NO existe

Creala con el comando correspondiente.

## Participante 1

```powershell
git checkout -b participant-1/register-asset-practice
```

## Participante 2

```powershell
git checkout -b participant-2/register-asset-practice
```

## Participante 3

```powershell
git checkout -b participant-3/register-asset-practice
```

## Participante 4

```powershell
git checkout -b participant-4/register-asset-practice
```

Este comando hace dos cosas:

1. crea una rama nueva;
2. te cambia automáticamente a esa rama.

---

# Si la rama YA existe

No la crees de nuevo.

Sólo cambiate a esa rama.

## Participante 1

```powershell
git checkout participant-1/register-asset-practice
```

## Participante 2

```powershell
git checkout participant-2/register-asset-practice
```

## Participante 3

```powershell
git checkout participant-3/register-asset-practice
```

## Participante 4

```powershell
git checkout participant-4/register-asset-practice
```

---

## Paso 6 — Confirmar que estás en tu rama

Ejecutá:

```powershell
git branch
```

Ejemplo esperado para participante 1:

```text
  main
* participant-1/register-asset-practice
```

El `*` debe estar en tu rama, no en `main`.

> Si el `*` está en `main`, NO empieces la tarea todavía.

---

## Paso 7 — Hacer la tarea

Ahora sí, seguí el README de tu carpeta.

Ejemplo:

```text
labs/README.md
```

Ese README te indica qué archivos crear o modificar.

---

## Paso 8 — Ver qué archivos cambiaste

Cuando termines o quieras revisar tu avance, ejecutá:

```powershell
git status
```

Git te va a mostrar archivos modificados o nuevos.

Ejemplo:

```text
modified: app/main.py
new file: app/modules/inventory/register_asset/router.py
new file: app/modules/inventory/register_asset/schemas.py
new file: tests/modules/inventory/test_register_asset.py
```

---

## Paso 9 — Ejecutar las pruebas

Antes de subir tu trabajo, ejecutá:

```powershell
python -m pytest -v
```

Resultado esperado:

```text
1 passed
```

Si falla, no subas todavía. Primero intentá leer el error y pedí ayuda.

---

## Paso 10 — Preparar los archivos para guardar

Ejecutá:

```powershell
git add .
```

Esto le dice a Git:

> Quiero incluir estos cambios en mi próximo guardado.

---

## Paso 11 — Crear un commit

Ejecutá:

```powershell
git commit -m "feat: practice register asset endpoint"
```

Un commit es una foto de tus cambios.

El mensaje debe explicar qué hiciste.

En este caso:

```text
feat: practice register asset endpoint
```

significa:

> agregué una práctica para crear el endpoint de registrar bienes.

---

## Paso 12 — Subir tu rama

Ejecutá el comando correspondiente a tu participante.

## Participante 1

```powershell
git push -u origin participant-1/register-asset-practice
```

## Participante 2

```powershell
git push -u origin participant-2/register-asset-practice
```

## Participante 3

```powershell
git push -u origin participant-3/register-asset-practice
```

## Participante 4

```powershell
git push -u origin participant-4/register-asset-practice
```

Esto sube tu rama al repositorio remoto.

Todavía no une tu código con `main`.

---

# Paso 13 — Crear la Pull Request

Después del `git push`, normalmente GitHub muestra un enlace en la terminal para crear la PR.

Si aparece un enlace, abrilo en el navegador.

También podés entrar al repositorio en GitHub y buscar un botón parecido a:

```text
Compare & pull request
```

## Qué completar en la PR

Título sugerido:

```text
feat: practice register asset endpoint
```

Descripción sugerida:

```md
## Qué hice

Implementé la práctica para crear el endpoint de registrar bienes.

## Cómo lo probé

- Ejecuté `python -m pytest -v`
- Revisé el endpoint en `/docs`

## Rama

participant-X/register-asset-practice

## Notas

Indicar acá si algo falló o si hubo dudas.
```

Reemplazá `participant-X` por tu número real.

---

# Paso 14 — Avisar al responsable

Cuando la PR esté creada, avisá con este formato:

```text
Participante: <tu número>
Rama: participant-X/register-asset-practice
PR: <link de GitHub>
Pruebas: python -m pytest -v funcionó / no funcionó
Comentario: <qué hiciste o dónde tuviste problemas>
```

Ejemplo:

```text
Participante: 1
Rama: participant-1/register-asset-practice
PR: https://github.com/organizacion/proyecto/pull/1
Pruebas: python -m pytest -v funcionó
Comentario: pude crear el endpoint y verlo en /docs
```

---

# Qué NO hacer

## No subir directo a main

No ejecutes:

```powershell
git push origin main
```

## No hacer merge

No ejecutes:

```powershell
git merge
```

El merge lo hace el responsable después de revisar.

## No probar comandos al azar

Si Git muestra palabras como estas:

```text
conflict
merge
rebase
rejected
```

frená y pedí ayuda.

Esto no es un fracaso. Es parte normal de trabajar con Git.


---

# Ejemplo completo de Pull Request

Cuando GitHub te pida completar la Pull Request, podés usar este modelo.

No copies sin pensar: leé cada parte y completá lo que corresponda.

---

## Título de la Pull Request

Usá este título:

```text
feat: practice register asset endpoint
```

## Qué significa el título

- `feat` significa que agregaste una funcionalidad.
- `practice register asset endpoint` significa que la funcionalidad es una práctica para registrar bienes.

---

## Descripción de la Pull Request

Copiá este texto en la descripción de la PR y completá las partes necesarias:

```md
## Qué hice

Implementé la práctica para crear el endpoint de registro de bienes.

El endpoint creado es:

POST /inventory/assets

## Archivos modificados

- app/modules/inventory/register_asset/schemas.py
- app/modules/inventory/register_asset/router.py
- app/main.py
- tests/modules/inventory/test_register_asset.py

## Cómo funciona

El usuario envía un JSON con los datos básicos del bien:

```json
{
  "internal_code": "BOM-001",
  "name": "Manguera forestal",
  "category_id": 1
}
```

FastAPI recibe la petición, Pydantic valida los datos, SQLAlchemy guarda el bien en PostgreSQL y el endpoint devuelve el bien creado.

Respuesta esperada:

```json
{
  "id": 1,
  "internal_code": "BOM-001",
  "name": "Manguera forestal",
  "category_id": 1
}
```

## Cómo lo probé

- [ ] Ejecuté `python -m pytest -v`
- [ ] El test pasó correctamente
- [ ] Abrí `http://127.0.0.1:8000/docs`
- [ ] Vi el endpoint `POST /inventory/assets`
- [ ] Probé el endpoint manualmente desde `/docs`

## Resultado de las pruebas

Pegar acá el resultado de la terminal.

Ejemplo:

```text
1 passed
```

## Dudas o problemas

Escribir acá si hubo algún problema.

Si no hubo problemas, escribir:

No tuve problemas para completar la práctica.
```

---

# Ejemplo de PR ya completada

Así podría verse una PR completa:

```md
## Qué hice

Implementé la práctica para crear el endpoint de registro de bienes.

El endpoint creado es:

POST /inventory/assets

## Archivos modificados

- app/modules/inventory/register_asset/schemas.py
- app/modules/inventory/register_asset/router.py
- app/main.py
- tests/modules/inventory/test_register_asset.py

## Cómo funciona

El usuario envía un JSON con los datos básicos del bien:

```json
{
  "internal_code": "BOM-001",
  "name": "Manguera forestal",
  "category_id": 1
}
```

FastAPI recibe la petición, Pydantic valida los datos, SQLAlchemy guarda el bien en PostgreSQL y el endpoint devuelve el bien creado.

Respuesta esperada:

```json
{
  "id": 1,
  "internal_code": "BOM-001",
  "name": "Manguera forestal",
  "category_id": 1
}
```

## Cómo lo probé

- [x] Ejecuté `python -m pytest -v`
- [x] El test pasó correctamente
- [x] Abrí `http://127.0.0.1:8000/docs`
- [x] Vi el endpoint `POST /inventory/assets`
- [x] Probé el endpoint manualmente desde `/docs`

## Resultado de las pruebas

```text
1 passed
```

## Dudas o problemas

No tuve problemas para completar la práctica.
```

---

# Qué debe revisar el responsable

El responsable del proyecto va a revisar:

- que la rama no sea `main`;
- que los archivos estén en las carpetas correctas;
- que el endpoint aparezca en `/docs`;
- que el test exista;
- que `python -m pytest -v` pase;
- que el participante pueda explicar con sus palabras qué hizo.

La Pull Request no es sólo para subir código.

También sirve para demostrar que entendiste el flujo.

---

# Antes de hacer commit — revisar prints de práctica

Durante la clase podés usar `print()` para entender qué está pasando.

Pero antes de crear el commit, revisá si quedaron prints de práctica en el código.

Ejecutá:

```powershell
git diff
```

Buscá líneas como:

```python
print(...)
```

Regla:

```text
Si el print era sólo para aprender o mirar datos en consola, borralo antes del commit.
```

No subas una Pull Request llena de prints de prueba.

Eso ensucia el código y hace más difícil revisar.

---

# Resumen rápido

```powershell
cd "C:\Users\Usuario\Desktop\fireops-intelligence"
git checkout main
git pull
git branch

# Si tu rama no existe:
git checkout -b participant-X/register-asset-practice

# Si tu rama ya existe:
git checkout participant-X/register-asset-practice

# Hacer la tarea
python -m pytest -v

git status
git add .
git commit -m "feat: practice register asset endpoint"
git push -u origin participant-X/register-asset-practice
```

Después del push, crear la PR en GitHub y avisar al responsable.

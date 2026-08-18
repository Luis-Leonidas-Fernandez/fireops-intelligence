# Task 04 — Test del registro de bienes

En esta tarea vamos a crear una prueba automática para el endpoint que registra bienes.

## Objetivo

Crear:

```text
tests/modules/inventory/test_register_asset.py
```

## Importante

Este test llama al endpoint real.

Como el endpoint guarda en PostgreSQL, la base de datos debe estar configurada y la tabla `bienes` debe existir.

## Rama sugerida

```powershell
git checkout main
git pull
git checkout -b participant-X/task-04-test-register-asset
```

---

# Paso 1 — Crear carpeta de tests

Crear si no existe:

```text
tests/modules/inventory/
```

---

# Paso 2 — Crear test

Crear:

```text
tests/modules/inventory/test_register_asset.py
```

Copiar:

```python
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_asset_creates_asset() -> None:
    internal_code = f"BOM-{uuid4().hex[:8]}"

    response = client.post(
        "/inventory/assets",
        json={
            "internal_code": internal_code,
            "name": "Manguera forestal",
            "category_id": 1,
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert isinstance(data["id"], int)
    assert data["internal_code"] == internal_code
    assert data["name"] == "Manguera forestal"
    assert data["category_id"] == 1
```

## Por qué usamos `uuid4`

La tabla `bienes` exige que `codigo_interno` sea único.

Si el test usara siempre `BOM-001`, la segunda ejecución podría fallar porque ese código ya existe.

Con `uuid4`, generamos un código distinto cada vez.

---

# Paso 3 — Ejecutar test

```powershell
python -m pytest -v
```

Resultado esperado:

```text
1 passed
```

---

# Paso 4 — Revisar cambios

```powershell
git status
```

No subas `.env`, `.venv`, `__pycache__` ni archivos temporales.

---

# Qué entregar

- Resultado de `python -m pytest -v`.
- Explicación breve de qué prueba el test.
- Si falla, copiar el error completo.

---

# Qué aprendiste

Un test automático permite comprobar que el endpoint sigue funcionando sin probar todo manualmente desde `/docs`.

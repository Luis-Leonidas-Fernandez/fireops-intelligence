import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_root_serves_frontend() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Fire Control — Inventario general" in response.text
    assert 'src="js/app.js?v=20261003-light-theme"' in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_registration_page_is_separate_from_dashboard() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get("/registro")
        stylesheet = await client.get("/css/registro.css")
        script = await client.get("/js/registro.js")

    assert page.status_code == 200
    assert "Crear cuenta | Fire Control" in page.text
    assert "Registro no disponible" not in page.text
    assert "El formulario es únicamente una vista previa visual" not in page.text
    assert "El inicio de sesión todavía no está disponible" not in page.text
    assert 'class="submit-button" type="submit"' in page.text
    assert '<a href="/iniciar-sesion">Iniciar sesión</a>' in page.text
    assert "<dialog" not in page.text
    assert 'event.preventDefault()' in script.text
    assert "Atención de emergencias 24 hs." in page.text
    assert 'href="/css/registro.css"' in page.text
    assert 'src="/js/registro.js"' in page.text
    assert "GitHub" not in page.text
    assert 'aria-label="Continuar con Google"' in page.text
    assert 'aria-label="Continuar con Google" disabled' not in page.text
    assert stylesheet.status_code == 200
    assert script.status_code == 200
    assert 'window.location.assign("/")' in script.text
    assert 'googleButton?.addEventListener("click", goToDashboard)' in script.text
    assert "fetch(" not in script.text


@pytest.mark.asyncio
async def test_sign_in_page_is_separate_from_registration() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get("/iniciar-sesion")
        script = await client.get("/js/iniciar-sesion.js")

    assert page.status_code == 200
    assert "Iniciar sesión | Fire Control" in page.text
    assert 'id="login-form"' in page.text
    assert 'type="email"' in page.text
    assert 'type="password"' in page.text
    assert '<a href="/registro">Crear cuenta</a>' in page.text
    assert 'href="/css/registro.css"' in page.text
    assert 'src="/js/iniciar-sesion.js"' in page.text
    assert "<dialog" not in page.text
    assert "GitHub" not in page.text
    assert 'aria-label="Continuar con Google"' in page.text
    assert 'aria-label="Continuar con Google" aria-disabled' not in page.text
    assert script.status_code == 200
    assert 'event.preventDefault()' in script.text
    assert 'window.location.assign("/")' in script.text
    assert 'googleButton?.addEventListener("click", goToDashboard)' in script.text
    assert "fetch(" not in script.text


@pytest.mark.asyncio
async def test_frontend_assets_and_api_routes_coexist() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        stylesheet = await client.get("/css/tokens.css")
        light_stylesheet = await client.get("/css/theme-light.css")
        script = await client.get("/js/app.js")
        dashboard = await client.get("/")
        docs = await client.get("/docs")
        openapi = await client.get("/openapi.json")
        missing_asset = await client.get("/js/missing.js")

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert stylesheet.headers["cache-control"] == "no-store"
    assert light_stylesheet.status_code == 200
    assert 'html[data-theme="light"]' in light_stylesheet.text
    assert dashboard.status_code == 200
    assert 'href="css/theme-light.css?v=20261003-light-theme"' in dashboard.text
    assert 'id="brightness-toggle"' in dashboard.text
    assert 'aria-label="Activar modo claro"' in dashboard.text
    assert script.status_code == 200
    assert script.headers["cache-control"] == "no-store"
    assert 'document.documentElement.dataset.theme' in script.text
    assert '"Activar modo oscuro"' in script.text
    assert 'fetch("/health"' in script.text
    assert 'fetch("/inventory/categories"' in script.text
    assert docs.status_code == 200
    assert "/inventory/categories" in openapi.json()["paths"]
    assert "/inventory/assets" in openapi.json()["paths"]
    assert missing_asset.status_code == 404


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_local_frontend_origin_can_read_api() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for origin in ("http://127.0.0.1:5500", "http://localhost:5500"):
            response = await client.get("/health", headers={"Origin": origin})

            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
            assert "access-control-allow-credentials" not in response.headers


@pytest.mark.asyncio
async def test_other_origins_cannot_read_api_from_browser() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health", headers={"Origin": "http://example.com"}
        )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_local_frontend_can_preflight_categories_get() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/inventory/categories",
            headers={
                "Origin": "http://127.0.0.1:5500",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5500"

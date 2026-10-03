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
    assert 'src="js/app.js"' in response.text


@pytest.mark.asyncio
async def test_frontend_assets_and_api_routes_coexist() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        stylesheet = await client.get("/css/tokens.css")
        script = await client.get("/js/app.js")
        docs = await client.get("/docs")
        openapi = await client.get("/openapi.json")
        missing_asset = await client.get("/js/missing.js")

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
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

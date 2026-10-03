from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.modules.inventory.register_asset.router import router as register_asset_router
from app.modules.inventory.register_category.router import (
    router as register_category_router,
)
from app.shared.errors.application_error import ApplicationError
from app.shared.errors.handlers import (
    application_error_handler,
    unexpected_error_handler,
)

app = FastAPI(
    title="Fire Control",
    version="0.1.0",
)

# Keep the existing loopback CORS allowance for separately hosted local demos.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_methods=["GET"],
    allow_headers=[],
)

app.add_exception_handler(
    ApplicationError,
    application_error_handler
)

app.add_exception_handler(
    Exception,
    unexpected_error_handler
)

app.include_router(register_asset_router)
app.include_router(register_category_router)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/css", StaticFiles(directory=frontend_dir / "css"), name="frontend-css")
app.mount("/js", StaticFiles(directory=frontend_dir / "js"), name="frontend-js")

@app.get("/")
async def root() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

from fastapi import FastAPI

from app.modules.inventory.register_asset.router import router as register_asset_router
from app.shared.errors.application_error import ApplicationError
from app.shared.errors.handlers import (
    application_error_handler,
    unexpected_error_handler,
)

app = FastAPI(
    title="Fire Control",
    version="0.1.0",
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

@app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": "Fire Control API",
        "status": "running",
    }

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
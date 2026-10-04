from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config.settings import get_settings
from app.modules.auth.router import router as auth_router
from app.modules.auth.validations.tokens import (
    ACCESS_TOKEN_COOKIE,
    validate_access_token,
)
from app.modules.inventory.register_asset.router import router as register_asset_router
from app.modules.inventory.register_category.router import (
    router as register_category_router,
)
from app.shared.errors.application_error import ApplicationError
from app.shared.errors.authentication_error import AuthenticationError
from app.shared.errors.handlers import (
    application_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)

app = FastAPI(
    title="Fire Control",
    version="0.1.0",
)


@app.middleware("http")
async def prevent_stale_frontend_assets(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in {"/", "/registro", "/iniciar-sesion"} or path.startswith(
        ("/css/", "/js/", "/auth/")
    ):
        response.headers["Cache-Control"] = "no-store"
    return response


# Keep the existing loopback CORS allowance for separately hosted local demos.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_methods=["GET"],
    allow_headers=[],
)

app.add_exception_handler(ApplicationError, application_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)

app.add_exception_handler(Exception, unexpected_error_handler)

app.include_router(register_asset_router)
app.include_router(register_category_router)
app.include_router(auth_router)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/css", StaticFiles(directory=frontend_dir / "css"), name="frontend-css")
app.mount("/js", StaticFiles(directory=frontend_dir / "js"), name="frontend-js")


@app.get("/", response_model=None)
async def root(request: Request) -> FileResponse | RedirectResponse:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if token is None:
        return RedirectResponse("/iniciar-sesion", status_code=303)
    try:
        validate_access_token(token, get_settings().secret_key)
    except AuthenticationError:
        return RedirectResponse("/iniciar-sesion", status_code=303)
    return FileResponse(frontend_dir / "index.html")


@app.get("/registro", include_in_schema=False)
async def registration_page() -> FileResponse:
    return FileResponse(frontend_dir / "pages" / "registro" / "index.html")


@app.get("/iniciar-sesion", include_in_schema=False)
async def sign_in_page() -> FileResponse:
    return FileResponse(frontend_dir / "pages" / "iniciar-sesion" / "index.html")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.errors.application_error import ApplicationError

logger = logging.getLogger(__name__)


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    fields = []
    for error in exc.errors():
        field = str(error["loc"][-1]) if error["loc"] else "request"
        message = str(error["msg"]).removeprefix("Value error, ")
        fields.append({"field": field, "message": message})
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Revisá los datos ingresados.",
                "details": {"fields": fields},
            }
        },
    )


async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    message = (
        exc.detail
        if isinstance(exc.detail, str)
        else "No se pudo completar la solicitud."
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": message,
                "details": {},
            }
        },
    )


async def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": exc.code, "message": exc.message, "details": exc.details}
        },
    )


async def unexpected_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "Unexpected application error",
        extra={"method": request.method, "path": request.url.path},
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Ocurrió un error inesperado. Intentá nuevamente.",
                "details": {},
            }
        },
    )

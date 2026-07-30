import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.shared.errors.application_error import ApplicationError

logger = logging.getLogger(__name__)


async def application_error_handler(
    request: Request,
    exc: ApplicationError,
)-> JSONResponse:
  return JSONResponse(
    status_code=exc.status_code,
    content={
      "error": {
        "code": exc.code,
        "message": exc.message,
        "details": exc.details
      }
    }
  )


async def unexpected_error_handler(
    request: Request,
    exc: Exception,
)-> JSONResponse:
  logger.exception(
    "Unexpected application error",
    extra={
      "method": request.method,
      "path": request.url.path
    }
  )

  return JSONResponse(
    status_code=500,
    content={
      "error": {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "An unexpected error ocurred",
        "details": {},
      }
    }
  )
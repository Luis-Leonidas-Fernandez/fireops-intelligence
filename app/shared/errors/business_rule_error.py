from typing import Any

from app.shared.errors.application_error import ApplicationError


class BusinessRuleError(ApplicationError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=422,
            details=details,
        )

from app.shared.errors.application_error import ApplicationError


class AuthorizationError(ApplicationError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=403)

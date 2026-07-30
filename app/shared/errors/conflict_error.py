from typing import Any

from app.shared.errors.application_error import ApplicationError


class ConflictError(ApplicationError):
  def __init__(
      self, 
      *, 
      code: str, 
      message: str, 
      details: dict[str, Any] | None = None,
      )-> None:
    super().__init__(
      code=code, 
      message=message,
      status_code= 409,  
      details=details
      )
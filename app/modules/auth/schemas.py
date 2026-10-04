from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.auth.validations.credentials import (
    normalize_email,
    validate_registration_password,
)


class CredentialsRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return normalize_email(value)


class RegisterRequest(CredentialsRequest):
    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return validate_registration_password(value)


class LoginRequest(CredentialsRequest):
    pass


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str


class AuthResponse(BaseModel):
    message: str
    user: UserResponse

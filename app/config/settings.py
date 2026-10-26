import base64
import os
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Este archivo sirve para leer las variables del archivo .env
# lru_cache sirve para guardar el resultado de una función, La primera vez que llamamos a get_settings(), lee la configuración.
# Las siguientes veces, reutiliza la misma configuración sin volver a leer todo.
class Settings(BaseSettings):
    app_name: str = "FireOps Intelligence"
    environment: str = "development"
    database_url: str
    secret_key: str = Field(min_length=32, repr=False)
    google_client_id: str | None = None
    google_client_secret: str | None = Field(default=None, repr=False)
    google_redirect_uri: str | None = None
    gmail_sender_email: str | None = None
    gmail_refresh_token: str | None = Field(default=None, repr=False)
    registration_admin_email: str | None = None
    registration_reviewer_google_sub: str | None = Field(default=None, repr=False)
    public_base_url: str | None = None
    readiness_timeout_seconds: float = 2.0
    check_migration_readiness: bool = True
    rate_limit_enabled: bool = True
    rate_limit_backend: str = "memory"
    rate_limit_redis_url: str | None = None
    rate_limit_hmac_key: str | None = Field(default=None, repr=False)
    trusted_proxies: str = "127.0.0.1,::1"
    argon2_max_running: int = 2
    argon2_max_waiting: int = 8
    argon2_queue_timeout: float = 0.50
    admin_rate_limit_list_requests: int = 30
    admin_rate_limit_review_requests: int = 20
    admin_rate_limit_reissue_requests: int = 20
    outbox_encryption_key: str | None = Field(default=None, repr=False)
    outbox_encryption_key_id: str = "v1"
    outbox_secondary_encryption_keys: str | None = Field(default=None, repr=False)
    outbox_enabled: bool = False

    @model_validator(mode="after")
    def validate_outbox_configuration(self) -> "Settings":
        if self.outbox_enabled:
            if not self.outbox_encryption_key:
                raise ValueError(
                    "outbox_encryption_key must be configured when outbox_enabled is True"
                )
            try:
                raw_bytes = base64.b64decode(self.outbox_encryption_key, validate=True)
                if len(raw_bytes) != 32:
                    raise ValueError(
                        f"outbox_encryption_key must be exactly 32 bytes, got {len(raw_bytes)}"
                    )
            except Exception as e:
                raise ValueError(f"Invalid outbox_encryption_key: {e}") from e
        return self

    @property
    def trusted_proxies_list(self) -> list[str]:
        return [p.strip() for p in self.trusted_proxies.split(",") if p.strip()]

    @property
    def gmail_invitation_enabled(self) -> bool:
        return all(
            (
                self.google_client_id,
                self.google_client_secret,
                self.google_redirect_uri,
                self.gmail_sender_email,
                self.gmail_refresh_token,
            )
        )

    @property
    def google_oauth_enabled(self) -> bool:
        return all(
            (self.google_client_id, self.google_client_secret, self.google_redirect_uri)
        )

    model_config = SettingsConfigDict(
        # Lee .env por defecto o el archivo indicado por ENV_FILE.
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Funcion para obtener todas las configuraciones actuales
@lru_cache
def get_settings() -> Settings:
    # BaseSettings fills required values from the selected environment file.
    return Settings()  # type: ignore[call-arg]

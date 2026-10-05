import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


#Este archivo sirve para leer las variables del archivo .env
#lru_cache sirve para guardar el resultado de una función, La primera vez que llamamos a get_settings(), lee la configuración.
#Las siguientes veces, reutiliza la misma configuración sin volver a leer todo.
class Settings(BaseSettings):
    app_name: str = "FireOps Intelligence"
    environment: str = "development"
    database_url: str
    secret_key: str = Field(min_length=32, repr=False)
    google_client_id: str | None = None
    google_client_secret: str | None = Field(default=None, repr=False)
    google_redirect_uri: str | None = None

    @property
    def google_oauth_enabled(self) -> bool:
        return all((self.google_client_id, self.google_client_secret, self.google_redirect_uri))

    model_config = SettingsConfigDict(
        # Lee .env por defecto o el archivo indicado por ENV_FILE.
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

#Funcion para obtener todas las configuraciones actuales
@lru_cache
def get_settings() -> Settings:
    # BaseSettings fills required values from the selected environment file.
    return Settings()  # type: ignore[call-arg]

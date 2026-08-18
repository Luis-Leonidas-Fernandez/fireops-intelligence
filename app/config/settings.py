from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


#Este archivo sirve para leer las variables del archivo .env
#lru_cache sirve para guardar el resultado de una función, La primera vez que llamamos a get_settings(), lee la configuración.
#Las siguientes veces, reutiliza la misma configuración sin volver a leer todo.
class Settings(BaseSettings):
    app_name: str = "FireOps Intelligence"
    environment: str = "development"
    database_url: str
    secret_key: str

    model_config = SettingsConfigDict(
        #busca el archivo .env
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

#Funcion para obtener todas las configuraciones actuales
@lru_cache
def get_settings() -> Settings:
    return Settings()
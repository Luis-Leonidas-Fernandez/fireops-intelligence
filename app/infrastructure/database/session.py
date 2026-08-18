from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import get_settings

#obtiene las configuraciones de .env
settings = get_settings()

#Esto crea el motor de base de datos
engine = create_async_engine(
    settings.database_url,
    #permite mostrar las consultas sql en terminal
    echo=settings.environment == "development",
)

#crea una fabrica de sesiones no crea la sesion es el objeto que ayuda a crearla
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    #las sesiones seran sesiones async
    class_=AsyncSession,
    expire_on_commit=False,
)

#Esta funcion va a ser usada por FastApi para darle una session a los endpoints
async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
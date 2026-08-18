from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


#Sirve para decir:
#Las clases que hereden de mí van a representar tablas.
class Base(AsyncAttrs, DeclarativeBase):
    pass
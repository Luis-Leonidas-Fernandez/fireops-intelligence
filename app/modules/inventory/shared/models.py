from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class Category(Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    assets: Mapped[list["Asset"]] = relationship(back_populates="category")


class Asset(Base):
    __tablename__ = "bienes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    codigo_interno: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("categorias.id"),
        nullable=False,
    )
    ubicacion_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "ubicaciones.id",
            name="fk_bienes_ubicacion_id_ubicaciones",
            ondelete="SET NULL",
            use_alter=True,
        ),
        index=True,
        nullable=True,
    )
    category: Mapped[Category] = relationship(back_populates="assets")
    location: Mapped["Location | None"] = relationship(
        back_populates="assets",
        foreign_keys=[ubicacion_id],
    )
    container_location: Mapped["Location | None"] = relationship(
        back_populates="container_asset",
        foreign_keys="Location.bien_contenedor_id",
        uselist=False,
    )
    movements: Mapped[list["Movement"]] = relationship(back_populates="asset")


class Location(Base):
    __tablename__ = "ubicaciones"
    __table_args__ = (
        CheckConstraint(
            "tipo_ubicacion IN ('FISICA', 'VEHICULO')",
            name="ck_ubicaciones_tipo_ubicacion",
        ),
        CheckConstraint(
            "(tipo_ubicacion = 'FISICA' AND bien_contenedor_id IS NULL) OR "
            "(tipo_ubicacion = 'VEHICULO' AND bien_contenedor_id IS NOT NULL)",
            name="ck_ubicaciones_contenedor_por_tipo",
        ),
        Index(
            "uq_ubicaciones_bien_contenedor_id",
            "bien_contenedor_id",
            unique=True,
            postgresql_where=text("bien_contenedor_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bien_contenedor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("bienes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    tipo_ubicacion: Mapped[str] = mapped_column(String(20), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    activa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    container_asset: Mapped[Asset | None] = relationship(
        back_populates="container_location",
        foreign_keys=[bien_contenedor_id],
    )
    assets: Mapped[list[Asset]] = relationship(
        back_populates="location",
        foreign_keys=[Asset.ubicacion_id],
    )
    outgoing_movements: Mapped[list["Movement"]] = relationship(
        back_populates="origin_location",
        foreign_keys="Movement.ubicacion_origen_id",
    )
    incoming_movements: Mapped[list["Movement"]] = relationship(
        back_populates="destination_location",
        foreign_keys="Movement.ubicacion_destino_id",
    )


class Movement(Base):
    __tablename__ = "movimientos"
    __table_args__ = (
        CheckConstraint(
            "tipo_movimiento IN ('ALTA', 'BAJA_TOTAL', 'BAJA_PARCIAL', "
            "'TRASLADO', 'ASIGNACION', 'DESASIGNACION', 'CAMBIO_ESTADO', "
            "'AJUSTE_CANTIDAD', 'RESTAURACION', 'CORRECCION')",
            name="ck_movimientos_tipo_movimiento",
        ),
        CheckConstraint(
            "tipo_movimiento <> 'TRASLADO' OR "
            "(ubicacion_destino_id IS NOT NULL AND "
            "ubicacion_origen_id IS DISTINCT FROM ubicacion_destino_id)",
            name="ck_movimientos_traslado_destino",
        ),
        Index("ix_movimientos_bien_id_fecha", "bien_id", "fecha", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bien_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bienes.id", ondelete="RESTRICT"), nullable=False
    )
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    tipo_movimiento: Mapped[str] = mapped_column(String(30), nullable=False)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    cantidad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ubicacion_origen_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ubicaciones.id", ondelete="RESTRICT"), nullable=True
    )
    ubicacion_destino_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ubicaciones.id", ondelete="RESTRICT"), nullable=True
    )
    estado_origen: Mapped[str | None] = mapped_column(String(30), nullable=True)
    estado_destino: Mapped[str | None] = mapped_column(String(30), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="movements")
    origin_location: Mapped[Location | None] = relationship(
        back_populates="outgoing_movements",
        foreign_keys=[ubicacion_origen_id],
    )
    destination_location: Mapped[Location | None] = relationship(
        back_populates="incoming_movements",
        foreign_keys=[ubicacion_destino_id],
    )


class AuditChange(Base):
    __tablename__ = "auditoria_cambios"
    __table_args__ = (
        CheckConstraint(
            "entidad_tipo IN ('BIEN', 'MOVIMIENTO', 'USUARIO', 'UBICACION', "
            "'CATEGORIA', 'OTRO')",
            name="ck_auditoria_cambios_entidad_tipo",
        ),
        CheckConstraint(
            "accion IN ('ALTA', 'MODIFICACION', 'CORRECCION', "
            "'ELIMINACION_LOGICA', 'ELIMINACION_FISICA', 'RESTAURACION')",
            name="ck_auditoria_cambios_accion",
        ),
        Index("ix_auditoria_cambios_entidad", "entidad_tipo", "entidad_id"),
        Index("ix_auditoria_cambios_operacion_id", "operacion_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operacion_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    entidad_tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    entidad_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    accion: Mapped[str] = mapped_column(String(30), nullable=False)
    datos_anteriores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    datos_nuevos: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    realizado_por_usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

"""Toma de inventario: el recuento físico de un depósito.

Es un expediente con estado y no un ajuste suelto porque contar un depósito
lleva horas: hace falta un borrador que sobreviva a que se cierre el navegador,
y hace falta la foto de lo que el sistema creía tener al abrir el conteo, que es
lo único que después permite distinguir una diferencia de inventario de una
venta ocurrida mientras se contaba.
"""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TomaInventario(Base):
    __tablename__ = "tomas_inventario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    deposito_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("depositos.id"), nullable=False, index=True
    )
    # borrador (se está contando) | aplicada (ya movió stock) | anulada
    estado: Mapped[str] = mapped_column(
        String(20), default="borrador", server_default="borrador", nullable=False, index=True
    )
    # manual (se contó en pantalla) | import (entró por planilla)
    origen: Mapped[str] = mapped_column(
        String(20), default="manual", server_default="manual", nullable=False
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_por_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    aplicado_por_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    aplicada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    deposito = relationship("Deposito", lazy="selectin")
    creado_por = relationship("User", foreign_keys=[creado_por_id], lazy="selectin")
    aplicado_por = relationship("User", foreign_keys=[aplicado_por_id], lazy="selectin")
    # `noload`: una toma tiene miles de líneas y se piden paginadas aparte.
    items = relationship(
        "TomaInventarioItem",
        back_populates="toma",
        lazy="noload",
        cascade="all, delete-orphan",
    )


class TomaInventarioItem(Base):
    __tablename__ = "toma_inventario_items"
    __table_args__ = (
        UniqueConstraint("toma_id", "producto_id", name="uq_toma_producto"),
        CheckConstraint(
            "(contado_cajas IS NULL OR contado_cajas >= 0) AND "
            "(contado_blisters IS NULL OR contado_blisters >= 0)",
            name="ck_toma_contado_no_negativo",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    toma_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tomas_inventario.id", ondelete="CASCADE"), nullable=False, index=True
    )
    producto_id: Mapped[int] = mapped_column(Integer, ForeignKey("productos.id"), nullable=False)

    # Foto de lo que el sistema tenía al abrir la toma. No es cache: es contra
    # esto que se detecta que un producto se movió durante el conteo.
    esperado_cajas: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    esperado_blisters: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    # NULL = todavía no se contó. Cero es un conteo válido ("no hay ninguno").
    contado_cajas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contado_blisters: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Diferencia efectivamente aplicada, congelada al aplicar la toma.
    aplicado_delta_blisters: Mapped[int | None] = mapped_column(Integer, nullable=True)

    contado_por_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    contado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    toma = relationship("TomaInventario", back_populates="items")
    producto = relationship("Producto", lazy="selectin")

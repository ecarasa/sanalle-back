from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class IngresoMercaderia(Base):
    __tablename__ = "ingresos_mercaderia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    proveedor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("proveedores.id"), nullable=True
    )
    numero_comprobante: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    destino: Mapped[str] = mapped_column(String(1), default="A", server_default="A", nullable=False)
    creado_por_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # Subtotal de los renglones (sin impuestos). importe_total = subtotal_neto + impuestos.
    subtotal_neto: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    importe_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    saldo_pendiente: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    fecha_vencimiento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dias_plazo: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sociedad: Mapped[str] = mapped_column(String(20), default="Sanalle", server_default="Sanalle", nullable=False)
    archivo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    proveedor: Mapped["Proveedor | None"] = relationship("Proveedor", lazy="noload")  # noqa: F821
    creado_por: Mapped["User"] = relationship("User", lazy="noload")  # noqa: F821
    items: Mapped[list["IngresoMercaderiaItem"]] = relationship(
        "IngresoMercaderiaItem", back_populates="ingreso", lazy="noload", cascade="all, delete-orphan"
    )
    impuestos: Mapped[list["IngresoImpuesto"]] = relationship(
        "IngresoImpuesto", back_populates="ingreso", lazy="noload", cascade="all, delete-orphan"
    )
    imputaciones: Mapped[list["PagoProveedorImputacion"]] = relationship(  # noqa: F821
        "PagoProveedorImputacion", back_populates="ingreso", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<IngresoMercaderia(id={self.id}, numero={self.numero!r})>"


class IngresoMercaderiaItem(Base):
    __tablename__ = "ingreso_mercaderia_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ingreso_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ingresos_mercaderia.id", ondelete="CASCADE"), nullable=False, index=True
    )
    producto_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("productos.id"), nullable=False
    )
    cantidad_cajas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cantidad_blisters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    costo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Relationships
    ingreso: Mapped["IngresoMercaderia"] = relationship(
        "IngresoMercaderia", back_populates="items", lazy="noload"
    )
    producto: Mapped["Producto"] = relationship("Producto", lazy="noload")  # noqa: F821

    def __repr__(self) -> str:
        return f"<IngresoMercaderiaItem(id={self.id}, ingreso_id={self.ingreso_id}, producto_id={self.producto_id})>"


class IngresoImpuesto(Base):
    """Línea de impuesto/percepción de cabecera de un ingreso (IVA 21, IVA 10.5, Perc. IIBB…)."""
    __tablename__ = "ingreso_impuestos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ingreso_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ingresos_mercaderia.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo_iva_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tipo_iva.id"), nullable=True
    )
    concepto: Mapped[str] = mapped_column(String(100), nullable=False)
    base: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    tasa: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default="0", nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)

    ingreso: Mapped["IngresoMercaderia"] = relationship(
        "IngresoMercaderia", back_populates="impuestos", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<IngresoImpuesto(id={self.id}, concepto={self.concepto!r}, importe={self.importe})>"

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.pago import TipoCuenta


class TipoNota(enum.Enum):
    credito = "credito"
    debito = "debito"


class NotaCreditoDebito(Base):
    __tablename__ = "notas_credito_debito"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    tipo: Mapped[TipoNota] = mapped_column(
        Enum(TipoNota, name="tiponota", native_enum=True), nullable=False, index=True
    )
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id"), nullable=False, index=True
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    importe_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    pedido_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pedidos.id"), nullable=True
    )
    tipo_cuenta: Mapped[TipoCuenta] = mapped_column(
        Enum(TipoCuenta, name="tipocuenta", native_enum=True),
        default=TipoCuenta.remito,
        server_default="remito",
        nullable=False,
        index=True,
    )
    creado_por_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    afecta_stock: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    stock_tipo: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # "A" o "B"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="noload")  # noqa: F821
    pedido: Mapped["Pedido | None"] = relationship("Pedido", lazy="noload")  # noqa: F821
    creado_por: Mapped["User"] = relationship("User", lazy="noload")  # noqa: F821
    items: Mapped[list["NotaCreditoItem"]] = relationship(
        "NotaCreditoItem", back_populates="nota", lazy="noload", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<NotaCreditoDebito(id={self.id}, numero={self.numero!r}, tipo={self.tipo.value})>"


class NotaCreditoItem(Base):
    __tablename__ = "nota_credito_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nota_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notas_credito_debito.id", ondelete="CASCADE"), nullable=False, index=True
    )
    producto_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("productos.id"), nullable=True
    )
    descripcion: Mapped[str] = mapped_column(String(500), nullable=False)
    cantidad_cajas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cantidad_blisters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Unidad de venta original de la línea del pedido ('caja' | 'blister').
    unidad_venta: Mapped[str] = mapped_column(String(20), default="caja", server_default="caja", nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    precio_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    # Relationships
    nota: Mapped["NotaCreditoDebito"] = relationship(
        "NotaCreditoDebito", back_populates="items", lazy="noload"
    )
    producto: Mapped["Producto | None"] = relationship("Producto", lazy="noload")  # noqa: F821

    def __repr__(self) -> str:
        return f"<NotaCreditoItem(id={self.id}, nota_id={self.nota_id})>"

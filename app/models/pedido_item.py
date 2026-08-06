from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PedidoItem(Base):
    __tablename__ = "pedido_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pedidos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    producto_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("productos.id"), nullable=False, index=True
    )
    cantidad_cajas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cantidad_blisters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    precio_lista: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    descuento_porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    precio_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    pedido: Mapped["Pedido"] = relationship(  # noqa: F821
        "Pedido", back_populates="items", lazy="noload"
    )
    producto: Mapped["Producto"] = relationship(  # noqa: F821
        "Producto", lazy="noload"
    )
    comision_vendedor: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0", nullable=False)

    @property
    def cantidad(self) -> int:
        """Alias for cantidad_cajas to maintain compatibility with older code."""
        return self.cantidad_cajas

    def __repr__(self) -> str:
        return f"<PedidoItem(id={self.id}, pedido_id={self.pedido_id}, producto_id={self.producto_id}, cajas={self.cantidad_cajas}, blisters={self.cantidad_blisters})>"

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StockProductoDeposito(Base):
    """Stock de un producto en un depósito (reemplaza las columnas fijas A/B)."""

    __tablename__ = "stock_producto_deposito"
    __table_args__ = (
        UniqueConstraint("producto_id", "deposito_id", name="uq_stock_prod_dep"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("productos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deposito_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("depositos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cajas: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    blisters: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    deposito = relationship("Deposito", lazy="selectin")

    def __repr__(self) -> str:
        return f"<StockProductoDeposito(prod={self.producto_id}, dep={self.deposito_id}, cajas={self.cajas})>"

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, func, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class HistorialPvpProducto(Base):
    __tablename__ = "historial_pvp_producto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(Integer, ForeignKey("productos.id"), nullable=False)
    pvp_anterior: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    pvp_nuevo: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fecha_cambio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    producto: Mapped["Producto"] = relationship("Producto", back_populates="historial_pvp")

    def __repr__(self) -> str:
        return f"<HistorialPvpProducto(id={self.id}, producto_id={self.producto_id}, pvp_nuevo={self.pvp_nuevo})>"

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MovimientoStock(Base):
    __tablename__ = "movimientos_stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    usuario_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    tipo_operacion: Mapped[str] = mapped_column(String(50), nullable=False)  # TRANSFER, FRACTION, ADJUST
    origen: Mapped[str | None] = mapped_column(String(20), nullable=True)     # STOCK_A, STOCK_B, NONE
    destino: Mapped[str | None] = mapped_column(String(20), nullable=True)    # STOCK_A, STOCK_B, NONE
    
    cantidad_cajas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cantidad_blisters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    observacion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    producto = relationship("Producto")
    usuario = relationship("User")

    def __repr__(self) -> str:
        return f"<MovimientoStock(id={self.id}, tipo={self.tipo_operacion}, producto_id={self.producto_id})>"

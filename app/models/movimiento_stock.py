from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MovimientoStock(Base):
    __tablename__ = "movimientos_stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    usuario_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # ADJUST (ajuste manual), TRANSFER (entre depósitos), INGRESO,
    # NC_RETURN / ND_ADJUST (notas), VENTA / VENTA_REVERSA (pedidos).
    tipo_operacion: Mapped[str] = mapped_column(String(50), nullable=False)
    # Depósito del que sale la mercadería (NULL cuando entra de la nada: ingreso, NC).
    deposito_origen_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("depositos.id"), nullable=True, index=True
    )
    # Depósito al que entra (NULL cuando sale del circuito: venta entregada, ND).
    deposito_destino_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("depositos.id"), nullable=True, index=True
    )
    
    cantidad_cajas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cantidad_blisters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    observacion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    producto = relationship("Producto")
    usuario = relationship("User")
    deposito_origen = relationship("Deposito", foreign_keys=[deposito_origen_id], lazy="selectin")
    deposito_destino = relationship("Deposito", foreign_keys=[deposito_destino_id], lazy="selectin")

    def __repr__(self) -> str:
        return f"<MovimientoStock(id={self.id}, tipo={self.tipo_operacion}, producto_id={self.producto_id})>"

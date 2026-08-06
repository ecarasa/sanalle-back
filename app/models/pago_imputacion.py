from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PagoImputacion(Base):
    __tablename__ = "pago_imputaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pago_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pagos.id"), nullable=False, index=True
    )
    pedido_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pedidos.id"), nullable=False, index=True
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    pago: Mapped["Pago"] = relationship(  # noqa: F821
        "Pago", back_populates="imputaciones", lazy="noload"
    )
    pedido: Mapped["Pedido"] = relationship(  # noqa: F821
        "Pedido", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<PagoImputacion(id={self.id}, pago_id={self.pago_id}, pedido_id={self.pedido_id}, monto={self.monto})>"

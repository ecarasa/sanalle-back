from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CashbackProveedor(Base):
    """Acumulador de cashback de un proveedor.

    Cada pago con cashback genera una fila 'pendiente'. Cuando se pide la nota de
    crédito, se suman todas las pendientes en UNA sola NotaProveedor(credito) y quedan
    'acreditado' ligadas a esa nota. (Operatoria del proveedor Savant.)
    """
    __tablename__ = "cashback_proveedor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proveedor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("proveedores.id"), nullable=False, index=True
    )
    pago_proveedor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pagos_proveedor.id", ondelete="SET NULL"), nullable=True, index=True
    )
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), default="pendiente", server_default="pendiente", nullable=False, index=True
    )
    nota_proveedor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("notas_proveedor.id"), nullable=True
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    proveedor: Mapped["Proveedor"] = relationship("Proveedor", lazy="noload")  # noqa: F821

    def __repr__(self) -> str:
        return f"<CashbackProveedor(id={self.id}, proveedor_id={self.proveedor_id}, importe={self.importe}, estado={self.estado})>"

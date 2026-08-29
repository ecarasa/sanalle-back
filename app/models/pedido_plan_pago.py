from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PedidoPlanPago(Base):
    """Cómo se va a cobrar un pedido: forma de pago, cuenta destino e importe.

    Es INFORMATIVO. No crea `Pago`, no imputa, no toca `saldo_pendiente` ni el
    ledger: es la instrucción para cobranza, no el cobro. El cobro real sigue
    entrando por Pagos, que es lo único que mueve plata.

    Una fila por tramo, así el mismo pedido puede repartirse: "transferencia a
    la cuenta Galicia $500.000" + "efectivo en caja $200.000". Eso cubre tanto
    la condición de pago múltiple como el pago derivado a varias cuentas, porque
    son la misma cosa mirada de dos lados.
    """

    __tablename__ = "pedido_plan_pago"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pedidos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Forma de pago. Texto libre alimentado por `entidades` con
    # categoria='condicion_pago', igual que el resto de los combos paramétricos.
    forma: Mapped[str] = mapped_column(String(40), nullable=False)
    # Cuenta de la empresa a la que entra este tramo. Nullable porque no siempre
    # se sabe de antemano (efectivo que todavía no se depositó, por ejemplo).
    cuenta_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cuentas.id"), nullable=True, index=True
    )
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pedido: Mapped["Pedido"] = relationship(  # noqa: F821
        "Pedido", back_populates="plan_pago", lazy="noload"
    )
    cuenta: Mapped["Cuenta | None"] = relationship(  # noqa: F821
        "Cuenta", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<PedidoPlanPago(pedido_id={self.pedido_id}, forma={self.forma!r}, importe={self.importe})>"

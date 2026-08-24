from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StockProductoDeposito(Base):
    """Stock de un producto en un depósito. Única fuente de verdad del stock.

    Las cantidades se guardan desnormalizadas en cajas + blísters sueltos, pero
    toda la aritmética se hace en blísters (la unidad más chica) y se re-normaliza
    al final, así fraccionar una caja para vender blísters no pierde nada.

    `reservado_*` es la parte del stock que ya está comprometida en un pedido
    creado pero todavía no entregado. El stock físico (`cajas`/`blisters`) ya no
    la incluye: al crear el pedido se descuenta de físico y se suma a reservado,
    y al entregar simplemente se libera la reserva.
    """

    __tablename__ = "stock_producto_deposito"
    __table_args__ = (
        UniqueConstraint("producto_id", "deposito_id", name="uq_stock_prod_dep"),
        CheckConstraint("cajas >= 0 AND blisters >= 0", name="ck_stock_no_negativo"),
        CheckConstraint(
            "reservado_cajas >= 0 AND reservado_blisters >= 0",
            name="ck_reservado_no_negativo",
        ),
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
    reservado_cajas: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    reservado_blisters: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    deposito = relationship("Deposito", lazy="selectin")

    # --- Aritmética en blísters -------------------------------------------------
    # `por_caja` viene siempre del producto (blisters_por_caja, mínimo 1). No se
    # cachea acá para que un cambio de presentación no deje filas inconsistentes.

    def total_blisters(self, por_caja: int) -> int:
        """Stock físico disponible, expresado en blísters."""
        return self.cajas * por_caja + self.blisters

    def total_reservado_blisters(self, por_caja: int) -> int:
        """Stock comprometido en pedidos no entregados, en blísters."""
        return self.reservado_cajas * por_caja + self.reservado_blisters

    def set_total_blisters(self, total: int, por_caja: int) -> None:
        self.cajas = total // por_caja
        self.blisters = total % por_caja

    def set_total_reservado_blisters(self, total: int, por_caja: int) -> None:
        self.reservado_cajas = total // por_caja
        self.reservado_blisters = total % por_caja

    def __repr__(self) -> str:
        return (
            f"<StockProductoDeposito(prod={self.producto_id}, dep={self.deposito_id}, "
            f"cajas={self.cajas}, blisters={self.blisters})>"
        )

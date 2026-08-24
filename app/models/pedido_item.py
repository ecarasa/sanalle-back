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
    # Depósito del que sale esta línea. Es lo que le dice a depósito de qué
    # góndola pickear, y contra qué fila de stock se reservó/descontó.
    # Nullable solo por los pedidos anteriores a los depósitos por línea.
    deposito_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("depositos.id"), nullable=True, index=True
    )
    cantidad_cajas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cantidad_blisters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Unidad en la que se vendió la línea: 'caja' | 'blister'.
    # Define la base del precio y en qué unidad se descuenta el stock.
    unidad_venta: Mapped[str] = mapped_column(String(20), default="caja", server_default="caja", nullable=False)
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
    deposito: Mapped["Deposito | None"] = relationship(  # noqa: F821
        "Deposito", lazy="selectin"
    )
    comision_vendedor: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0", nullable=False)

    @property
    def cantidad(self) -> int:
        """Alias for cantidad_cajas to maintain compatibility with older code."""
        return self.cantidad_cajas

    @property
    def cantidad_venta(self) -> int:
        """Cantidad expresada en la UNIDAD DE VENTA de la línea.

        Para líneas por blíster devuelve `cantidad_blisters` (cantidad_cajas es 0);
        para caja devuelve `cantidad_cajas`. Es la cantidad "real" a mostrar en
        respuestas de API, PDF, reportes y hoja de ruta.
        """
        if self.unidad_venta == "blister":
            return self.cantidad_blisters
        return self.cantidad_cajas

    @property
    def unidad_label(self) -> str:
        """Etiqueta corta de la unidad para textos/PDF."""
        return "blíster" if self.unidad_venta == "blister" else "caja"

    def __repr__(self) -> str:
        return f"<PedidoItem(id={self.id}, pedido_id={self.pedido_id}, producto_id={self.producto_id}, cajas={self.cantidad_cajas}, blisters={self.cantidad_blisters})>"

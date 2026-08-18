import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.pago import TipoPago


class TipoMovimiento(enum.Enum):
    ingreso = "ingreso"
    egreso = "egreso"


class CategoriaMovimiento(enum.Enum):
    cobro_cliente = "cobro_cliente"
    pago_proveedor = "pago_proveedor"
    gasto_general = "gasto_general"
    sueldo = "sueldo"
    impuesto = "impuesto"
    ajuste = "ajuste"
    ingreso_extraordinario = "ingreso_extraordinario"
    transferencia_recibida = "transferencia_recibida"
    cheque_recibido = "cheque_recibido"
    compra_mercaderia = "compra_mercaderia"
    # Pasamanos: plata de un cliente que entra sólo para salir a un proveedor.
    # No es caja propia; se excluye de los totales reales de ingresos/egresos.
    transito = "transito"
    otro = "otro"


class CuentaSanalle(Base):
    __tablename__ = "cuenta_sanalle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    tipo: Mapped[TipoMovimiento] = mapped_column(
        Enum(TipoMovimiento, name="tipomovimiento", native_enum=True),
        nullable=False,
        index=True,
    )
    categoria: Mapped[CategoriaMovimiento] = mapped_column(
        Enum(CategoriaMovimiento, name="categoriamovimiento", native_enum=True),
        nullable=False,
        index=True,
    )
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    metodo_pago: Mapped[TipoPago] = mapped_column(
        Enum(TipoPago, name="tipopago", native_enum=True),
        nullable=False,
        index=True,
    )
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    referencia_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    usuario: Mapped["User"] = relationship("User", lazy="noload")  # noqa: F821

    def __repr__(self) -> str:
        return f"<CuentaSanalle(id={self.id}, tipo={self.tipo.value}, categoria={self.categoria.value}, importe={self.importe})>"

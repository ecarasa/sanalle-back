import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.pago import TipoCuenta


class TipoNota(enum.Enum):
    credito = "credito"
    debito = "debito"


class NotaProveedor(Base):
    __tablename__ = "notas_proveedor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    tipo: Mapped[TipoNota] = mapped_column(
        Enum(TipoNota, name="tiponota", native_enum=True), nullable=False, index=True
    )
    proveedor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("proveedores.id"), nullable=False, index=True
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    importe_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    creado_por_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    proveedor: Mapped["Proveedor"] = relationship("Proveedor", lazy="noload")  # noqa: F821
  

    def __repr__(self) -> str:
        return f"<NotaCreditoDebito(id={self.id}, numero={self.numero!r}, tipo={self.tipo.value})>"


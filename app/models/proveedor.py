from sqlalchemy import Integer, String, Numeric, Boolean, DateTime, func, Enum
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base
import enum

class TipoProveedor(enum.Enum):
    LABORATORIO = "LABORATORIO"
    DROGUERIA = "DROGUERIA"


class Proveedor(Base):
    __tablename__ = "proveedores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False, index=True, unique=True)
    telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)
    direccion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    deuda_inicial: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    saldo_remito: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    saldo_factura: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    

    tipo: Mapped[TipoProveedor] = mapped_column(Enum(TipoProveedor), nullable=False, default=TipoProveedor.LABORATORIO)
    plazo_pago: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    descuento: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    cashback: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    contacto_nombre: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contacto_telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contacto_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

   
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Proveedor(id={self.id}, nombre={self.nombre!r})>"

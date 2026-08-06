import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TipoPago(enum.Enum):
    efectivo = "efectivo"
    cheque = "cheque"
    transferencia = "transferencia"
    retencion = "retencion"


class EstadoPago(enum.Enum):
    pendiente = "pendiente"
    recibido = "recibido"
    imputado = "imputado"
    imputado_parcial = "imputado_parcial"
    acreditado = "acreditado"
    rechazado = "rechazado"


class TipoCuenta(enum.Enum):
    remito = "remito"
    factura = "factura"


class Pago(Base):
    __tablename__ = "pagos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id"), nullable=False, index=True
    )
    receptor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    tipo_pago: Mapped[TipoPago] = mapped_column(
        Enum(TipoPago, name="tipopago", native_enum=True),
        nullable=False,
        index=True,
    )
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    saldo_restante: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fecha_recepcion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    estado: Mapped[EstadoPago] = mapped_column(
        Enum(EstadoPago, name="estadopagopago", native_enum=True),
        default=EstadoPago.recibido,
        server_default="recibido",
        nullable=False,
        index=True,
    )
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    recibo_pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    numero_recibo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    tipo_cuenta: Mapped[TipoCuenta] = mapped_column(
        Enum(TipoCuenta, name="tipocuenta", native_enum=True),
        default=TipoCuenta.remito,
        server_default="remito",
        nullable=False,
        index=True,
    )

    # DB-06: FK to bancos table
    banco_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bancos.id"), nullable=True, index=True
    )

    # Cheque-specific fields
    ch_numero: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ch_banco: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ch_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    ch_vto: Mapped[date | None] = mapped_column(Date, nullable=True)

    # DB-07: Retencion-specific fields
    retencion_tipo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retencion_numero: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retencion_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)

    # DB-07: Transferencia-specific fields
    transferencia_numero: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transferencia_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    transferencia_cuenta_origen: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Group receipt
    grupo_recibo_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    cliente: Mapped["Cliente"] = relationship(  # noqa: F821
        "Cliente", back_populates="pagos", lazy="noload"
    )
    receptor: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="pagos_recibidos", lazy="noload"
    )
    banco: Mapped["Banco"] = relationship(  # noqa: F821
        "Banco", lazy="noload"
    )
    imputaciones: Mapped[list["PagoImputacion"]] = relationship(  # noqa: F821
        "PagoImputacion", back_populates="pago", lazy="noload"
    )
    pagos_proveedor: Mapped[list["PagoProveedor"]] = relationship(  # noqa: F821
        "PagoProveedor", back_populates="pago", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Pago(id={self.id}, recibo={self.numero_recibo!r}, tipo={self.tipo_pago.value}, importe={self.importe})>"

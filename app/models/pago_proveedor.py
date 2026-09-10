from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.pago import TipoPago, TipoCuenta


class PagoProveedor(Base):
    __tablename__ = "pagos_proveedor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proveedor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("proveedores.id"), nullable=False, index=True
    )
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    pago_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pagos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Cuenta de dinero de la empresa desde la que sale este pago.
    cuenta_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cuentas.id"), nullable=True, index=True
    )
    # Cuenta del PROVEEDOR a la que se transfirió. Es el otro extremo del giro y
    # es lo que permite contestar "¿a qué CBU le pagamos esta factura?".
    # `SET NULL` y no `CASCADE`: si mañana se borra la cuenta de la libreta, el
    # pago tiene que sobrevivir — es un hecho contable, no un dato de la libreta.
    proveedor_cuenta_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("proveedor_cuentas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fecha_pago: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    tipo_pago: Mapped[TipoPago] = mapped_column(
        Enum(TipoPago, name="tipopago", native_enum=True),
        nullable=False,
        index=True,
    )
    tipo_cuenta: Mapped[TipoCuenta] = mapped_column(
        Enum(TipoCuenta, name="tipocuenta", native_enum=True),
        default=TipoCuenta.remito,
        server_default="remito",
        nullable=False,
        index=True,
    )
    referencia_pago: Mapped[str | None] = mapped_column(String(100), nullable=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    proveedor: Mapped["Proveedor"] = relationship("Proveedor", lazy="noload")  # noqa: F821
    usuario: Mapped["User"] = relationship("User", lazy="noload")  # noqa: F821
    pago: Mapped["Pago | None"] = relationship("Pago", back_populates="pagos_proveedor", lazy="noload")  # noqa: F821
    imputaciones: Mapped[list["PagoProveedorImputacion"]] = relationship(
        "PagoProveedorImputacion", back_populates="pago_proveedor", lazy="noload", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PagoProveedor(id={self.id}, proveedor_id={self.proveedor_id}, importe={self.importe})>"


class PagoProveedorImputacion(Base):
    __tablename__ = "pago_proveedor_imputaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pago_proveedor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pagos_proveedor.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingreso_mercaderia_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ingresos_mercaderia.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    importe_aplicado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    pago_proveedor: Mapped["PagoProveedor"] = relationship("PagoProveedor", back_populates="imputaciones", lazy="noload")
    ingreso: Mapped["IngresoMercaderia"] = relationship("IngresoMercaderia", back_populates="imputaciones", lazy="noload")  # noqa: F821

    def __repr__(self) -> str:
        return f"<PagoProveedorImputacion(id={self.id}, pago_proveedor_id={self.pago_proveedor_id}, ingreso_id={self.ingreso_mercaderia_id}, importe={self.importe_aplicado})>"

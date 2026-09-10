from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ProveedorCuenta(Base):
    """Una de las cuentas bancarias en las que se le puede pagar al proveedor.

    Mismo patrón que la libreta de direcciones del cliente (`ClienteDireccion`):
    tabla hija, una marcada por defecto, baja lógica. Un proveedor grande cobra en
    varias cuentas —una por sociedad, o una para transferencias y otra para
    cheques— y hasta acá había que buscar el CBU en un mail cada vez.

    No confundir con `Cuenta`, que son las cuentas de dinero de SANALLE (de dónde
    sale la plata). Esta es la de la contraparte: a dónde va.

    El `cuit` va acá y no en `Proveedor` a propósito: el titular de la cuenta no
    siempre es el proveedor (puede ser una razón social del grupo), y es el dato
    que pide el banco al cargar la transferencia.
    """

    __tablename__ = "proveedor_cuentas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proveedor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("proveedores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Cómo la reconoce quien paga en el combo: "Santander principal", "Cheques".
    etiqueta: Mapped[str] = mapped_column(String(80), nullable=False)
    banco: Mapped[str | None] = mapped_column(String(120), nullable=True)
    titular: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cuit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    numero_cuenta: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cbu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    alias: Mapped[str | None] = mapped_column(String(60), nullable=True)
    observacion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # La que se propone sola al registrar un pago.
    es_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    activo: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    proveedor: Mapped["Proveedor"] = relationship(  # noqa: F821
        "Proveedor", back_populates="cuentas", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<ProveedorCuenta(id={self.id}, proveedor_id={self.proveedor_id}, etiqueta={self.etiqueta!r})>"

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Cuenta(Base):
    """Cuenta de dinero de la empresa (caja, banco, billetera).

    A cada pago (cobro) se lo puede asociar a una cuenta. Siempre hay una
    cuenta marcada por defecto (es_default) que se usa si no se elige otra.
    """

    __tablename__ = "cuentas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    # 'efectivo' | 'banco' | 'billetera' | 'otro'
    tipo: Mapped[str] = mapped_column(String(30), nullable=False, default="banco", server_default="banco")
    banco: Mapped[str | None] = mapped_column(String(120), nullable=True)
    numero_cuenta: Mapped[str | None] = mapped_column(String(80), nullable=True)
    titular: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cbu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    alias: Mapped[str | None] = mapped_column(String(60), nullable=True)
    es_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FeatureFlag(Base):
    """Habilita/deshabilita módulos de la app. Si una clave no existe en la
    tabla, el módulo se considera habilitado (default abierto)."""

    __tablename__ = "feature_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clave: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    habilitado: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<FeatureFlag(clave={self.clave!r}, habilitado={self.habilitado})>"

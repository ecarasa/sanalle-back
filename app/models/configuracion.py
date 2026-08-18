from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Configuracion(Base):
    """Configuración general del sistema como pares clave/valor.

    Los valores se guardan como texto; el service los castea según la clave.
    Una clave ausente usa el default de CONFIG_DEFAULTS.
    """

    __tablename__ = "configuracion"

    clave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

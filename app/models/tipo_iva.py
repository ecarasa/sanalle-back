from decimal import Decimal

from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TipoIva(Base):
    __tablename__ = "tipo_iva"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False)
    tasa: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    discrimina: Mapped[str] = mapped_column(String(1), nullable=False, default="N", server_default="N")

    def __repr__(self) -> str:
        return f"<TipoIva(id={self.id}, nombre={self.nombre!r}, tasa={self.tasa})>"

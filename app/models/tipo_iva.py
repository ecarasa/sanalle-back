from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TipoIva(Base):
    """Catálogo de conceptos impositivos: IVA (21, 10.5) y percepciones (IIBB provinciales, etc.).

    Se usa como catálogo de impuestos/percepciones que se agregan a un ingreso de mercadería.
    """
    __tablename__ = "tipo_iva"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False)
    tasa: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    discrimina: Mapped[str] = mapped_column(String(1), nullable=False, default="N", server_default="N")
    # "iva" | "percepcion" — para agrupar en la UI.
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="percepcion", server_default="percepcion")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    def __repr__(self) -> str:
        return f"<TipoIva(id={self.id}, nombre={self.nombre!r}, tasa={self.tasa})>"

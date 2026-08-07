from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScraperRunItem(Base):
    """Detalle por producto de una corrida del scraper de PVP.

    Se registra SIEMPRE (aunque el precio no cambie), para tener el log completo
    de que el scraper trajo bien el precio.
    """

    __tablename__ = "scraper_run_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scraper_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    producto_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("productos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)  # updated | skipped | failed
    pvp_anterior: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    pvp_traido: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    detalle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ScraperRunItem(run={self.run_id}, prod={self.producto_id}, {self.resultado})>"

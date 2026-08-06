import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
   
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Float,
    func,
)

from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Ruta(Base):
    __tablename__ = "rutas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    ruta_geojson: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden_waypoints: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_entrega: Mapped[date | None] = mapped_column(Date, nullable=True)
    distancia_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    tiempo_minutos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tramos_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    inicio_recorrido: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fin_recorrido: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eta_paradas: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    repartidor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


    repartidor: Mapped["User | None"] = relationship(  # noqa: F821
        "User", lazy="noload", foreign_keys=[repartidor_id]
    )

    def __repr__(self) -> str:
        return f"<Ruta(id={self.id}, hash_id={self.hash_id!r}, distancia_km={self.distancia_km})>"

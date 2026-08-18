from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Entidad(Base):
    """Valor paramétrico genérico para los combos de la app.

    Una sola tabla para todos los desplegables "sueltos" (los que hoy son texto
    libre o constantes hardcodeadas): condición de pago, transporte, sociedad,
    tipo de precio, etc. Se agrupan por `categoria`.

    NO reemplaza a las tablas con FKs propias (zonas, localidades, laboratorios,
    bancos, depósitos, proveedores): esas siguen en su tabla.
    """

    __tablename__ = "entidades"
    __table_args__ = (UniqueConstraint("categoria", "nombre", name="uq_entidad_categoria_nombre"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Grupo del combo: 'condicion_pago' | 'transporte' | 'sociedad' | 'tipo_precio' | ...
    categoria: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    # Código estable opcional para referenciar por valor (ej. 'contado', 'oca').
    codigo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", default=True)
    # Campos propios de cada categoría (ej. {"dias": 30} en condición de pago).
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

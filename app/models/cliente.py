from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    razon_social: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cuit: Mapped[str | None] = mapped_column(String(13), nullable=True, index=True)
    domicilio: Mapped[str] = mapped_column(String(500), nullable=False)
    telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(5), nullable=True)
    tipo: Mapped[str | None] = mapped_column(String(20), nullable=True)  # mayorista / minorista
    zona_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("zonas.id"), nullable=True
    )
    condicion_pago: Mapped[str | None] = mapped_column(String(20), nullable=True)  # contado / plazo
    plazo_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)  # días para el compromiso de pago
    dias_entrega: Mapped[int | None] = mapped_column(Integer, nullable=True)  # días hasta la fecha de entrega por defecto
    vendedor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    deuda_inicial: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    deuda_inicial_remito: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    deuda_inicial_factura: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    localidad_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("localidades.id"), nullable=True
    )
    avg_dias_pago: Mapped[float | None] = mapped_column(Float, nullable=True)
    aprobado: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    comentarios: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitud: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitud: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Último transporte con el que se le despachó. Se actualiza solo al guardar
    # un pedido, para no tener que retipearlo en cada uno; sigue siendo editable
    # acá y por pedido.
    transporte_habitual: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    vendedor: Mapped["User"] = relationship(  # noqa: F821
        "User", foreign_keys=[vendedor_id], lazy="noload"
    )
    localidad_rel: Mapped["Localidad"] = relationship(  # noqa: F821
        "Localidad", lazy="noload"
    )
    zona_rel: Mapped["Zona"] = relationship(  # noqa: F821
        "Zona", lazy="noload"
    )
    pedidos: Mapped[list["Pedido"]] = relationship(  # noqa: F821
        "Pedido", back_populates="cliente", lazy="noload"
    )
    pagos: Mapped[list["Pago"]] = relationship(  # noqa: F821
        "Pago", back_populates="cliente", lazy="noload"
    )
    direcciones: Mapped[list["ClienteDireccion"]] = relationship(  # noqa: F821
        "ClienteDireccion",
        back_populates="cliente",
        lazy="noload",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Cliente(id={self.id}, nombre={self.nombre!r})>"

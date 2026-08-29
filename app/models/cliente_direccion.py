from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ClienteDireccion(Base):
    """Una de las direcciones de entrega de un cliente.

    El `domicilio` del cliente es su dirección fiscal y sigue siendo una sola.
    Esto es aparte: la mercadería puede ir a varios lados (sucursales, depósito
    del cliente, domicilio particular) y cada pedido elige a cuál.

    El pedido igual guarda la dirección como texto (`Pedido.direccion_entrega`):
    es la foto del momento, y de ahí salen el remito y la hoja de ruta. Si acá
    después se corrige una dirección, los pedidos viejos no cambian.
    """

    __tablename__ = "cliente_direcciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Cómo la reconoce el vendedor en el combo: "Sucursal Centro", "Depósito".
    etiqueta: Mapped[str] = mapped_column(String(80), nullable=False)
    direccion: Mapped[str] = mapped_column(String(500), nullable=False)
    localidad_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("localidades.id"), nullable=True
    )
    codigo_postal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latitud: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitud: Mapped[float | None] = mapped_column(Float, nullable=True)
    # La que se propone sola al abrir un pedido nuevo.
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

    cliente: Mapped["Cliente"] = relationship(  # noqa: F821
        "Cliente", back_populates="direcciones", lazy="noload"
    )
    localidad: Mapped["Localidad | None"] = relationship(  # noqa: F821
        "Localidad", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<ClienteDireccion(id={self.id}, cliente_id={self.cliente_id}, etiqueta={self.etiqueta!r})>"

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EstadoSolicitud(enum.Enum):
    pendiente = "pendiente"
    aprobada = "aprobada"
    rechazada = "rechazada"


class SolicitudCambioCliente(Base):
    __tablename__ = "solicitudes_cambio_cliente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id"), nullable=False, index=True
    )
    solicitante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    campo: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[EstadoSolicitud] = mapped_column(
        Enum(EstadoSolicitud, name="estadosolicitud", native_enum=True),
        default=EstadoSolicitud.pendiente,
        server_default="pendiente",
        nullable=False,
        index=True,
    )
    revisado_por_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="noload")  # noqa: F821
    solicitante: Mapped["User"] = relationship("User", foreign_keys=[solicitante_id], lazy="noload")  # noqa: F821
    revisado_por: Mapped["User | None"] = relationship("User", foreign_keys=[revisado_por_id], lazy="noload")  # noqa: F821

    def __repr__(self) -> str:
        return f"<SolicitudCambioCliente(id={self.id}, cliente_id={self.cliente_id}, estado={self.estado.value})>"

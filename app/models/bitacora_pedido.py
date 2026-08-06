from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BitacoraPedido(Base):
    """Log append-only de modificaciones sobre pedidos. Una fila por campo cambiado.

    `pedido_id` NO es ForeignKey a propósito: DELETE /pedidos/{id} borra el pedido
    físicamente (con cascade a sus items). Con una FK, ese borrado se llevaría puesto
    justo el registro de quién lo borró. Por eso también se guardan snapshots de los
    nombres: la fila tiene que seguir siendo legible cuando el pedido ya no existe.
    """

    __tablename__ = "bitacora_pedidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    pedido_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    numero_pedido: Mapped[str | None] = mapped_column(String(50), nullable=True)

    usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    usuario_nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # creacion | actualizacion | eliminacion | cambio_estado_despacho |
    # cambio_estado_pago | comision_item | asignacion_repartidor
    evento: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    entidad: Mapped[str] = mapped_column(String(10), nullable=False)  # pedido | item
    accion: Mapped[str] = mapped_column(String(15), nullable=False)  # alta | baja | modificacion

    campo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    valor_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, nullable=True)

    producto_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    producto_nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # uuid4 por request: agrupa todos los cambios de una misma edición
    grupo_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    usuario = relationship("User", lazy="noload")

    def __repr__(self) -> str:
        return (
            f"<BitacoraPedido(id={self.id}, pedido_id={self.pedido_id}, "
            f"evento={self.evento!r}, campo={self.campo!r})>"
        )

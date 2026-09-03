"""Bitácora de productos: quién cambió qué en la ficha, y cuándo.

Las cantidades ya se auditan en `movimientos_stock`. Esto es lo otro: el precio,
el mínimo de reposición, la categoría, el nombre. Hasta ahora un aumento masivo
de precios o el borrado de un producto no dejaban ningún rastro.

Espeja `BitacoraPedido`, incluida la decisión de que `producto_id` NO sea
ForeignKey: el producto se puede borrar, y con una FK ese borrado se llevaría
puesto justo el registro de quién lo borró. Por eso también se guardan el código
y el nombre: la fila tiene que seguir siendo legible cuando el producto ya no está.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BitacoraProducto(Base):
    __tablename__ = "bitacora_productos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    producto_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    producto_codigo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    producto_nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)

    usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    usuario_nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # alta | modificacion | baja
    accion: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    # De dónde vino el cambio: ficha | minimos | precios_masivo | import | api.
    # Sirve para distinguir "lo tocó alguien a mano" de "entró por una planilla".
    origen: Mapped[str] = mapped_column(String(20), nullable=False, default="ficha", index=True)

    campo: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    valor_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, nullable=True)

    # uuid4 por request: agrupa todos los campos tocados en una misma edición.
    grupo_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    usuario = relationship("User", lazy="noload")

    def __repr__(self) -> str:
        return (
            f"<BitacoraProducto(id={self.id}, producto_id={self.producto_id}, "
            f"campo={self.campo!r})>"
        )

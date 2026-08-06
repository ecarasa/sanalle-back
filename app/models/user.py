import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RolUsuario(enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    ventas = "ventas"
    repartidor = "repartidor"



class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(
        Enum(RolUsuario, name="rolusuario", native_enum=True),
        nullable=False,
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    # USR-01: Force password change flag
    debe_cambiar_contrasena: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    comision_generico: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0", nullable=True)
    comision_otc: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0", nullable=True)

    # Relationships
    pedidos: Mapped[list["Pedido"]] = relationship(  # noqa: F821
        "Pedido", back_populates="vendedor", lazy="noload", foreign_keys="Pedido.vendedor_id"
    )
    pagos_recibidos: Mapped[list["Pago"]] = relationship(  # noqa: F821
        "Pago", back_populates="receptor", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username!r}, rol={self.rol.value})>"

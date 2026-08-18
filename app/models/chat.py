from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ChatConversacion(Base):
    __tablename__ = "chat_conversaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 'individual' | 'grupo'
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="individual")
    # Nombre del grupo (solo para grupos; individual usa el nombre del otro usuario).
    nombre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    creador_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    participantes: Mapped[list["ChatParticipante"]] = relationship(
        "ChatParticipante", back_populates="conversacion", cascade="all, delete-orphan", lazy="selectin"
    )
    mensajes: Mapped[list["ChatMensaje"]] = relationship(
        "ChatMensaje", back_populates="conversacion", cascade="all, delete-orphan"
    )


class ChatParticipante(Base):
    __tablename__ = "chat_participantes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversacion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_conversaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Última vez que el usuario leyó la conversación (para contar no leídos).
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversacion: Mapped["ChatConversacion"] = relationship("ChatConversacion", back_populates="participantes")
    usuario: Mapped["User"] = relationship("User", lazy="selectin")  # noqa: F821


class ChatMensaje(Base):
    __tablename__ = "chat_mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversacion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_conversaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    autor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    conversacion: Mapped["ChatConversacion"] = relationship("ChatConversacion", back_populates="mensajes")
    autor: Mapped["User"] = relationship("User", lazy="selectin")  # noqa: F821

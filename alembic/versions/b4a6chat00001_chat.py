"""chat interno: conversaciones, participantes y mensajes

Revision ID: b4a6chat00001
Revises: a3f5fmtventa01
Create Date: 2026-08-11

Aditiva: tres tablas nuevas para el chat interno (grupos e individual).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4a6chat00001'
down_revision: Union[str, None] = 'a3f5fmtventa01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_conversaciones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tipo", sa.String(length=20), nullable=False, server_default="individual"),
        sa.Column("nombre", sa.String(length=120), nullable=True),
        sa.Column("creador_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "chat_participantes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversacion_id", sa.Integer(), sa.ForeignKey("chat_conversaciones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_chat_participantes_conversacion_id", "chat_participantes", ["conversacion_id"])
    op.create_index("ix_chat_participantes_user_id", "chat_participantes", ["user_id"])
    op.create_table(
        "chat_mensajes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversacion_id", sa.Integer(), sa.ForeignKey("chat_conversaciones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("autor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_chat_mensajes_conversacion_id", "chat_mensajes", ["conversacion_id"])
    op.create_index("ix_chat_mensajes_autor_id", "chat_mensajes", ["autor_id"])
    op.create_index("ix_chat_mensajes_created_at", "chat_mensajes", ["created_at"])


def downgrade() -> None:
    op.drop_table("chat_mensajes")
    op.drop_table("chat_participantes")
    op.drop_table("chat_conversaciones")

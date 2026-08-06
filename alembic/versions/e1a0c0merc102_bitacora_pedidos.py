"""bitacora de pedidos

Revision ID: e1a0c0merc102
Revises: e1a0c0merc101
Create Date: 2026-07-13

pedido_id NO lleva ForeignKey a proposito: DELETE /pedidos/{id} borra el pedido
fisicamente, y con una FK el borrado se llevaria puesto el registro de quien lo borro.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1a0c0merc102'
down_revision: Union[str, None] = 'e1a0c0merc101'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bitacora_pedidos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pedido_id", sa.Integer(), nullable=False),
        sa.Column("numero_pedido", sa.String(length=50), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("usuario_nombre", sa.String(length=255), nullable=True),
        sa.Column("evento", sa.String(length=30), nullable=False),
        sa.Column("entidad", sa.String(length=10), nullable=False),
        sa.Column("accion", sa.String(length=15), nullable=False),
        sa.Column("campo", sa.String(length=50), nullable=True),
        sa.Column("valor_anterior", sa.Text(), nullable=True),
        sa.Column("valor_nuevo", sa.Text(), nullable=True),
        sa.Column("producto_id", sa.Integer(), nullable=True),
        sa.Column("producto_nombre", sa.String(length=255), nullable=True),
        sa.Column("grupo_id", sa.String(length=36), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bitacora_pedidos_pedido_id", "bitacora_pedidos", ["pedido_id"])
    op.create_index("ix_bitacora_pedidos_usuario_id", "bitacora_pedidos", ["usuario_id"])
    op.create_index("ix_bitacora_pedidos_evento", "bitacora_pedidos", ["evento"])
    op.create_index("ix_bitacora_pedidos_grupo_id", "bitacora_pedidos", ["grupo_id"])
    op.create_index("ix_bitacora_pedidos_created_at", "bitacora_pedidos", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_bitacora_pedidos_created_at", table_name="bitacora_pedidos")
    op.drop_index("ix_bitacora_pedidos_grupo_id", table_name="bitacora_pedidos")
    op.drop_index("ix_bitacora_pedidos_evento", table_name="bitacora_pedidos")
    op.drop_index("ix_bitacora_pedidos_usuario_id", table_name="bitacora_pedidos")
    op.drop_index("ix_bitacora_pedidos_pedido_id", table_name="bitacora_pedidos")
    op.drop_table("bitacora_pedidos")

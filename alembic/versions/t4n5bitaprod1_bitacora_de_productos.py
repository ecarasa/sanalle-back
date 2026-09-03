"""bitácora de productos: quién cambió qué en la ficha

Las cantidades ya dejaban rastro en `movimientos_stock`, pero la ficha del
producto no: un aumento masivo de precios, un cambio de mínimo o el borrado de un
producto no quedaban registrados en ningún lado. Cuando alguien preguntaba "¿por
qué este producto cambió de precio?", la única respuesta posible era "no se sabe".

`producto_id` no es ForeignKey a propósito, igual que en `bitacora_pedidos`: el
producto se puede borrar, y una FK se llevaría puesto justo el registro de quién
lo borró. Por eso también se guardan el código y el nombre del momento.

Revision ID: t4n5bitaprod1
Revises: s3m4stock0001
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "t4n5bitaprod1"
down_revision: Union[str, None] = "s3m4stock0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bitacora_productos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("producto_id", sa.Integer(), nullable=False),
        sa.Column("producto_codigo", sa.String(length=50), nullable=True),
        sa.Column("producto_nombre", sa.String(length=255), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("usuario_nombre", sa.String(length=255), nullable=True),
        sa.Column("accion", sa.String(length=15), nullable=False),
        sa.Column("origen", sa.String(length=20), nullable=False, server_default="ficha"),
        sa.Column("campo", sa.String(length=50), nullable=True),
        sa.Column("valor_anterior", sa.Text(), nullable=True),
        sa.Column("valor_nuevo", sa.Text(), nullable=True),
        sa.Column("grupo_id", sa.String(length=36), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bitacora_productos_producto_id", "bitacora_productos", ["producto_id"])
    op.create_index("ix_bitacora_productos_usuario_id", "bitacora_productos", ["usuario_id"])
    op.create_index("ix_bitacora_productos_accion", "bitacora_productos", ["accion"])
    op.create_index("ix_bitacora_productos_origen", "bitacora_productos", ["origen"])
    op.create_index("ix_bitacora_productos_campo", "bitacora_productos", ["campo"])
    op.create_index("ix_bitacora_productos_grupo_id", "bitacora_productos", ["grupo_id"])
    op.create_index("ix_bitacora_productos_created_at", "bitacora_productos", ["created_at"])


def downgrade() -> None:
    for idx in (
        "ix_bitacora_productos_created_at",
        "ix_bitacora_productos_grupo_id",
        "ix_bitacora_productos_campo",
        "ix_bitacora_productos_origen",
        "ix_bitacora_productos_accion",
        "ix_bitacora_productos_usuario_id",
        "ix_bitacora_productos_producto_id",
    ):
        op.drop_index(idx, table_name="bitacora_productos")
    op.drop_table("bitacora_productos")

"""formato de venta por producto (vende_caja/blister/comprimido) + unidad_venta en items

Revision ID: a3f5fmtventa01
Revises: f1a2scitem01
Create Date: 2026-08-11

Aditiva: banderas de formato de venta en productos (default caja) y la unidad de
venta usada en cada línea de pedido. No cambia el comportamiento existente hasta
que un producto se configure con otro formato.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f5fmtventa01'
down_revision: Union[str, None] = 'f1a2scitem01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("productos", sa.Column("vende_caja", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.add_column("productos", sa.Column("vende_blister", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("productos", sa.Column("vende_comprimido", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("pedido_items", sa.Column("unidad_venta", sa.String(length=20), server_default="caja", nullable=False))


def downgrade() -> None:
    op.drop_column("pedido_items", "unidad_venta")
    op.drop_column("productos", "vende_comprimido")
    op.drop_column("productos", "vende_blister")
    op.drop_column("productos", "vende_caja")

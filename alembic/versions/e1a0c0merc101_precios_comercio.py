"""lista comercio: margenes y precios por formato + formato en pedido_items

Revision ID: e1a0c0merc101
Revises: d3f1a2b4c5e6
Create Date: 2026-07-13

Los margenes van nullable y SIN server_default: un margen en NULL significa que el
producto no se vende en ese formato, y su precio queda en NULL (el catalogo muestra
"—"). Un default de 0 le inventaria un precio a todo el catalogo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1a0c0merc101'
down_revision: Union[str, None] = 'd3f1a2b4c5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRODUCTO_COLS = [
    "margen_comercio_blisteado",
    "precio_venta_comercio_blisteado",
    "margen_comercio_estuchado",
    "precio_venta_comercio_estuchado",
    "margen_comercio_hospitalario",
    "precio_venta_comercio_hospitalario",
]


def upgrade() -> None:
    for name in PRODUCTO_COLS:
        op.add_column("productos", sa.Column(name, sa.Numeric(12, 2), nullable=True))
    op.add_column("pedido_items", sa.Column("formato_comercio", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("pedido_items", "formato_comercio")
    for name in reversed(PRODUCTO_COLS):
        op.drop_column("productos", name)

"""comercio pasa a un solo margen/precio (sin formatos blisteado/estuchado/hospitalario)

Revision ID: b3c4comerc01
Revises: a2b3pvpsel01
Create Date: 2026-07-22

El formato ya está a nivel producto (la presentación), así que comercio deja de
dividirse en 3. Se reemplazan las 6 columnas por formato por un único par
margen_comercio / precio_venta_comercio, y se elimina pedido_items.formato_comercio.
Todas las columnas viejas estaban en NULL (comercio nunca se usó), no hay pérdida de datos.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c4comerc01'
down_revision: Union[str, None] = 'a2b3pvpsel01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VIEJAS = [
    "margen_comercio_blisteado", "precio_venta_comercio_blisteado",
    "margen_comercio_estuchado", "precio_venta_comercio_estuchado",
    "margen_comercio_hospitalario", "precio_venta_comercio_hospitalario",
]


def upgrade() -> None:
    op.add_column("productos", sa.Column("margen_comercio", sa.Numeric(12, 2), nullable=True))
    op.add_column("productos", sa.Column("precio_venta_comercio", sa.Numeric(12, 2), nullable=True))
    for col in VIEJAS:
        op.drop_column("productos", col)
    op.drop_column("pedido_items", "formato_comercio")


def downgrade() -> None:
    op.add_column("pedido_items", sa.Column("formato_comercio", sa.String(length=20), nullable=True))
    for col in reversed(VIEJAS):
        op.add_column("productos", sa.Column(col, sa.Numeric(12, 2), nullable=True))
    op.drop_column("productos", "precio_venta_comercio")
    op.drop_column("productos", "margen_comercio")

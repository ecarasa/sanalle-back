"""orden manual de laboratorios en la lista de precios

La droguería ordena los laboratorios por importancia comercial, no alfabéticamente,
y las listas de precios impresas tienen que respetar ese orden. Hasta acá el único
criterio era el nombre.

Mismo patrón que `depositos.orden` y `entidades.orden`.

Revision ID: x8r9laborden01
Revises: w7q8excepprecio
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "x8r9laborden01"
down_revision: Union[str, None] = "w7q8excepprecio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "laboratorios",
        sa.Column("orden", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    # Backfill alfabético: arrancar todos en 0 dejaría a los botones ↑/↓ sin nada
    # que intercambiar, y el primer clic no haría nada visible.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (ORDER BY lower(nombre)) AS rn FROM laboratorios
        )
        UPDATE laboratorios l SET orden = r.rn FROM ranked r WHERE r.id = l.id
        """
    )


def downgrade() -> None:
    op.drop_column("laboratorios", "orden")

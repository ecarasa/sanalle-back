"""excepciones de precio y umbral mayorista por pedido

Un pedido puede facturarse a un precio distinto del de lista. Hasta acá eso no
dejaba rastro: quedaba enterrado en `pedido_items.precio_unitario` y nadie podía
listar "los pedidos con precios fuera de lista".

`tiene_excepcion_precio` se persiste en vez de calcularse porque la pantalla de
pedidos tiene que poder filtrar por él, y en SQL sería una subconsulta
correlacionada sobre pedido_items ⋈ productos por cada fila del listado.

`aplica_umbral_mayorista` permite apagar, para un pedido puntual, el salto
automático a precio mayorista por volumen.

Revision ID: w7q8excepprecio
Revises: v6p7tipocliente
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "w7q8excepprecio"
down_revision: Union[str, None] = "v6p7tipocliente"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pedidos",
        sa.Column(
            "aplica_umbral_mayorista",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "pedidos",
        sa.Column(
            "tiene_excepcion_precio",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("pedidos", sa.Column("excepcion_precio_detalle", sa.Text(), nullable=True))
    op.create_index("ix_pedidos_tiene_excepcion_precio", "pedidos", ["tiene_excepcion_precio"])

    # Sin backfill a propósito: recalcular el flag para los pedidos históricos
    # usaría la lista de precios de HOY, no la del día en que se hizo cada pedido.
    # Marcaría como "excepción" cualquier pedido anterior a un aumento, que es
    # exactamente el ruido que esta columna existe para evitar. Los pedidos viejos
    # arrancan en false y se van marcando solos a medida que se editan.


def downgrade() -> None:
    op.drop_index("ix_pedidos_tiene_excepcion_precio", table_name="pedidos")
    op.drop_column("pedidos", "excepcion_precio_detalle")
    op.drop_column("pedidos", "tiene_excepcion_precio")
    op.drop_column("pedidos", "aplica_umbral_mayorista")

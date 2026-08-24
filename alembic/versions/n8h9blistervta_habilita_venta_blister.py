"""habilita la venta por blíster en los productos fraccionables

La migración que creó el formato de venta (a3f5fmtventa01) agregó vende_blister
con server_default=false y no hizo backfill, así que TODOS los productos
quedaron como "solo caja". El selector de unidad del formulario de pedido solo
aparece cuando el producto admite más de una unidad, con lo cual nunca se
mostraba y no se podía vender fraccionado sin ir producto por producto.

Un producto con blisters_por_caja > 1 es físicamente fraccionable: se habilita
la venta por blíster. Los que no tienen el dato, o tienen 1, quedan como están
(un "blíster" ahí sería la caja entera).

El flag sigue mandando: después de esta migración se puede destildar "Blíster"
en la ficha de cualquier producto que no se quiera vender fraccionado.

Revision ID: n8h9blistervta
Revises: m7g8stockdep01
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n8h9blistervta"
down_revision: Union[str, None] = "m7g8stockdep01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE productos
        SET vende_blister = true
        WHERE blisters_por_caja IS NOT NULL
          AND blisters_por_caja > 1
          AND vende_blister = false
        """
    )


def downgrade() -> None:
    # Vuelve a "solo caja" el mismo conjunto que tocó el upgrade. Si alguien
    # destildó Blíster a mano después de migrar, el downgrade lo deja igual
    # (ya estaba en false); lo que no se puede distinguir es un producto que
    # se haya tildado a mano, que también volvería a false.
    op.execute(
        """
        UPDATE productos
        SET vende_blister = false
        WHERE blisters_por_caja IS NOT NULL
          AND blisters_por_caja > 1
        """
    )

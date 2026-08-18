"""unidad_venta en items de notas de crédito/débito

Revision ID: d6c8notaunidad01
Revises: c5b7config0001
Create Date: 2026-08-11

Aditiva: fidelidad de la unidad de venta al copiar ítems de un pedido a una nota.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd6c8notaunidad01'
down_revision: Union[str, None] = 'c5b7config0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("nota_credito_items", sa.Column("unidad_venta", sa.String(length=20), server_default="caja", nullable=False))


def downgrade() -> None:
    op.drop_column("nota_credito_items", "unidad_venta")

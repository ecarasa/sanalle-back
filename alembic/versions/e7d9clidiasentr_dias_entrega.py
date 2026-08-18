"""dias_entrega por cliente (default de fecha de entrega)

Revision ID: e7d9clidiasentr
Revises: d6c8notaunidad01
Create Date: 2026-08-11

Aditiva: días hasta la fecha de entrega por defecto, configurable por cliente.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7d9clidiasentr'
down_revision: Union[str, None] = 'd6c8notaunidad01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clientes", sa.Column("dias_entrega", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("clientes", "dias_entrega")

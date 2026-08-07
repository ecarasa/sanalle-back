"""marca stock_legacy en depositos (mapeo A/B) para dual-write

Revision ID: e9f0legac001
Revises: d7e8depos001
Create Date: 2026-08-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e9f0legac001'
down_revision: Union[str, None] = 'd7e8depos001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("depositos", sa.Column("stock_legacy", sa.String(length=1), nullable=True))
    # Mapeo con las columnas viejas: Sanalle=A, Farmacare=B (seeds de la migración anterior)
    op.execute("UPDATE depositos SET stock_legacy='a' WHERE nombre='Sanalle'")
    op.execute("UPDATE depositos SET stock_legacy='b' WHERE nombre='Farmacare'")


def downgrade() -> None:
    op.drop_column("depositos", "stock_legacy")

"""configuración general (key-value)

Revision ID: c5b7config0001
Revises: b4a6chat00001
Create Date: 2026-08-11

Aditiva: tabla de configuración general clave/valor.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5b7config0001'
down_revision: Union[str, None] = 'b4a6chat00001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "configuracion",
        sa.Column("clave", sa.String(length=80), primary_key=True),
        sa.Column("valor", sa.String(length=500), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("configuracion")

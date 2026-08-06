"""guardar la opcion de alfabeta elegida a mano (pvp_descripcion)

Revision ID: a2b3pvpsel01
Revises: f1a2b3flag001
Create Date: 2026-07-22

Aditiva: una columna nullable. El scraper la usa para elegir la misma opción que
seleccionó el usuario cuando la página de Alfabeta trae varias presentaciones.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a2b3pvpsel01'
down_revision: Union[str, None] = 'f1a2b3flag001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("productos", sa.Column("pvp_descripcion", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("productos", "pvp_descripcion")

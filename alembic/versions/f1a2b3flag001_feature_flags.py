"""feature flags de modulos

Revision ID: f1a2b3flag001
Revises: e1a0c0merc102
Create Date: 2026-07-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3flag001'
down_revision: Union[str, None] = 'e1a0c0merc102'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("clave", sa.String(length=100), nullable=False),
        sa.Column("habilitado", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clave"),
    )
    op.create_index("ix_feature_flags_clave", "feature_flags", ["clave"])


def downgrade() -> None:
    op.drop_index("ix_feature_flags_clave", table_name="feature_flags")
    op.drop_table("feature_flags")

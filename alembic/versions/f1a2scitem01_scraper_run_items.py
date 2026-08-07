"""detalle por producto de cada corrida del scraper (log completo)

Revision ID: f1a2scitem01
Revises: e9f0legac001
Create Date: 2026-08-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2scitem01'
down_revision: Union[str, None] = 'e9f0legac001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scraper_run_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("producto_id", sa.Integer(), nullable=False),
        sa.Column("resultado", sa.String(length=20), nullable=False),
        sa.Column("pvp_anterior", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("pvp_traido", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("detalle", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["scraper_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["producto_id"], ["productos.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sri_run", "scraper_run_items", ["run_id"])
    op.create_index("ix_sri_producto", "scraper_run_items", ["producto_id"])


def downgrade() -> None:
    op.drop_index("ix_sri_producto", table_name="scraper_run_items")
    op.drop_index("ix_sri_run", table_name="scraper_run_items")
    op.drop_table("scraper_run_items")

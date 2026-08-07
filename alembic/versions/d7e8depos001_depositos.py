"""depositos dinámicos + stock por deposito (migra A/B)

Revision ID: d7e8depos001
Revises: c5d6scraper01
Create Date: 2026-08-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7e8depos001'
down_revision: Union[str, None] = 'c5d6scraper01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "depositos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("orden", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )

    op.create_table(
        "stock_producto_deposito",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("producto_id", sa.Integer(), nullable=False),
        sa.Column("deposito_id", sa.Integer(), nullable=False),
        sa.Column("cajas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("blisters", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["producto_id"], ["productos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deposito_id"], ["depositos.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("producto_id", "deposito_id", name="uq_stock_prod_dep"),
    )
    op.create_index("ix_spd_producto", "stock_producto_deposito", ["producto_id"])
    op.create_index("ix_spd_deposito", "stock_producto_deposito", ["deposito_id"])

    # Seed de los 2 depósitos actuales (ex Stock A y Stock B)
    op.execute(
        "INSERT INTO depositos (nombre, activo, orden) VALUES ('Sanalle', true, 1), ('Farmacare', true, 2)"
    )

    # Migrar el stock actual: A -> Sanalle, B -> Farmacare
    op.execute(
        """
        INSERT INTO stock_producto_deposito (producto_id, deposito_id, cajas, blisters)
        SELECT p.id, (SELECT id FROM depositos WHERE nombre='Sanalle'), p.stock_a_cajas, p.stock_a_blisters
        FROM productos p
        """
    )
    op.execute(
        """
        INSERT INTO stock_producto_deposito (producto_id, deposito_id, cajas, blisters)
        SELECT p.id, (SELECT id FROM depositos WHERE nombre='Farmacare'), p.stock_b_cajas, p.stock_b_blisters
        FROM productos p
        """
    )


def downgrade() -> None:
    op.drop_index("ix_spd_deposito", table_name="stock_producto_deposito")
    op.drop_index("ix_spd_producto", table_name="stock_producto_deposito")
    op.drop_table("stock_producto_deposito")
    op.drop_table("depositos")

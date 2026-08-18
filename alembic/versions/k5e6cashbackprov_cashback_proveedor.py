"""Cashback proveedor: doble tasa (parcial/total) + tabla acumuladora

Revision ID: k5e6cashbackprov
Revises: j4d5ingimpuestos
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa


revision = "k5e6cashbackprov"
down_revision = "j4d5ingimpuestos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proveedores", sa.Column("cashback_parcial", sa.Numeric(14, 2), server_default="0", nullable=False))
    op.add_column("proveedores", sa.Column("cashback_total", sa.Numeric(14, 2), server_default="0", nullable=False))
    # El cashback único actual corresponde al de pagos parciales.
    op.execute("UPDATE proveedores SET cashback_parcial = cashback")

    op.create_table(
        "cashback_proveedor",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("proveedor_id", sa.Integer(), nullable=False),
        sa.Column("pago_proveedor_id", sa.Integer(), nullable=True),
        sa.Column("importe", sa.Numeric(14, 2), nullable=False),
        sa.Column("estado", sa.String(length=20), server_default="pendiente", nullable=False),
        sa.Column("nota_proveedor_id", sa.Integer(), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["proveedor_id"], ["proveedores.id"]),
        sa.ForeignKeyConstraint(["pago_proveedor_id"], ["pagos_proveedor.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["nota_proveedor_id"], ["notas_proveedor.id"]),
    )
    op.create_index("ix_cashback_proveedor_proveedor_id", "cashback_proveedor", ["proveedor_id"])
    op.create_index("ix_cashback_proveedor_estado", "cashback_proveedor", ["estado"])
    op.create_index("ix_cashback_proveedor_pago_proveedor_id", "cashback_proveedor", ["pago_proveedor_id"])


def downgrade() -> None:
    op.drop_table("cashback_proveedor")
    op.drop_column("proveedores", "cashback_total")
    op.drop_column("proveedores", "cashback_parcial")

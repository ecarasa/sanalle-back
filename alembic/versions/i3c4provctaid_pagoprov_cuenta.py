"""Pago a proveedor: columna cuenta_id (cuenta desde donde sale la plata)

Revision ID: i3c4provctaid
Revises: h2b3puente001
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa


revision = "i3c4provctaid"
down_revision = "h2b3puente001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pagos_proveedor", sa.Column("cuenta_id", sa.Integer(), nullable=True))
    op.create_index("ix_pagos_proveedor_cuenta_id", "pagos_proveedor", ["cuenta_id"])
    op.create_foreign_key(
        "fk_pagos_proveedor_cuenta_id",
        "pagos_proveedor",
        "cuentas",
        ["cuenta_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_pagos_proveedor_cuenta_id", "pagos_proveedor", type_="foreignkey")
    op.drop_index("ix_pagos_proveedor_cuenta_id", table_name="pagos_proveedor")
    op.drop_column("pagos_proveedor", "cuenta_id")

"""cuentas de dinero + cuenta_id en pagos

Revision ID: f8e0cuentas001
Revises: e7d9clidiasentr
Create Date: 2026-08-12

Aditiva: tabla de cuentas (caja/banco/billetera) con una por defecto, y el
vínculo opcional de cada cobro a una cuenta.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f8e0cuentas001'
down_revision: Union[str, None] = 'e7d9clidiasentr'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cuentas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False, server_default="banco"),
        sa.Column("banco", sa.String(length=120), nullable=True),
        sa.Column("numero_cuenta", sa.String(length=80), nullable=True),
        sa.Column("titular", sa.String(length=120), nullable=True),
        sa.Column("cbu", sa.String(length=60), nullable=True),
        sa.Column("alias", sa.String(length=60), nullable=True),
        sa.Column("es_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    # Cuenta por defecto inicial ("Caja").
    op.execute("INSERT INTO cuentas (nombre, tipo, es_default, activo) VALUES ('Caja', 'efectivo', true, true)")

    op.add_column("pagos", sa.Column("cuenta_id", sa.Integer(), sa.ForeignKey("cuentas.id"), nullable=True))
    op.create_index("ix_pagos_cuenta_id", "pagos", ["cuenta_id"])


def downgrade() -> None:
    op.drop_index("ix_pagos_cuenta_id", table_name="pagos")
    op.drop_column("pagos", "cuenta_id")
    op.drop_table("cuentas")

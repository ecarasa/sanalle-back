"""múltiples cuentas bancarias por proveedor

Un proveedor no tenía ninguna cuenta modelada: el CBU se buscaba en un mail cada
vez que había que pagarle. Y los grandes cobran en varias —una por sociedad, o
una para transferencias y otra para cheques—, así que un solo campo no alcanzaba.

Mismo patrón que la libreta de direcciones del cliente (`cliente_direcciones`):
tabla hija con una marcada por defecto y baja lógica.

`pagos_proveedor.proveedor_cuenta_id` deja registrado el otro extremo del giro,
para poder contestar después "¿a qué CBU le pagamos esta factura?". Es `SET NULL`
y no `CASCADE`: dar de baja una cuenta de la libreta no puede llevarse puesto un
pago, que es un hecho contable.

Revision ID: y9s0provcuenta
Revises: x8r9laborden01
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "y9s0provcuenta"
down_revision: Union[str, None] = "x8r9laborden01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proveedor_cuentas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proveedor_id", sa.Integer(), nullable=False),
        sa.Column("etiqueta", sa.String(length=80), nullable=False),
        sa.Column("banco", sa.String(length=120), nullable=True),
        sa.Column("titular", sa.String(length=120), nullable=True),
        sa.Column("cuit", sa.String(length=20), nullable=True),
        sa.Column("numero_cuenta", sa.String(length=80), nullable=True),
        sa.Column("cbu", sa.String(length=60), nullable=True),
        sa.Column("alias", sa.String(length=60), nullable=True),
        sa.Column("observacion", sa.String(length=300), nullable=True),
        sa.Column("es_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["proveedor_id"], ["proveedores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proveedor_cuentas_proveedor_id", "proveedor_cuentas", ["proveedor_id"])

    op.add_column("pagos_proveedor", sa.Column("proveedor_cuenta_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_pagos_proveedor_proveedor_cuenta_id", "pagos_proveedor", ["proveedor_cuenta_id"]
    )
    op.create_foreign_key(
        "fk_pagos_proveedor_proveedor_cuenta_id",
        "pagos_proveedor",
        "proveedor_cuentas",
        ["proveedor_cuenta_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Sin backfill: no hay de dónde sacar a qué cuenta se pagó históricamente. Los
    # pagos viejos quedan en NULL, que es la verdad — "no se registró".


def downgrade() -> None:
    op.drop_constraint("fk_pagos_proveedor_proveedor_cuenta_id", "pagos_proveedor", type_="foreignkey")
    op.drop_index("ix_pagos_proveedor_proveedor_cuenta_id", table_name="pagos_proveedor")
    op.drop_column("pagos_proveedor", "proveedor_cuenta_id")
    op.drop_index("ix_proveedor_cuentas_proveedor_id", table_name="proveedor_cuentas")
    op.drop_table("proveedor_cuentas")

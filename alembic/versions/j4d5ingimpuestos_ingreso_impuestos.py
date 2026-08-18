"""Ingreso de mercadería: impuestos/percepciones + subtotal_neto; catálogo TipoIva (tipo, activo)

Revision ID: j4d5ingimpuestos
Revises: i3c4provctaid
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa


revision = "j4d5ingimpuestos"
down_revision = "i3c4provctaid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Catálogo de percepciones/IVA: agrupar por tipo y poder desactivar.
    op.add_column("tipo_iva", sa.Column("tipo", sa.String(length=20), server_default="percepcion", nullable=False))
    op.add_column("tipo_iva", sa.Column("activo", sa.Boolean(), server_default=sa.true(), nullable=False))

    # Subtotal neto (sin impuestos) del ingreso.
    op.add_column(
        "ingresos_mercaderia",
        sa.Column("subtotal_neto", sa.Numeric(14, 2), server_default="0", nullable=False),
    )

    # Líneas de impuesto/percepción de cabecera.
    op.create_table(
        "ingreso_impuestos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ingreso_id", sa.Integer(), nullable=False),
        sa.Column("tipo_iva_id", sa.Integer(), nullable=True),
        sa.Column("concepto", sa.String(length=100), nullable=False),
        sa.Column("base", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("tasa", sa.Numeric(6, 2), server_default="0", nullable=False),
        sa.Column("importe", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["ingreso_id"], ["ingresos_mercaderia.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tipo_iva_id"], ["tipo_iva.id"]),
    )
    op.create_index("ix_ingreso_impuestos_ingreso_id", "ingreso_impuestos", ["ingreso_id"])


def downgrade() -> None:
    op.drop_index("ix_ingreso_impuestos_ingreso_id", table_name="ingreso_impuestos")
    op.drop_table("ingreso_impuestos")
    op.drop_column("ingresos_mercaderia", "subtotal_neto")
    op.drop_column("tipo_iva", "activo")
    op.drop_column("tipo_iva", "tipo")

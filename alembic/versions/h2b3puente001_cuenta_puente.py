"""Cuenta puente / tránsito: columna pagos.es_puente + categoría 'transito'

Revision ID: h2b3puente001
Revises: g1a2entidades01
Create Date: 2026-08-12

Modela el pasamanos "cliente paga -> va directo a un proveedor": el cobro se marca
como es_puente y los movimientos en la Cuenta Sanalle se registran con la categoría
'transito', para que no impacten la caja real ni inflen los totales de ingresos/egresos.
"""
from alembic import op
import sqlalchemy as sa


revision = "h2b3puente001"
down_revision = "g1a2entidades01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nuevo valor del enum nativo categoriamovimiento (PG 12+: ADD VALUE es seguro en
    # transacción mientras no se use el valor en la misma transacción).
    op.execute("ALTER TYPE categoriamovimiento ADD VALUE IF NOT EXISTS 'transito'")

    # Marca de cobro-pasamanos.
    op.add_column(
        "pagos",
        sa.Column("es_puente", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("pagos", "es_puente")
    # Nota: Postgres no permite quitar un valor de un enum; 'transito' queda en el tipo.

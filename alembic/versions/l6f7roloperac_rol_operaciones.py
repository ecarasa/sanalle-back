"""Rol nuevo 'operaciones' (arma pedidos: en_preparacion -> listo_para_despacho)

Revision ID: l6f7roloperac
Revises: k5e6cashbackprov
Create Date: 2026-08-14
"""
from alembic import op


revision = "l6f7roloperac"
down_revision = "k5e6cashbackprov"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres 12+ admite ADD VALUE dentro de la transacción de Alembic mientras el
    # valor no se USE en la misma transacción (acá solo lo agregamos).
    op.execute("ALTER TYPE rolusuario ADD VALUE IF NOT EXISTS 'operaciones'")


def downgrade() -> None:
    # Postgres no soporta quitar un valor de un enum (no hay DROP VALUE). No-op.
    pass

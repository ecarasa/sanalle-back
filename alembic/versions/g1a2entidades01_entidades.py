"""entidades paramétricas (combos genéricos)

Revision ID: g1a2entidades01
Revises: f8e0cuentas001
Create Date: 2026-08-12

Tabla única para los combos "sueltos" de la app (texto libre/hardcodeados hasta
ahora): condición de pago, transporte, sociedad, tipo de precio. Se siembra con
los valores actuales. No toca las tablas con FK propias (zonas, localidades, etc.).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'g1a2entidades01'
down_revision: Union[str, None] = 'f8e0cuentas001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entidades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("categoria", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("codigo", sa.String(length=60), nullable=True),
        sa.Column("orden", sa.Integer(), server_default="0", nullable=False),
        sa.Column("activo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("categoria", "nombre", name="uq_entidad_categoria_nombre"),
    )
    op.create_index("ix_entidades_categoria", "entidades", ["categoria"])

    # Seeds de los combos actuales.
    op.execute("""
        INSERT INTO entidades (categoria, nombre, codigo, orden, activo) VALUES
          ('condicion_pago', 'Contado', 'contado', 1, true),
          ('condicion_pago', 'A plazo', 'plazo', 2, true),
          ('sociedad', 'Sanalle', 'sanalle', 1, true),
          ('sociedad', 'Farmacare', 'farmacare', 2, true),
          ('tipo_precio', 'Minorista', 'minorista', 1, true),
          ('tipo_precio', 'Mayorista', 'mayorista', 2, true),
          ('tipo_precio', 'Comercio', 'comercio', 3, true),
          ('transporte', 'Retira', 'retira', 1, true),
          ('transporte', 'Propio', 'propio', 2, true),
          ('transporte', 'OCA', 'oca', 3, true),
          ('transporte', 'Cruz del Sur', 'cruz_del_sur', 4, true)
    """)


def downgrade() -> None:
    op.drop_index("ix_entidades_categoria", table_name="entidades")
    op.drop_table("entidades")

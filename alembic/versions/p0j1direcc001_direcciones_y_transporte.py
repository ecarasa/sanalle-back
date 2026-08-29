"""libreta de direcciones de entrega y transporte habitual del cliente

Dos cosas que hoy obligan a retipear en cada pedido:

- `clientes.transporte_habitual`: el transporte se cargaba a mano en cada pedido
  aunque el cliente use siempre el mismo. Ahora el último usado queda guardado y
  se propone solo.
- `cliente_direcciones`: el cliente tenía una sola dirección (`domicilio`, que es
  la fiscal). La mercadería puede ir a varios lados, así que la entrega pasa a
  ser una libreta y el pedido elige de ahí.

El backfill crea una dirección por cliente a partir de su domicilio, marcada como
la propuesta por defecto, para que nadie arranque con la libreta vacía. Las
coordenadas se copian del cliente: ya están geocodificadas y son las mismas.

Revision ID: p0j1direcc001
Revises: o9i0borrador01
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p0j1direcc001"
down_revision: Union[str, None] = "o9i0borrador01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clientes", sa.Column("transporte_habitual", sa.String(length=200), nullable=True))

    op.create_table(
        "cliente_direcciones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("etiqueta", sa.String(length=80), nullable=False),
        sa.Column("direccion", sa.String(length=500), nullable=False),
        sa.Column("localidad_id", sa.Integer(), nullable=True),
        sa.Column("codigo_postal", sa.String(length=20), nullable=True),
        sa.Column("latitud", sa.Float(), nullable=True),
        sa.Column("longitud", sa.Float(), nullable=True),
        sa.Column("es_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["localidad_id"], ["localidades.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cliente_direcciones_cliente_id", "cliente_direcciones", ["cliente_id"], unique=False
    )

    # Una dirección por cliente, tomada de su domicilio actual.
    op.execute(
        """
        INSERT INTO cliente_direcciones
            (cliente_id, etiqueta, direccion, localidad_id, latitud, longitud, es_default, activo)
        SELECT id, 'Principal', domicilio, localidad_id, latitud, longitud, true, true
        FROM clientes
        WHERE domicilio IS NOT NULL AND btrim(domicilio) <> ''
        """
    )

    op.add_column("pedidos", sa.Column("direccion_entrega_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_pedidos_direccion_entrega",
        "pedidos",
        "cliente_direcciones",
        ["direccion_entrega_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_pedidos_direccion_entrega", "pedidos", type_="foreignkey")
    op.drop_column("pedidos", "direccion_entrega_id")
    op.drop_index("ix_cliente_direcciones_cliente_id", table_name="cliente_direcciones")
    op.drop_table("cliente_direcciones")
    op.drop_column("clientes", "transporte_habitual")

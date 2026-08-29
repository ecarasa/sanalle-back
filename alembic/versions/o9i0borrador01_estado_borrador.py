"""estado borrador y pedidos que no mueven stock

Dos cambios que van juntos porque los dos separan "pedido que se está cargando"
de "venta real":

1. `borrador`: hoy el alta de un pedido lo crea directamente en `pendiente`
   apenas se elige el cliente, así que un pedido a medio tipear ya suma a la
   deuda del cliente, al dashboard y a la cola de depósito. Con el estado nuevo
   adelante, ventas carga en `borrador` y recién al finalizar pasa a `pendiente`.

2. `reserva_stock`: permite cargar un pedido sin comprometer mercadería, para
   las operaciones de volumen que se facturan antes de que entre el ingreso del
   proveedor. Cuando la mercadería entra se vuelve a prender y ahí se reserva.

Los pedidos que ya existen NO se tocan: los `pendiente` de hoy son pedidos
reales terminados y se quedan donde están.

Revision ID: o9i0borrador01
Revises: n8h9blistervta
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o9i0borrador01"
down_revision: Union[str, None] = "n8h9blistervta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Orden final del enum, para poder recrearlo en el downgrade.
ESTADOS_SIN_BORRADOR = (
    "pendiente",
    "en_preparacion",
    "listo_para_despacho",
    "en_camino",
    "entregado",
    "cancelado",
)


def upgrade() -> None:
    # `ALTER TYPE ... ADD VALUE` no puede correr dentro de una transacción, y
    # Alembic envuelve la migración en una. El autocommit_block la corta.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE estadodespacho ADD VALUE IF NOT EXISTS 'borrador' BEFORE 'pendiente'")

    # El pedido nuevo nace en borrador. El default del modelo ya es ese; esto
    # alinea la base para cualquier insert que no lo mande explícito.
    op.execute("ALTER TABLE pedidos ALTER COLUMN shipping_status SET DEFAULT 'borrador'")

    op.add_column(
        "pedidos",
        sa.Column(
            "reserva_stock",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("pedidos", "reserva_stock")

    # Postgres no sabe quitar un valor de un enum: hay que recrear el tipo. Los
    # borradores pasan a `pendiente`, que es donde vivían antes de esta migración.
    op.execute("UPDATE pedidos SET shipping_status = 'pendiente' WHERE shipping_status = 'borrador'")

    valores = ", ".join(f"'{e}'" for e in ESTADOS_SIN_BORRADOR)
    op.execute("ALTER TYPE estadodespacho RENAME TO estadodespacho_old")
    op.execute(f"CREATE TYPE estadodespacho AS ENUM ({valores})")
    op.execute(
        "ALTER TABLE pedidos ALTER COLUMN shipping_status DROP DEFAULT"
    )
    op.execute(
        "ALTER TABLE pedidos ALTER COLUMN shipping_status "
        "TYPE estadodespacho USING shipping_status::text::estadodespacho"
    )
    op.execute(
        "ALTER TABLE pedidos ALTER COLUMN shipping_status SET DEFAULT 'pendiente'"
    )
    op.execute("DROP TYPE estadodespacho_old")

"""plan de cobro del pedido: formas de pago y cuentas destino

Hasta ahora un pedido tenía una sola condición de pago (y encima heredada del
cliente, no propia) y ninguna forma de indicar a qué cuenta entra la plata. Los
pedidos que se cobran mezclando transferencia y efectivo, o que se derivan a
varias cuentas, había que anotarlos en la observación.

`pedido_plan_pago` guarda una fila por tramo: forma + cuenta + importe. Es
INFORMATIVO: no crea pagos ni toca cuenta corriente ni el ledger. La cobranza
real sigue entrando por Pagos.

Se siembran también los valores de combo de `condicion_pago` y `transporte` si
la tabla `entidades` no tiene ninguno, para que los desplegables no arranquen
vacíos.

Revision ID: q1k2planpago1
Revises: p0j1direcc001
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "q1k2planpago1"
down_revision: Union[str, None] = "p0j1direcc001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEMILLAS = {
    "condicion_pago": ["Contado", "Transferencia", "Efectivo", "Cheque", "Plazo"],
    "transporte": ["Propio", "OCA", "Andreani", "Retira el cliente"],
}


def upgrade() -> None:
    op.create_table(
        "pedido_plan_pago",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pedido_id", sa.Integer(), nullable=False),
        sa.Column("forma", sa.String(length=40), nullable=False),
        sa.Column("cuenta_id", sa.Integer(), nullable=True),
        sa.Column("importe", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pedido_id"], ["pedidos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cuenta_id"], ["cuentas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pedido_plan_pago_pedido_id", "pedido_plan_pago", ["pedido_id"], unique=False)
    op.create_index("ix_pedido_plan_pago_cuenta_id", "pedido_plan_pago", ["cuenta_id"], unique=False)

    # Solo si la categoría está vacía: si alguien ya cargó sus propios valores,
    # no se le agregan otros por atrás.
    conn = op.get_bind()
    for categoria, nombres in SEMILLAS.items():
        existentes = conn.execute(
            sa.text("SELECT count(*) FROM entidades WHERE categoria = :c"),
            {"c": categoria},
        ).scalar_one()
        if existentes:
            continue
        for orden, nombre in enumerate(nombres, start=1):
            conn.execute(
                sa.text(
                    "INSERT INTO entidades (categoria, nombre, orden, activo) "
                    "VALUES (CAST(:c AS varchar), CAST(:n AS varchar), :o, true) "
                    "ON CONFLICT (categoria, nombre) DO NOTHING"
                ),
                {"c": categoria, "n": nombre, "o": orden},
            )


def downgrade() -> None:
    op.drop_index("ix_pedido_plan_pago_cuenta_id", table_name="pedido_plan_pago")
    op.drop_index("ix_pedido_plan_pago_pedido_id", table_name="pedido_plan_pago")
    op.drop_table("pedido_plan_pago")
    # Las semillas de `entidades` no se borran: pueden haberse usado en pedidos
    # y son valores de combo, no datos de esta tabla.

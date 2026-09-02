"""modalidad de entrega del pedido: retira por depósito o envío a domicilio

Hasta ahora la única pista de cómo se entregaba un pedido era el texto libre de
`transporte`, donde "Retira el cliente" es apenas uno de los valores sugeridos.
De la modalidad dependen qué dirección sale impresa en el remito y cuántas
copias se emiten (el transporte pide tres), así que no puede quedar atada a lo
que alguien haya tipeado.

Los pedidos existentes quedan en `envio`, salvo aquellos cuyo transporte
menciona un retiro: es el único indicio que dejaron y sólo afecta cómo se
reimprime un remito viejo, nunca plata ni stock.

Revision ID: r2l3modalidad1
Revises: q1k2planpago1
Create Date: 2026-09-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "r2l3modalidad1"
down_revision: Union[str, None] = "q1k2planpago1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Con `server_default` el ADD COLUMN NOT NULL no reescribe la tabla.
    op.add_column(
        "pedidos",
        sa.Column("modalidad_entrega", sa.String(length=20), nullable=False, server_default="envio"),
    )
    op.create_index("ix_pedidos_modalidad_entrega", "pedidos", ["modalidad_entrega"], unique=False)
    op.create_check_constraint(
        "ck_pedidos_modalidad_entrega",
        "pedidos",
        "modalidad_entrega IN ('envio', 'retira')",
    )
    op.execute(
        "UPDATE pedidos SET modalidad_entrega = 'retira' WHERE transporte ILIKE '%retira%'"
    )


def downgrade() -> None:
    op.drop_constraint("ck_pedidos_modalidad_entrega", "pedidos", type_="check")
    op.drop_index("ix_pedidos_modalidad_entrega", table_name="pedidos")
    op.drop_column("pedidos", "modalidad_entrega")

"""forma de pago en el pedido, reemplazando el plan de cobro multi-tramo

El "Cómo paga" pedía forma, cuenta destino e importe por cada parte del cobro.
Era más de lo que ventas necesita al tomar el pedido y en la práctica quedaba
vacío. Se reemplaza por un solo campo: efectivo, transferencia o cheque.

Los valores son los de `TipoPago` (app/models/pago.py) para que, cuando después
se registre el cobro de verdad, la forma coincida sin traducir entre dos
vocabularios.

La tabla `pedido_plan_pago` NO se borra: los pedidos viejos que tengan un plan
cargado lo conservan y el remito lo sigue imprimiendo. Sólo deja de ofrecerse en
el formulario.

Revision ID: z0t1formapago
Revises: y9s0provcuenta
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "z0t1formapago"
down_revision: Union[str, None] = "y9s0provcuenta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pedidos", sa.Column("forma_pago", sa.String(length=30), nullable=True))

    # Backfill desde el plan viejo: si un pedido tenía un solo tramo y su forma es
    # una de las tres que ahora se ofrecen, se hereda. Los de varios tramos quedan
    # en NULL a propósito — no hay una sola forma que los represente, y el remito
    # les sigue imprimiendo el plan completo.
    op.execute(
        """
        UPDATE pedidos p
        SET forma_pago = lower(trim(t.forma))
        FROM (
            SELECT pedido_id, min(forma) AS forma
            FROM pedido_plan_pago
            GROUP BY pedido_id
            HAVING count(*) = 1
        ) t
        WHERE t.pedido_id = p.id
          AND lower(trim(t.forma)) IN ('efectivo', 'transferencia', 'cheque')
        """
    )


def downgrade() -> None:
    op.drop_column("pedidos", "forma_pago")

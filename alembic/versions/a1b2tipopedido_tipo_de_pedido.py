"""tipo_pedido: separar cotizaciones de pedidos con un campo explícito

Hasta ahora "es una cotización" se inferia de `shipping_status == 'borrador'`,
lo que se filtraba con un booleano opt-in (`excluir_borradores`) fácil de
olvidar en un endpoint nuevo (de hecho el calendario de cobros y la pantalla de
Entregas lo tenían sin filtrar). Se agrega `tipo_pedido`, que es un trinquete:
arranca en 'cotizacion' y pasa a 'pedido' sólo al confirmarse
(borrador -> pendiente), y no vuelve atrás aunque el pedido se cancele o se
reabra a borrador después. Ver el comentario en app/models/pedido.py.

Backfill: se usa la bitácora (evento cambio_estado_despacho, campo
shipping_status, valor_nuevo pendiente) en vez de mirar el shipping_status
actual, porque un pedido puede haber pasado borrador -> cancelado directo sin
haberse confirmado nunca, y ese caso tiene que seguir siendo cotización.

Revision ID: a1b2tipopedido
Revises: z0t1formapago
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2tipopedido"
down_revision: Union[str, None] = "z0t1formapago"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pedidos",
        sa.Column(
            "tipo_pedido", sa.String(length=20), nullable=False, server_default="cotizacion"
        ),
    )
    op.create_index("ix_pedidos_tipo_pedido", "pedidos", ["tipo_pedido"])

    op.execute(
        """
        UPDATE pedidos p
        SET tipo_pedido = 'pedido'
        WHERE EXISTS (
            SELECT 1 FROM bitacora_pedidos b
            WHERE b.pedido_id = p.id
              AND b.evento = 'cambio_estado_despacho'
              AND b.campo = 'shipping_status'
              AND b.valor_nuevo = 'pendiente'
        )
        -- Fallback para pedidos sin bitácora (datos de seed/importados viejos):
        -- si ya está en un estado que sólo se llega pasando por 'pendiente',
        -- fue confirmado alguna vez.
        OR p.shipping_status NOT IN ('borrador', 'cancelado')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_pedidos_tipo_pedido", table_name="pedidos")
    op.drop_column("pedidos", "tipo_pedido")

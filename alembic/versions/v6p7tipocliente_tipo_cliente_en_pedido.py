"""tipo de cliente en el pedido, separado de la lista de precios

`pedidos.tipo_precio` venía mezclando dos cosas: con qué columna de precios se
cotizó, y qué clase de venta es. Se separan porque no siempre coinciden — una
venta minorista puede facturarse a precio mayorista por volumen o por excepción —
y las estadísticas comerciales necesitan la segunda, no la primera.

De paso normaliza `clientes.tipo`, que es texto libre: el form de pedidos siembra
la lista de precios a partir de ese valor y con un "MAYORISTA" heredado caía en
silencio a minorista, cotizando al cliente equivocado.

Revision ID: v6p7tipocliente
Revises: u5o6cotizastock
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "v6p7tipocliente"
down_revision: Union[str, None] = "u5o6cotizastock"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Espeja `pricing_service.GRUPOS`. Va literal y no importado porque una migración
# tiene que seguir corriendo igual dentro de un año, aunque el código cambie.
GRUPOS_SQL = "('minorista', 'mayorista', 'comercio')"


def upgrade() -> None:
    op.add_column("pedidos", sa.Column("tipo_cliente", sa.String(length=20), nullable=True))

    # 1) Normalizar el tipo del cliente ANTES del backfill, o el pedido heredaría
    #    la misma basura que estamos limpiando.
    op.execute("UPDATE clientes SET tipo = lower(trim(tipo)) WHERE tipo IS NOT NULL")
    op.execute(f"UPDATE clientes SET tipo = NULL WHERE tipo IS NOT NULL AND tipo NOT IN {GRUPOS_SQL}")

    # 2) Los pedidos históricos heredan el tipo actual del cliente. Es una
    #    aproximación —el cliente pudo cambiar de categoría desde entonces— pero
    #    es mejor dato que NULL y no hay forma de reconstruir el de aquel día.
    op.execute(
        """
        UPDATE pedidos p
        SET tipo_cliente = c.tipo
        FROM clientes c
        WHERE c.id = p.cliente_id AND c.tipo IS NOT NULL
        """
    )


def downgrade() -> None:
    # La normalización de `clientes.tipo` no se revierte: no se guardó el valor
    # original y volver a "MAYORISTA" sería reintroducir el bug a mano.
    op.drop_column("pedidos", "tipo_cliente")

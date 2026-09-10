"""cotizaciones sin reserva: liberar el stock que retienen los borradores

Hasta acá un `borrador` reservaba mercadería igual que un pedido confirmado, así
que una cotización abandonada retenía stock que nadie iba a comprar. Ahora la
reserva la decide el estado y arranca recién en `pendiente`, pero las reservas
que ya están hechas siguen en la base: hay que devolverlas.

Sólo mueve datos, no toca el esquema.

Diferencia intencional con `stock_service.liberar_reserva`: esa función suma la
cantidad completa al físico pero resta sólo `min(cantidad, reservado)` del
reservado, y si la reserva quedó corta por un ajuste manual termina inflando el
stock. Acá se usa `a_liberar = LEAST(pedido, reservado)` de los DOS lados, así el
físico sólo puede subir lo que realmente estaba reservado. Nunca inventa.

Revision ID: u5o6cotizastock
Revises: t4n5bitaprod1
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op


revision: str = "u5o6cotizastock"
down_revision: Union[str, None] = "t4n5bitaprod1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Todo en blísters, que es la unidad interna del stock, y se re-normaliza a
# (cajas, blísters) al final — igual que `StockProductoDeposito.set_total_*`.
# Se usa MOD() y no el operador `%`: alembic corre sobre asyncpg y el escapado
# de `%` depende del paramstyle del driver. MOD() no tiene esa ambigüedad.
LIBERAR_BORRADORES = """
WITH por_caja AS (
    SELECT id, GREATEST(COALESCE(blisters_por_caja, 1), 1) AS bpc
    FROM productos
),
pedido_borradores AS (
    SELECT pi.producto_id,
           pi.deposito_id,
           SUM(pi.cantidad_cajas * pc.bpc + pi.cantidad_blisters) AS blisters
    FROM pedido_items pi
    JOIN pedidos ped ON ped.id = pi.pedido_id
    JOIN por_caja pc ON pc.id = pi.producto_id
    WHERE ped.shipping_status = 'borrador'
      AND ped.reserva_stock IS TRUE
      AND pi.deposito_id IS NOT NULL
    GROUP BY pi.producto_id, pi.deposito_id
),
calculo AS (
    SELECT s.producto_id,
           s.deposito_id,
           pc.bpc,
           s.cajas * pc.bpc + s.blisters                     AS fisico,
           s.reservado_cajas * pc.bpc + s.reservado_blisters AS reservado,
           LEAST(
               pb.blisters,
               s.reservado_cajas * pc.bpc + s.reservado_blisters
           ) AS a_liberar
    FROM stock_producto_deposito s
    JOIN pedido_borradores pb
      ON pb.producto_id = s.producto_id AND pb.deposito_id = s.deposito_id
    JOIN por_caja pc ON pc.id = s.producto_id
)
UPDATE stock_producto_deposito s
SET reservado_cajas    = (c.reservado - c.a_liberar) / c.bpc,
    reservado_blisters = MOD(c.reservado - c.a_liberar, c.bpc),
    cajas              = (c.fisico + c.a_liberar) / c.bpc,
    blisters           = MOD(c.fisico + c.a_liberar, c.bpc)
FROM calculo c
WHERE s.producto_id = c.producto_id
  AND s.deposito_id = c.deposito_id
  AND c.a_liberar > 0
"""


def upgrade() -> None:
    op.execute(LIBERAR_BORRADORES)


def downgrade() -> None:
    """No-op a propósito.

    Volver a reservar no es reversible con seguridad: entre la migración y el
    rollback esa mercadería pudo venderse, y re-comprometerla dejaría el stock
    físico en negativo o le sacaría producto a un pedido real. Si hace falta
    volver atrás, el camino es restaurar el backup de `stock_producto_deposito`.
    """

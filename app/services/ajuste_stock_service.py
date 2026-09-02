"""Mover stock y dejar el movimiento, en un solo lugar.

Antes este par estaba copiado en tres routers (ajuste manual, ingreso de
mercadería, notas) y directamente ausente en un cuarto (la importación de
productos, que cambiaba existencias sin dejar rastro). Todo lo que mueva stock
por una corrección debería pasar por acá.
"""

from __future__ import annotations

from typing import Literal

from app.models.movimiento_stock import MovimientoStock
from app.models.producto import Producto
from app.models.stock_producto_deposito import StockProductoDeposito
from app.services import stock_service


async def registrar_ajuste(
    db,
    *,
    producto: Producto,
    deposito_id: int,
    cajas: int,
    blisters: int,
    modo: Literal["delta", "absoluto"] = "delta",
    motivo: str,
    usuario_id: int,
    observacion: str | None = None,
    toma_inventario_id: int | None = None,
) -> tuple[StockProductoDeposito, MovimientoStock | None]:
    """Aplica el ajuste y devuelve (fila de stock, movimiento).

    El movimiento es None cuando el ajuste no cambió nada: un no-cambio no se
    audita, y en una importación de 3000 filas la mayoría no cambia nada.

    En modo absoluto la diferencia se calcula ANTES de escribir. Es el punto
    entero de auditar un "dejalo en 40": sin eso el movimiento no dice cuánta
    mercadería se movió, que es la única pregunta que se le hace después.
    """
    por_caja = producto.get_blisters_por_caja
    fila = await stock_service.obtener_o_crear_fila(db, producto.id, deposito_id)
    antes = fila.total_blisters(por_caja)
    pedido = stock_service.a_blisters(producto, cajas, blisters)

    if modo == "absoluto":
        delta = pedido - antes
    else:
        delta = pedido

    if delta == 0:
        return fila, None

    # `ajustar` valida que no quede negativo y vuelve a tomar la fila con lock.
    d_cajas, d_sueltos = divmod(abs(delta), por_caja)
    fila = await stock_service.ajustar(
        db,
        producto,
        deposito_id,
        d_cajas if delta > 0 else -d_cajas,
        d_sueltos if delta > 0 else -d_sueltos,
    )

    # Cantidades siempre positivas: la dirección la da origen/destino, como en
    # los movimientos de ingreso. Guardarlas con signo *y además* invertir los
    # depósitos era información redundante y ambigua.
    movimiento = MovimientoStock(
        producto_id=producto.id,
        usuario_id=usuario_id,
        tipo_operacion="ADJUST",
        deposito_origen_id=None if delta > 0 else deposito_id,
        deposito_destino_id=deposito_id if delta > 0 else None,
        cantidad_cajas=d_cajas,
        cantidad_blisters=d_sueltos,
        motivo=motivo,
        toma_inventario_id=toma_inventario_id,
        observacion=observacion,
    )
    db.add(movimiento)
    return fila, movimiento

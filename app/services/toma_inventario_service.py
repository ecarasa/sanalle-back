"""Toma de inventario: abrir el conteo, guardarlo y aplicarlo."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, func, insert, literal, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deposito import Deposito
from app.models.producto import Producto
from app.models.stock_producto_deposito import StockProductoDeposito
from app.models.toma_inventario import TomaInventario, TomaInventarioItem
from app.services import ajuste_stock_service, stock_service


async def _siguiente_numero(db: AsyncSession) -> str:
    """TOM-00001, mismo criterio que la numeración de ingresos."""
    ultimo = (
        await db.execute(select(func.max(TomaInventario.numero)))
    ).scalar_one_or_none()
    n = int(ultimo.split("-")[1]) + 1 if ultimo and "-" in ultimo else 1
    return f"TOM-{n:05d}"


async def abrir(
    db: AsyncSession,
    *,
    deposito_id: int,
    usuario_id: int,
    fecha: date | None = None,
    observacion: str | None = None,
    laboratorio_id: int | None = None,
    categoria: str | None = None,
    solo_con_stock: bool = False,
) -> tuple[TomaInventario, int]:
    """Crea la toma y siembra sus líneas con la foto del stock actual."""
    deposito = await stock_service.validar_deposito(db, deposito_id)

    toma = TomaInventario(
        numero=await _siguiente_numero(db),
        deposito_id=deposito.id,
        estado="borrador",
        origen="manual",
        fecha=fecha or date.today(),
        observacion=observacion,
        creado_por_id=usuario_id,
    )
    db.add(toma)
    await db.flush()

    # Un solo INSERT ... SELECT: son miles de productos y hacerlo con el ORM
    # fila por fila tardaba lo que dura la paciencia del que abre el conteo.
    origen = (
        select(
            literal(toma.id),
            Producto.id,
            func.coalesce(StockProductoDeposito.cajas, 0),
            func.coalesce(StockProductoDeposito.blisters, 0),
        )
        .select_from(Producto)
        .outerjoin(
            StockProductoDeposito,
            and_(
                StockProductoDeposito.producto_id == Producto.id,
                StockProductoDeposito.deposito_id == deposito.id,
            ),
        )
        .where(Producto.activo.is_(True))
    )
    if laboratorio_id:
        origen = origen.where(Producto.laboratorio_id == laboratorio_id)
    if categoria:
        origen = origen.where(Producto.categoria_producto.ilike(categoria))
    if solo_con_stock:
        origen = origen.where(
            func.coalesce(StockProductoDeposito.cajas, 0)
            + func.coalesce(StockProductoDeposito.blisters, 0)
            > 0
        )

    await db.execute(
        insert(TomaInventarioItem).from_select(
            ["toma_id", "producto_id", "esperado_cajas", "esperado_blisters"], origen
        )
    )
    total = (
        await db.execute(
            select(func.count()).select_from(TomaInventarioItem).where(
                TomaInventarioItem.toma_id == toma.id
            )
        )
    ).scalar_one()
    return toma, total


async def guardar_conteo(
    db: AsyncSession, *, toma: TomaInventario, items: list, usuario_id: int
) -> int:
    """Upsert parcial de lo contado. Es el autosave de la planilla."""
    if toma.estado != "borrador":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La toma {toma.numero} ya está {toma.estado}: no se puede seguir contando.",
        )
    ahora = datetime.now(timezone.utc)
    guardadas = 0
    for item in items:
        res = await db.execute(
            update(TomaInventarioItem)
            .where(
                TomaInventarioItem.toma_id == toma.id,
                TomaInventarioItem.producto_id == item.producto_id,
            )
            .values(
                contado_cajas=item.contado_cajas,
                contado_blisters=item.contado_blisters,
                contado_por_id=usuario_id,
                contado_at=ahora,
            )
        )
        guardadas += res.rowcount or 0
    return guardadas


async def _lineas_con_actual(db: AsyncSession, toma: TomaInventario):
    """Líneas de la toma junto con el stock de AHORA y el producto."""
    filas = await db.execute(
        select(TomaInventarioItem, Producto, StockProductoDeposito)
        .join(Producto, Producto.id == TomaInventarioItem.producto_id)
        .outerjoin(
            StockProductoDeposito,
            and_(
                StockProductoDeposito.producto_id == TomaInventarioItem.producto_id,
                StockProductoDeposito.deposito_id == toma.deposito_id,
            ),
        )
        .where(TomaInventarioItem.toma_id == toma.id)
        # Orden determinístico de bloqueo: evita deadlocks contra una venta que
        # esté tocando los mismos productos en otro orden.
        .order_by(TomaInventarioItem.producto_id)
    )
    return filas.all()


def _diferencia(item: TomaInventarioItem, producto: Producto, fila) -> tuple[int, int, bool]:
    """(contado_bl, actual_bl, se_movió_durante_el_conteo)."""
    por_caja = producto.get_blisters_por_caja
    actual_bl = (fila.cajas * por_caja + fila.blisters) if fila else 0
    esperado_bl = item.esperado_cajas * por_caja + item.esperado_blisters
    contado_bl = (
        (item.contado_cajas or 0) * por_caja + (item.contado_blisters or 0)
        if item.contado_cajas is not None or item.contado_blisters is not None
        else None
    )
    return contado_bl, actual_bl, actual_bl != esperado_bl


async def resumen(db: AsyncSession, toma: TomaInventario, lineas=None) -> dict:
    """`lineas` se puede pasar ya cargado: abrir la pantalla leía la toma dos veces."""
    if lineas is None:
        lineas = await _lineas_con_actual(db, toma)
    aplicada = toma.estado == "aplicada"
    res = {
        "lineas": len(lineas),
        "contadas": 0,
        "con_diferencia": 0,
        "delta_positivo_blisters": 0,
        "delta_negativo_blisters": 0,
        "movidas_durante_conteo": 0,
    }
    for item, producto, fila in lineas:
        contado_bl, actual_bl, movido = _diferencia(item, producto, fila)
        if contado_bl is None:
            continue
        res["contadas"] += 1
        if movido and not aplicada:
            res["movidas_durante_conteo"] += 1
        # Ya aplicada, el resumen tiene que mostrar lo que se aplicó y no una
        # diferencia nueva contra el stock de hoy.
        delta = item.aplicado_delta_blisters if aplicada else contado_bl - actual_bl
        if delta is None:
            continue
        if delta:
            res["con_diferencia"] += 1
            if delta > 0:
                res["delta_positivo_blisters"] += delta
            else:
                res["delta_negativo_blisters"] += -delta
    return res


async def aplicar(
    db: AsyncSession,
    *,
    toma: TomaInventario,
    usuario_id: int,
    observacion: str | None = None,
    confirmar_movidas: bool = False,
) -> dict:
    """Deja el stock en lo contado y escribe un movimiento por diferencia.

    Se aplica contra el stock del momento de aplicar y no contra la foto: un
    recuento físico es absoluto, lo que dice el papel manda. Por eso mismo, si un
    producto se movió mientras se contaba hay que confirmarlo a mano: esa venta
    se estaría borrando.
    """
    if toma.estado != "borrador":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La toma {toma.numero} ya está {toma.estado}.",
        )

    lineas = await _lineas_con_actual(db, toma)

    movidas = [
        (item, producto)
        for item, producto, fila in lineas
        if _diferencia(item, producto, fila)[0] is not None
        and _diferencia(item, producto, fila)[2]
    ]
    if movidas and not confirmar_movidas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{len(movidas)} producto(s) se movieron desde que empezó el conteo "
                f"(por ejemplo {movidas[0][1].nombre}). Revisá y confirmá para aplicar igual."
            ),
        )

    aplicados = 0
    delta_pos = 0
    delta_neg = 0
    for item, producto, fila in lineas:
        contado_bl, actual_bl, _ = _diferencia(item, producto, fila)
        if contado_bl is None or contado_bl == actual_bl:
            item.aplicado_delta_blisters = 0 if contado_bl is not None else None
            continue

        _, movimiento = await ajuste_stock_service.registrar_ajuste(
            db,
            producto=producto,
            deposito_id=toma.deposito_id,
            cajas=item.contado_cajas or 0,
            blisters=item.contado_blisters or 0,
            modo="absoluto",
            motivo="recuento_fisico",
            usuario_id=usuario_id,
            observacion=(f"Toma {toma.numero}" + (f" · {observacion}" if observacion else ""))[:200],
            toma_inventario_id=toma.id,
        )
        delta = contado_bl - actual_bl
        item.aplicado_delta_blisters = delta
        if delta > 0:
            delta_pos += delta
        else:
            delta_neg += -delta
        if movimiento is not None:
            aplicados += 1

    toma.estado = "aplicada"
    toma.aplicado_por_id = usuario_id
    toma.aplicada_at = datetime.now(timezone.utc)
    if observacion:
        toma.observacion = ((toma.observacion or "") + f"\n{observacion}").strip()

    return {
        "movimientos": aplicados,
        "delta_positivo_blisters": delta_pos,
        "delta_negativo_blisters": delta_neg,
        "movidas_durante_conteo": len(movidas),
    }

"""Toda la aritmética de stock, en un solo lugar.

El stock de un producto vive en `stock_producto_deposito`: una fila por
(producto, depósito). No hay columnas de stock en `productos`.

Cada fila tiene dos bolsas:

- **físico** (`cajas`/`blisters`): lo que hay en la góndola y se puede vender.
- **reservado** (`reservado_*`): lo comprometido en pedidos creados y no entregados.

El ciclo de un pedido mueve stock entre esas bolsas y nunca las duplica:

    crear pedido      físico -> reservado     (reservar)
    entregar          reservado -> fuera      (consumir_reserva)
    cancelar/borrar   reservado -> físico     (liberar_reserva)

Todas las funciones que escriben toman la fila con `FOR UPDATE`, así dos ventas
simultáneas del mismo producto se serializan y no pueden sobrevender.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deposito import Deposito
from app.models.producto import Producto
from app.models.stock_producto_deposito import StockProductoDeposito


class StockInsuficiente(HTTPException):
    """400 con un mensaje que le sirve al vendedor: qué falta y dónde."""

    def __init__(self, producto: Producto, deposito_nombre: str, pedido_blisters: int, disponible_blisters: int):
        por_caja = producto.get_blisters_por_caja
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Stock insuficiente de {producto.nombre} en {deposito_nombre}: "
                f"disponible {_fmt(disponible_blisters, por_caja)}, "
                f"se pidieron {_fmt(pedido_blisters, por_caja)}."
            ),
        )


def _fmt(blisters_totales: int, por_caja: int) -> str:
    """'3 cajas + 2 blísters' — o solo cajas cuando el producto no fracciona."""
    if por_caja <= 1:
        return f"{blisters_totales} caja(s)"
    cajas, sueltos = divmod(blisters_totales, por_caja)
    if sueltos == 0:
        return f"{cajas} caja(s)"
    if cajas == 0:
        return f"{sueltos} blíster(s)"
    return f"{cajas} caja(s) + {sueltos} blíster(s)"


def a_blisters(producto: Producto, cajas: int, blisters: int) -> int:
    """Convierte una cantidad mixta a la unidad interna (blísters)."""
    return cajas * producto.get_blisters_por_caja + blisters


@dataclass(frozen=True)
class StockDeposito:
    """Vista de solo lectura del stock de un producto en un depósito."""

    deposito_id: int
    nombre: str | None
    orden: int
    activo: bool
    cajas: int
    blisters: int
    reservado_cajas: int
    reservado_blisters: int
    total_blisters: int
    reservado_blisters_total: int


# --- Lectura -----------------------------------------------------------------


async def obtener_fila(
    db: AsyncSession,
    producto_id: int,
    deposito_id: int,
    *,
    lock: bool = False,
) -> StockProductoDeposito | None:
    q = select(StockProductoDeposito).where(
        StockProductoDeposito.producto_id == producto_id,
        StockProductoDeposito.deposito_id == deposito_id,
    )
    if lock:
        # selectin de `deposito` no convive con FOR UPDATE en la misma consulta.
        q = q.execution_options(populate_existing=True).with_for_update(of=StockProductoDeposito)
    return (await db.execute(q)).scalars().first()


async def obtener_o_crear_fila(
    db: AsyncSession,
    producto_id: int,
    deposito_id: int,
    *,
    lock: bool = True,
) -> StockProductoDeposito:
    """La fila producto×depósito se crea al primer movimiento, no al crear el producto.

    Así un depósito nuevo no obliga a escribir una fila en cero para los miles de
    productos que nunca van a pasar por ahí.
    """
    fila = await obtener_fila(db, producto_id, deposito_id, lock=lock)
    if fila is None:
        fila = StockProductoDeposito(
            producto_id=producto_id,
            deposito_id=deposito_id,
            cajas=0,
            blisters=0,
            reservado_cajas=0,
            reservado_blisters=0,
        )
        db.add(fila)
        await db.flush()
    return fila


async def disponible_blisters(db: AsyncSession, producto_id: int, deposito_id: int) -> int:
    """Stock físico (vendible) del producto en ese depósito, en blísters."""
    fila = await obtener_fila(db, producto_id, deposito_id)
    if fila is None:
        return 0
    producto = await db.get(Producto, producto_id)
    if producto is None:
        return 0
    return fila.total_blisters(producto.get_blisters_por_caja)


async def stocks_de_producto(db: AsyncSession, producto_id: int) -> list[StockDeposito]:
    """Stock del producto en todos sus depósitos, ordenado como el maestro."""
    producto = await db.get(Producto, producto_id)
    por_caja = producto.get_blisters_por_caja if producto else 1
    filas = (
        await db.execute(
            select(StockProductoDeposito, Deposito)
            .join(Deposito, Deposito.id == StockProductoDeposito.deposito_id)
            .where(StockProductoDeposito.producto_id == producto_id)
            .order_by(Deposito.orden, Deposito.id)
        )
    ).all()
    return [
        StockDeposito(
            deposito_id=dep.id,
            nombre=dep.nombre,
            orden=dep.orden,
            activo=dep.activo,
            cajas=fila.cajas,
            blisters=fila.blisters,
            reservado_cajas=fila.reservado_cajas,
            reservado_blisters=fila.reservado_blisters,
            total_blisters=fila.total_blisters(por_caja),
            reservado_blisters_total=fila.total_reservado_blisters(por_caja),
        )
        for fila, dep in filas
    ]


async def nombre_deposito(db: AsyncSession, deposito_id: int) -> str:
    dep = await db.get(Deposito, deposito_id)
    return dep.nombre if dep else f"depósito #{deposito_id}"


async def validar_deposito(db: AsyncSession, deposito_id: int | None) -> Deposito:
    """Un movimiento de stock siempre tiene depósito: sin él no sabemos de dónde sale."""
    if deposito_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Falta indicar el depósito del que sale la mercadería.",
        )
    dep = await db.get(Deposito, deposito_id)
    if dep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Depósito no encontrado")
    return dep


# --- Escritura ---------------------------------------------------------------


async def ajustar(
    db: AsyncSession,
    producto: Producto,
    deposito_id: int,
    cajas: int,
    blisters: int,
) -> StockProductoDeposito:
    """Suma (o resta, con signo negativo) stock físico. Es el ajuste manual y el ingreso."""
    fila = await obtener_o_crear_fila(db, producto.id, deposito_id)
    por_caja = producto.get_blisters_por_caja
    nuevo = fila.total_blisters(por_caja) + a_blisters(producto, cajas, blisters)
    if nuevo < 0:
        raise StockInsuficiente(
            producto,
            await nombre_deposito(db, deposito_id),
            -a_blisters(producto, cajas, blisters),
            fila.total_blisters(por_caja),
        )
    fila.set_total_blisters(nuevo, por_caja)
    return fila


async def establecer(
    db: AsyncSession,
    producto: Producto,
    deposito_id: int,
    cajas: int,
    blisters: int,
) -> StockProductoDeposito:
    """Fija el stock físico en un valor absoluto (importación de planilla).

    Distinto de `ajustar`, que suma un delta. No toca las reservas: si hay pedidos
    abiertos siguen comprometidos, y la planilla solo redefine lo que hay en góndola.
    """
    if cajas < 0 or blisters < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El stock de {producto.nombre} no puede ser negativo.",
        )
    fila = await obtener_o_crear_fila(db, producto.id, deposito_id)
    fila.set_total_blisters(a_blisters(producto, cajas, blisters), producto.get_blisters_por_caja)
    return fila


async def reservar(
    db: AsyncSession,
    producto: Producto,
    deposito_id: int,
    cajas: int,
    blisters: int,
) -> StockProductoDeposito:
    """Compromete stock para un pedido: sale del físico y entra al reservado.

    Es el único punto que puede rechazar una venta por falta de stock, y valida
    antes de mutar nada: si tira, la fila queda intacta.
    """
    fila = await obtener_o_crear_fila(db, producto.id, deposito_id)
    por_caja = producto.get_blisters_por_caja
    pedido = a_blisters(producto, cajas, blisters)
    disponible = fila.total_blisters(por_caja)
    if pedido > disponible:
        raise StockInsuficiente(producto, await nombre_deposito(db, deposito_id), pedido, disponible)

    fila.set_total_blisters(disponible - pedido, por_caja)
    fila.set_total_reservado_blisters(fila.total_reservado_blisters(por_caja) + pedido, por_caja)
    return fila


async def liberar_reserva(
    db: AsyncSession,
    producto: Producto,
    deposito_id: int,
    cajas: int,
    blisters: int,
) -> StockProductoDeposito:
    """Deshace una reserva y devuelve la mercadería al físico (cancelar, borrar, editar)."""
    fila = await obtener_o_crear_fila(db, producto.id, deposito_id)
    por_caja = producto.get_blisters_por_caja
    cantidad = a_blisters(producto, cajas, blisters)
    # La reserva puede haber quedado corta por ajustes manuales hechos a mano
    # mientras el pedido estaba abierto: se libera lo que realmente hay reservado.
    reservado = fila.total_reservado_blisters(por_caja)
    a_liberar = min(cantidad, reservado)
    fila.set_total_reservado_blisters(reservado - a_liberar, por_caja)
    fila.set_total_blisters(fila.total_blisters(por_caja) + cantidad, por_caja)
    return fila


async def consumir_reserva(
    db: AsyncSession,
    producto: Producto,
    deposito_id: int,
    cajas: int,
    blisters: int,
) -> StockProductoDeposito:
    """La mercadería se entregó: la reserva desaparece y el físico no vuelve."""
    fila = await obtener_o_crear_fila(db, producto.id, deposito_id)
    por_caja = producto.get_blisters_por_caja
    reservado = fila.total_reservado_blisters(por_caja)
    a_consumir = min(a_blisters(producto, cajas, blisters), reservado)
    fila.set_total_reservado_blisters(reservado - a_consumir, por_caja)
    return fila


async def transferir(
    db: AsyncSession,
    producto: Producto,
    origen_id: int,
    destino_id: int,
    cajas: int,
    blisters: int,
) -> tuple[StockProductoDeposito, StockProductoDeposito]:
    """Mueve stock físico entre dos depósitos. No toca reservas."""
    if origen_id == destino_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El depósito de origen y el de destino tienen que ser distintos.",
        )
    # Orden fijo de bloqueo por id: dos transferencias cruzadas simultáneas
    # (A->B y B->A) tomarían las filas en orden opuesto y se abrazarían.
    primero, segundo = sorted((origen_id, destino_id))
    await obtener_o_crear_fila(db, producto.id, primero)
    await obtener_o_crear_fila(db, producto.id, segundo)

    fila_origen = await ajustar(db, producto, origen_id, -cajas, -blisters)
    fila_destino = await ajustar(db, producto, destino_id, cajas, blisters)
    return fila_origen, fila_destino

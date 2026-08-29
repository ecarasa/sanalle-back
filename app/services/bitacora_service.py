"""Bitácora de pedidos: registro explícito de quién modificó qué.

Por qué se registra desde el router y no con event listeners de SQLAlchemy:
`PUT /pedidos/{id}` borra y recrea TODOS los items. A nivel ORM, cambiar la cantidad
de un ítem se ve como N deletes + M inserts, así que un listener escribiría
"baja Ibuprofeno / alta Ibuprofeno" en vez de "cantidad: 2 → 5". El diff sólo se
puede hacer en el router, snapshotteando antes de borrar y comparando después de
recrear. Los listeners tampoco tienen acceso al usuario autenticado.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bitacora_pedido import BitacoraPedido
from app.models.pedido import Pedido
from app.models.pedido_item import PedidoItem
from app.models.user import User

CAMPOS_PEDIDO_AUDITADOS: tuple[str, ...] = (
    "shipping_status",
    "payment_status",
    "tipo_documento",
    "fecha_entrega",
    "fecha_compromiso_pago",
    "transporte",
    "vendedor_id",
    "repartidor_id",
    "tipo_precio",
    "observacion",
    "bultos",
    "sociedad",
    "despachado",
    "reserva_stock",
    "importe_total",
)

CAMPOS_ITEM_AUDITADOS: tuple[str, ...] = (
    "cantidad_cajas",
    "cantidad_blisters",
    "unidad_venta",
    "precio_unitario",
    "precio_lista",
    "descuento_porcentaje",
)

# El form de pedidos autoguarda ~1s después de cada tecla. Sin esto, tipear una
# cantidad 1 → 2 → 3 dejaría tres filas. Dentro de esta ventana, un cambio del mismo
# usuario sobre el mismo campo actualiza la fila existente en vez de insertar otra.
COALESCE_WINDOW = timedelta(minutes=2)


def nuevo_grupo_id() -> str:
    return str(uuid.uuid4())


def _fmt(value) -> str | None:
    """Serializa un valor a texto para guardarlo en la bitácora."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if hasattr(value, "value"):  # Enums (EstadoDespacho, EstadoPago, TipoDocumento)
        return str(value.value)
    return str(value)


def snapshot_pedido(pedido: Pedido) -> dict[str, str | None]:
    return {campo: _fmt(getattr(pedido, campo, None)) for campo in CAMPOS_PEDIDO_AUDITADOS}


def snapshot_items(items: Iterable[PedidoItem]) -> dict[int, dict]:
    """{producto_id: {campo: str|None, ..., "_nombre": str|None}}

    Se indexa por producto_id (no por item.id) porque el PUT borra y recrea los items:
    los ids cambian, el producto no. Un producto aparece una sola vez por pedido.
    """
    snap: dict[int, dict] = {}
    for item in items:
        datos = {campo: _fmt(getattr(item, campo, None)) for campo in CAMPOS_ITEM_AUDITADOS}
        datos["_nombre"] = item.producto.nombre if item.producto else None
        snap[item.producto_id] = datos
    return snap


async def _registrar(
    db: AsyncSession,
    *,
    pedido: Pedido,
    usuario: User | None,
    evento: str,
    accion: str,
    entidad: str = "pedido",
    campo: str | None = None,
    valor_anterior: str | None = None,
    valor_nuevo: str | None = None,
    producto_id: int | None = None,
    producto_nombre: str | None = None,
    grupo_id: str | None = None,
    observacion: str | None = None,
    coalesce: bool = False,
) -> BitacoraPedido:
    if coalesce and campo is not None:
        desde = datetime.now(timezone.utc) - COALESCE_WINDOW
        previa = await db.execute(
            select(BitacoraPedido)
            .where(
                BitacoraPedido.pedido_id == pedido.id,
                BitacoraPedido.entidad == entidad,
                BitacoraPedido.campo == campo,
                BitacoraPedido.accion == "modificacion",
                BitacoraPedido.producto_id.is_(producto_id)
                if producto_id is None
                else BitacoraPedido.producto_id == producto_id,
                BitacoraPedido.usuario_id == (usuario.id if usuario else None),
                BitacoraPedido.created_at >= desde,
            )
            .order_by(BitacoraPedido.created_at.desc())
            .limit(1)
        )
        existente = previa.scalar_one_or_none()
        if existente is not None:
            # Se conserva el valor_anterior original: el usuario venía de ese valor.
            existente.valor_nuevo = valor_nuevo
            existente.grupo_id = grupo_id or existente.grupo_id
            return existente

    entrada = BitacoraPedido(
        pedido_id=pedido.id,
        numero_pedido=pedido.numero_pedido,
        usuario_id=usuario.id if usuario else None,
        usuario_nombre=(usuario.nombre_completo if usuario else None),
        evento=evento,
        entidad=entidad,
        accion=accion,
        campo=campo,
        valor_anterior=valor_anterior,
        valor_nuevo=valor_nuevo,
        producto_id=producto_id,
        producto_nombre=producto_nombre,
        grupo_id=grupo_id,
        observacion=observacion,
    )
    db.add(entrada)
    return entrada


async def registrar_evento(
    db: AsyncSession,
    *,
    pedido: Pedido,
    usuario: User | None,
    evento: str,
    accion: str,
    entidad: str = "pedido",
    campo: str | None = None,
    antes=None,
    despues=None,
    producto_id: int | None = None,
    producto_nombre: str | None = None,
    grupo_id: str | None = None,
    observacion: str | None = None,
) -> BitacoraPedido:
    """Registra un evento suelto (creación, eliminación, cambio de estado, etc.)."""
    return await _registrar(
        db,
        pedido=pedido,
        usuario=usuario,
        evento=evento,
        accion=accion,
        entidad=entidad,
        campo=campo,
        valor_anterior=_fmt(antes),
        valor_nuevo=_fmt(despues),
        producto_id=producto_id,
        producto_nombre=producto_nombre,
        grupo_id=grupo_id,
        observacion=observacion,
    )


async def registrar_cambios_pedido(
    db: AsyncSession,
    *,
    pedido: Pedido,
    antes: dict[str, str | None],
    usuario: User | None,
    evento: str = "actualizacion",
    grupo_id: str | None = None,
) -> int:
    """Diff de los campos escalares del pedido contra el snapshot previo."""
    despues = snapshot_pedido(pedido)
    cambios = 0
    for campo in CAMPOS_PEDIDO_AUDITADOS:
        anterior, nuevo = antes.get(campo), despues.get(campo)
        if anterior == nuevo:
            continue
        await _registrar(
            db,
            pedido=pedido,
            usuario=usuario,
            evento=evento,
            accion="modificacion",
            entidad="pedido",
            campo=campo,
            valor_anterior=anterior,
            valor_nuevo=nuevo,
            grupo_id=grupo_id,
            coalesce=(evento == "actualizacion"),
        )
        cambios += 1
    return cambios


async def registrar_diff_items(
    db: AsyncSession,
    *,
    pedido: Pedido,
    antes: dict[int, dict],
    despues: dict[int, dict],
    usuario: User | None,
    grupo_id: str | None = None,
    evento: str = "actualizacion",
) -> int:
    """Alta / baja / modificación de items, comparando por producto_id."""
    cambios = 0

    for producto_id, datos in despues.items():
        if producto_id in antes:
            continue
        await _registrar(
            db,
            pedido=pedido,
            usuario=usuario,
            evento=evento,
            accion="alta",
            entidad="item",
            campo=None,
            valor_nuevo=_resumen_item(datos),
            producto_id=producto_id,
            producto_nombre=datos.get("_nombre"),
            grupo_id=grupo_id,
        )
        cambios += 1

    for producto_id, datos in antes.items():
        if producto_id in despues:
            continue
        await _registrar(
            db,
            pedido=pedido,
            usuario=usuario,
            evento=evento,
            accion="baja",
            entidad="item",
            campo=None,
            valor_anterior=_resumen_item(datos),
            producto_id=producto_id,
            producto_nombre=datos.get("_nombre"),
            grupo_id=grupo_id,
        )
        cambios += 1

    for producto_id, datos_despues in despues.items():
        datos_antes = antes.get(producto_id)
        if datos_antes is None:
            continue
        for campo in CAMPOS_ITEM_AUDITADOS:
            anterior, nuevo = datos_antes.get(campo), datos_despues.get(campo)
            if anterior == nuevo:
                continue
            await _registrar(
                db,
                pedido=pedido,
                usuario=usuario,
                evento=evento,
                accion="modificacion",
                entidad="item",
                campo=campo,
                valor_anterior=anterior,
                valor_nuevo=nuevo,
                producto_id=producto_id,
                producto_nombre=datos_despues.get("_nombre"),
                grupo_id=grupo_id,
                coalesce=(evento == "actualizacion"),
            )
            cambios += 1

    return cambios


def _resumen_item(datos: dict) -> str:
    """'2 cajas + 3 blisters @ $1200.00' — legible en el timeline."""
    partes = []
    cajas = datos.get("cantidad_cajas")
    blisters = datos.get("cantidad_blisters")
    if cajas and cajas != "0":
        partes.append(f"{cajas} caja(s)")
    if blisters and blisters != "0":
        partes.append(f"{blisters} blister(s)")
    cantidad = " + ".join(partes) if partes else "sin cantidad"
    precio = datos.get("precio_unitario")
    return f"{cantidad} @ ${precio}" if precio else cantidad


async def limpiar_borrador(db: AsyncSession, pedido_id: int) -> bool:
    """Borra la bitácora de un pedido que nunca tuvo actividad, y avisa si lo hizo.

    "Sin actividad" es que lo único registrado sea su propia creación: el borrador que
    abre "Nuevo pedido" y el usuario cancela sin cargar nada. Un pedido al que se le
    agregaron y después se le quitaron los ítems SÍ tuvo historia, y esa historia no
    se toca: mirar los ítems que le quedan al momento de borrarlo no alcanza.
    """
    result = await db.execute(
        select(BitacoraPedido).where(BitacoraPedido.pedido_id == pedido_id)
    )
    entradas = result.scalars().all()

    # Sólo la fila de "creé el pedido". Cualquier otra cosa (ítems dados de alta al
    # crearlo, cambios, estados) significa que hubo historia y no se borra.
    if any(e.evento != "creacion" or e.entidad != "pedido" for e in entradas):
        return False

    for entrada in entradas:
        await db.delete(entrada)
    return True

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.cliente import Cliente
from app.models.pago import Pago, TipoPago
from app.models.pedido import Pedido, EstadoPago as EstadoPagoPedido, TIPO_PEDIDO
from app.models.pedido_item import PedidoItem
from app.models.producto import Producto
from app.models.historial_pvp_producto import HistorialPvpProducto
from app.models.ingreso_mercaderia import IngresoMercaderia
from app.models.user import User, RolUsuario
from app.schemas.reporte import (
    PagosPorPedidoRow, PedidoComisionDetalle, VendedorComisionRow,
    HistorialPvpResponse, HistorialPvpRow
)
from app.utils.deps import require_role
from sqlalchemy.orm import selectinload
from collections import defaultdict

router = APIRouter()

TIPO_PAGO_DISPLAY = {
    "efectivo": "Efectivo",
    "cheque": "Cheque",
    "transferencia": "Transferencia",
    "retencion": "Retención",
}


async def _fetch_pagos_por_pedido(
    db: AsyncSession,
    current_user: User,
    search: str = "",
    cliente_id: int | None = None,
    tipo_pago: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> list[PagosPorPedidoRow]:
    """Fetch all pagos-por-pedido rows (no pagination)."""
    stmt = (
        select(
            Cliente.nombre,
            Pedido.id,
            Pedido.fecha,
            Pedido.fecha_entrega,
            Pedido.importe_total,
            Pago.id,
            User.nombre_completo,
            Pago.tipo_pago,
            Pago.fecha_recepcion,
            Pago.ch_banco,
            Pago.ch_vto,
            Pago.importe,
        )
        .select_from(Pedido)
        .join(Cliente, Pedido.cliente_id == Cliente.id)
        .join(Pago, Pago.cliente_id == Pedido.cliente_id)
        .outerjoin(User, Pago.receptor_id == User.id)
    )

    # Role filter
    if current_user.rol.value == "ventas":
        stmt = stmt.where(Pedido.vendedor_id == current_user.id)

    if search:
        stmt = stmt.where(Cliente.nombre.ilike(f"%{search}%"))
    if cliente_id is not None:
        stmt = stmt.where(Pedido.cliente_id == cliente_id)
    if tipo_pago:
        stmt = stmt.where(Pago.tipo_pago == TipoPago(tipo_pago))
    if fecha_desde:
        stmt = stmt.where(Pago.fecha_recepcion >= datetime.fromisoformat(fecha_desde))
    if fecha_hasta:
        stmt = stmt.where(
            Pago.fecha_recepcion <= datetime.fromisoformat(fecha_hasta + "T23:59:59")
        )

    stmt = stmt.order_by(Cliente.nombre, Pedido.id, Pago.fecha_recepcion)

    result = await db.execute(stmt)
    raw_rows = result.all()

    # Compute running saldo per pedido
    rows: list[PagosPorPedidoRow] = []
    running_sums: dict[int, Decimal] = {}  # pedido_id -> running sum of pagos

    for (
        c_nombre,
        pe_id,
        pe_fecha,
        pe_fecha_entrega,
        pe_importe_total,
        pa_id,
        pa_receptor,
        pa_tipo_pago,
        pa_fecha_recep,
        pa_ch_banco,
        pa_ch_vto,
        pa_importe,
    ) in raw_rows:
        if pe_id not in running_sums:
            running_sums[pe_id] = Decimal("0")
        running_sums[pe_id] += pa_importe
        saldo = pe_importe_total - running_sums[pe_id]

        rows.append(
            PagosPorPedidoRow(
                c_nombre=c_nombre,
                a_idpedido=pe_id,
                pe_fecha=str(pe_fecha) if pe_fecha else "",
                pe_fechaentrega=str(pe_fecha_entrega) if pe_fecha_entrega else None,
                pe_importetotal=float(pe_importe_total),
                a_idpago=pa_id,
                pa_receptor=pa_receptor,
                tp_nombre=TIPO_PAGO_DISPLAY.get(
                    pa_tipo_pago.value, pa_tipo_pago.value
                ),
                pa_fecharecep=str(pa_fecha_recep)[:10] if pa_fecha_recep else "",
                pa_chbanco=pa_ch_banco,
                pa_chvto=str(pa_ch_vto) if pa_ch_vto else None,
                a_importe=float(pa_importe),
                a_saldo=float(saldo),
            )
        )

    return rows


@router.get("/pagos-por-pedido")
async def pagos_por_pedido(
    search: str = Query(""),
    cliente_id: int | None = Query(None),
    tipo_pago: str | None = Query(None),
    fecha_desde: str | None = Query(None),
    fecha_hasta: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["super_admin"])),
):
    all_rows = await _fetch_pagos_por_pedido(
        db, current_user, search, cliente_id, tipo_pago, fecha_desde, fecha_hasta
    )
    total = len(all_rows)
    start = (page - 1) * page_size
    end = start + page_size
    items = all_rows[start:end]

    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/pagos-por-pedido/export")
async def export_pagos_por_pedido(
    format: str = Query("excel"),
    search: str = Query(""),
    cliente_id: int | None = Query(None),
    tipo_pago: str | None = Query(None),
    fecha_desde: str | None = Query(None),
    fecha_hasta: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["super_admin"])),
):
    from app.routers.exports import _generate_export

    all_rows = await _fetch_pagos_por_pedido(
        db, current_user, search, cliente_id, tipo_pago, fecha_desde, fecha_hasta
    )

    columns = [
        "Cliente",
        "ID Pedido",
        "Fecha Pedido",
        "Fecha Entrega",
        "Importe Pedido",
        "ID Pago",
        "Receptor",
        "Tipo Pago",
        "Fecha Recep.",
        "Banco",
        "Vto Cheque",
        "Importe Pago",
        "Saldo",
    ]

    export_rows = [
        [
            r.c_nombre,
            r.a_idpedido,
            r.pe_fecha,
            r.pe_fechaentrega or "",
            r.pe_importetotal,
            r.a_idpago,
            r.pa_receptor or "",
            r.tp_nombre,
            r.pa_fecharecep,
            r.pa_chbanco or "",
            r.pa_chvto or "",
            r.a_importe,
            r.a_saldo,
        ]
        for r in all_rows
    ]

    return _generate_export(
        format, "Reporte - Pagos por Pedido", columns, export_rows, "pagos_por_pedido"
    )


@router.get("/calendario")
async def get_calendario_unificado(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """
    Endpoint unificado para el calendario:
    - Entregas de Pedidos
    - Vencimientos de Facturas de Proveedores
    """
    
    # 1. Fetch Entregas (Pedidos)
    # Sólo pedidos confirmados: una cotización sin confirmar no es una entrega
    # comprometida, aunque tenga una fecha_entrega sugerida.
    stmt_pedidos = (
        select(Pedido)
        .options(selectinload(Pedido.cliente))
        .where(Pedido.fecha_entrega.isnot(None))
        .where(Pedido.tipo_pedido == TIPO_PEDIDO)
    )
    if current_user.rol.value == "ventas":
        stmt_pedidos = stmt_pedidos.where(Pedido.vendedor_id == current_user.id)
    
    res_pedidos = await db.execute(stmt_pedidos)
    pedidos = res_pedidos.scalars().all()
    
    # 2. Fetch Vencimientos (Ingresos Mercaderia) — pendientes y parciales
    stmt_venc_pendientes = (
        select(IngresoMercaderia)
        .options(selectinload(IngresoMercaderia.proveedor))
        .where(IngresoMercaderia.fecha_vencimiento.isnot(None))
        .where(IngresoMercaderia.saldo_pendiente > 0)
        .where(IngresoMercaderia.saldo_pendiente == IngresoMercaderia.importe_total)
    )
    stmt_venc_parciales = (
        select(IngresoMercaderia)
        .options(selectinload(IngresoMercaderia.proveedor))
        .where(IngresoMercaderia.fecha_vencimiento.isnot(None))
        .where(IngresoMercaderia.saldo_pendiente > 0)
        .where(IngresoMercaderia.saldo_pendiente < IngresoMercaderia.importe_total)
    )

    # 3. Fetch Cobros (Pedidos por fecha_compromiso_pago) — por estado
    stmt_cobros_pendientes = (
        select(Pedido)
        .options(selectinload(Pedido.cliente))
        .where(Pedido.fecha_compromiso_pago.isnot(None))
        .where(Pedido.payment_status == EstadoPagoPedido.pendiente)
        .where(Pedido.saldo_pendiente > 0)
        .where(Pedido.tipo_pedido == TIPO_PEDIDO)
    )
    stmt_cobros_parciales = (
        select(Pedido)
        .options(selectinload(Pedido.cliente))
        .where(Pedido.fecha_compromiso_pago.isnot(None))
        .where(Pedido.payment_status == EstadoPagoPedido.parcial)
        .where(Pedido.saldo_pendiente > 0)
        .where(Pedido.tipo_pedido == TIPO_PEDIDO)
    )
    stmt_cobros_pagados = (
        select(Pedido)
        .options(selectinload(Pedido.cliente))
        .where(Pedido.fecha_compromiso_pago.isnot(None))
        .where(Pedido.payment_status == EstadoPagoPedido.pagado)
        .where(Pedido.tipo_pedido == TIPO_PEDIDO)
    )

    res_venc_pendientes, res_venc_parciales, res_cobros_pend, res_cobros_parc, res_cobros_pag = (
        await db.execute(stmt_venc_pendientes),
        await db.execute(stmt_venc_parciales),
        await db.execute(stmt_cobros_pendientes),
        await db.execute(stmt_cobros_parciales),
        await db.execute(stmt_cobros_pagados),
    )

    venc_pendientes = res_venc_pendientes.scalars().all()
    venc_parciales = res_venc_parciales.scalars().all()
    cobros_pendientes = res_cobros_pend.scalars().all()
    cobros_parciales = res_cobros_parc.scalars().all()
    cobros_pagados = res_cobros_pag.scalars().all()

    # 4. Agrupar por fecha
    empty_day = lambda: {
        "entregas": [],
        "cobros_pendientes": [],
        "cobros_parciales": [],
        "cobros_pagados": [],
        "vencimientos_pendientes": [],
        "vencimientos_parciales": [],
    }
    eventos_dict = defaultdict(empty_day)

    for p in pedidos:
        fecha = str(p.fecha_entrega)
        eventos_dict[fecha]["entregas"].append(f"Pedido #{p.numero_pedido} - {p.cliente.nombre}")

    for i in venc_pendientes:
        fecha = str(i.fecha_vencimiento.date()) if i.fecha_vencimiento else ""
        if fecha:
            eventos_dict[fecha]["vencimientos_pendientes"].append(
                f"Factura a Proveedor #{i.numero} - {i.proveedor.nombre if i.proveedor else 'S/P'} (${i.saldo_pendiente})"
            )

    for i in venc_parciales:
        fecha = str(i.fecha_vencimiento.date()) if i.fecha_vencimiento else ""
        if fecha:
            eventos_dict[fecha]["vencimientos_parciales"].append(
                f"Factura a Proveedor #{i.numero} - {i.proveedor.nombre if i.proveedor else 'S/P'} (${i.saldo_pendiente})"
            )

    for c in cobros_pendientes:
        fecha = str(c.fecha_compromiso_pago)
        eventos_dict[fecha]["cobros_pendientes"].append(
            f"Pedido #{c.numero_pedido} - {c.cliente.nombre} (${c.saldo_pendiente})"
        )

    for c in cobros_parciales:
        fecha = str(c.fecha_compromiso_pago)
        eventos_dict[fecha]["cobros_parciales"].append(
            f"Pedido #{c.numero_pedido} - {c.cliente.nombre} (${c.saldo_pendiente})"
        )

    for c in cobros_pagados:
        fecha = str(c.fecha_compromiso_pago)
        eventos_dict[fecha]["cobros_pagados"].append(
            f"Pedido #{c.numero_pedido} - {c.cliente.nombre}"
        )

    # 5. Formatear respuesta
    def make_evento(items: list) -> dict:
        return {"count": len(items), "detalles": items}

    return [
        {
            "fecha": fecha,
            "entregas": make_evento(data["entregas"]),
            "cobros_pendientes": make_evento(data["cobros_pendientes"]),
            "cobros_parciales": make_evento(data["cobros_parciales"]),
            "cobros_pagados": make_evento(data["cobros_pagados"]),
            "vencimientos_pendientes": make_evento(data["vencimientos_pendientes"]),
            "vencimientos_parciales": make_evento(data["vencimientos_parciales"]),
        }
        for fecha, data in eventos_dict.items()
    ]


@router.get("/comisiones-vendedores", response_model=list[VendedorComisionRow])
async def get_comisiones_vendedores(
    fecha_desde: date = Query(...),
    fecha_hasta: date = Query(...),
    vendedor_id: int | None = Query(None, description="Filtrar a un vendedor puntual (solo admin/super_admin)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["super_admin", "admin", "ventas"])),
):
    stmt = (
        select(Pedido)
        .options(
            selectinload(Pedido.vendedor),
            selectinload(Pedido.cliente),
            selectinload(Pedido.items).selectinload(PedidoItem.producto),
        )
        .where(Pedido.payment_status == EstadoPagoPedido.pagado)
        .where(func.coalesce(Pedido.fecha_entrega, Pedido.fecha) >= fecha_desde)
        .where(func.coalesce(Pedido.fecha_entrega, Pedido.fecha) <= fecha_hasta)
    )

    if current_user.rol.value == "ventas":
        # El vendedor solo ve lo suyo, sin importar el vendedor_id pedido.
        stmt = stmt.where(Pedido.vendedor_id == current_user.id)
    elif vendedor_id:
        # Admin/super_admin puede filtrar a un vendedor puntual para unificar sus ventas.
        stmt = stmt.where(Pedido.vendedor_id == vendedor_id)

    result = await db.execute(stmt)
    pedidos = result.scalars().all()

    # Group by vendedor
    vendedores: dict[int, dict] = {}
    for pedido in pedidos:
        if not pedido.vendedor_id or not pedido.vendedor:
            continue
        vid = pedido.vendedor_id
        if vid not in vendedores:
            v = pedido.vendedor
            vendedores[vid] = {
                "vendedor_id": vid,
                "vendedor_nombre": v.nombre_completo,
                "comision_generico_pct": float(v.comision_generico or 0),
                "comision_otc_pct": float(v.comision_otc or 0),
                "total_ventas_otc": 0.0,
                "total_ventas_generico": 0.0,
                "total_comision_otc": 0.0,
                "total_comision_generico": 0.0,
                "pedidos": [],
            }

        otc_pct = vendedores[vid]["comision_otc_pct"]
        gen_pct = vendedores[vid]["comision_generico_pct"]

        pedido_otc = 0.0
        pedido_gen = 0.0
        pedido_items_detalle = []
        comision_pedido = 0.0
        
        for item in pedido.items:
            cat = (item.producto.categoria_producto or "").lower() if item.producto else ""
            monto = float(item.precio_total)
            
            # Use saved commission percentage from item
            pct = float(item.comision_vendedor)
            # Fallback for historical data if field was zero (e.g. before migration)
            if pct == 0:
                pct = otc_pct if "otc" in cat else gen_pct
            
            comision_item = monto * pct / 100
            comision_pedido += comision_item

            if "otc" in cat:
                pedido_otc += monto
                vendedores[vid]["total_comision_otc"] += comision_item
            else:
                pedido_gen += monto
                vendedores[vid]["total_comision_generico"] += comision_item

            pedido_items_detalle.append({
                "producto_id": item.producto_id,
                "producto_nombre": item.producto.nombre if item.producto else "Producto Desconocido",
                "cantidad": item.cantidad_venta,
                "precio_unitario": float(item.precio_unitario),
                "precio_total": float(item.precio_total),
                "descuento_porcentaje": float(item.descuento_porcentaje or 0),
                "categoria": "OTC" if "otc" in cat else "Genérico",
                "comision_porcentaje": pct,
                "comision_calculada": round(comision_item, 2)
            })

        vendedores[vid]["total_ventas_otc"] += pedido_otc
        vendedores[vid]["total_ventas_generico"] += pedido_gen
        vendedores[vid]["pedidos"].append(PedidoComisionDetalle(
            pedido_id=pedido.id,
            numero_pedido=pedido.numero_pedido,
            cliente_nombre=pedido.cliente.nombre if pedido.cliente else "",
            fecha_entrega=str(pedido.fecha_entrega or pedido.fecha),
            total_otc=round(pedido_otc, 2),
            total_generico=round(pedido_gen, 2),
            total_pedido=round(pedido_otc + pedido_gen, 2),
            comision_calculada=round(comision_pedido, 2),
            items=pedido_items_detalle,
        ))

    rows = []
    for vdata in vendedores.values():
        otc_monto = round(vdata["total_comision_otc"], 2)
        gen_monto = round(vdata["total_comision_generico"], 2)
        rows.append(VendedorComisionRow(
            vendedor_id=vdata["vendedor_id"],
            vendedor_nombre=vdata["vendedor_nombre"],
            comision_generico_pct=vdata["comision_generico_pct"],
            comision_otc_pct=vdata["comision_otc_pct"],
            total_ventas_otc=round(vdata["total_ventas_otc"], 2),
            total_ventas_generico=round(vdata["total_ventas_generico"], 2),
            comision_otc_monto=otc_monto,
            comision_generico_monto=gen_monto,
            total_comision=round(otc_monto + gen_monto, 2),
            num_pedidos=len(vdata["pedidos"]),
            pedidos=vdata["pedidos"],
        ))

    rows.sort(key=lambda r: r.total_comision, reverse=True)
    return rows


@router.get("/historial-pvp", response_model=list[HistorialPvpResponse])
async def get_historial_pvp(
    search: str = Query("", description="Buscar por nombre o código de producto"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["super_admin", "admin", "ventas"])),
):
    """
    Returns the PVP history for products matching the search criteria.
    """
    if not search:
        return []

    like_pattern = f"%{search}%"
    stmt = (
        select(Producto)
        .options(selectinload(Producto.historial_pvp))
        .where(
            or_(
                Producto.nombre.ilike(like_pattern),
                Producto.codigo.ilike(like_pattern)
            )
        )
        .order_by(Producto.nombre)
        .limit(50)  # Limit to 50 products to avoid huge responses
    )

    result = await db.execute(stmt)
    productos = result.scalars().unique().all()

    response = []
    for p in productos:
        historial_rows = []
        # Sort history by date descending
        sorted_history = sorted(p.historial_pvp, key=lambda h: h.fecha_cambio, reverse=True)
        
        for h in sorted_history:
            variacion = None
            if h.pvp_anterior and h.pvp_anterior > 0:
                variacion = float(((h.pvp_nuevo - h.pvp_anterior) / h.pvp_anterior) * 100)
            
            historial_rows.append(HistorialPvpRow(
                id=h.id,
                fecha_cambio=h.fecha_cambio.isoformat(),
                pvp_anterior=float(h.pvp_anterior) if h.pvp_anterior else None,
                pvp_nuevo=float(h.pvp_nuevo),
                variacion_porcentaje=variacion
            ))
            
        response.append(HistorialPvpResponse(
            producto_id=p.id,
            producto_nombre=p.nombre,
            producto_codigo=p.codigo,
            historial=historial_rows
        ))

    return response


@router.get("/aumentos")
async def get_aumentos(
    dias: int = Query(180, ge=1, le=1095, description="Ventana en días hacia atrás"),
    limit: int = Query(50, ge=1, le=200, description="Máximo de lotes de aumento a devolver"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["super_admin", "admin", "ventas"])),
):
    """Cuadro discriminado de aumentos de PVP.

    Reutiliza `historial_pvp_producto`: agrupa los cambios de PVP por día y devuelve,
    por lote/día, el % promedio de variación y el detalle de productos afectados.
    Solo cuenta cambios con pvp_anterior (excluye la carga inicial del PVP).
    """
    from datetime import timedelta

    desde = datetime.now() - timedelta(days=dias)

    stmt = (
        select(HistorialPvpProducto, Producto.nombre, Producto.codigo)
        .join(Producto, HistorialPvpProducto.producto_id == Producto.id)
        .where(HistorialPvpProducto.fecha_cambio >= desde)
        .where(HistorialPvpProducto.pvp_anterior.isnot(None))
        .order_by(HistorialPvpProducto.fecha_cambio.desc())
    )
    rows = (await db.execute(stmt)).all()

    grupos: dict[str, dict] = {}
    for h, nombre, codigo in rows:
        if not h.pvp_anterior or h.pvp_anterior <= 0:
            continue
        variacion = float(((h.pvp_nuevo - h.pvp_anterior) / h.pvp_anterior) * 100)
        fecha_key = h.fecha_cambio.date().isoformat()
        grupo = grupos.setdefault(fecha_key, {"fecha": fecha_key, "productos": []})
        grupo["productos"].append({
            "producto_id": h.producto_id,
            "producto_nombre": nombre,
            "producto_codigo": codigo,
            "pvp_anterior": float(h.pvp_anterior),
            "pvp_nuevo": float(h.pvp_nuevo),
            "variacion_porcentaje": round(variacion, 2),
        })

    resultado = []
    for fecha_key in sorted(grupos.keys(), reverse=True)[:limit]:
        grupo = grupos[fecha_key]
        variaciones = [p["variacion_porcentaje"] for p in grupo["productos"]]
        aumentos = [v for v in variaciones if v > 0]
        resultado.append({
            "fecha": fecha_key,
            "cantidad_productos": len(grupo["productos"]),
            "variacion_promedio": round(sum(variaciones) / len(variaciones), 2) if variaciones else 0,
            "variacion_promedio_aumentos": round(sum(aumentos) / len(aumentos), 2) if aumentos else 0,
            "variacion_min": round(min(variaciones), 2) if variaciones else 0,
            "variacion_max": round(max(variaciones), 2) if variaciones else 0,
            "productos": grupo["productos"],
        })

    return resultado

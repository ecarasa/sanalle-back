from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, extract, and_, Date
from datetime import datetime, date, timedelta
from app.models.pedido import Pedido, EstadoDespacho
from app.models.pago import Pago, EstadoPago
from app.models.producto import Producto
from app.models.cliente import Cliente
from app.models.pedido_item import PedidoItem
from app.models.user import User
from decimal import Decimal


def _six_months_range(ref: date | None = None):
    """Return (six_months_ago date, month_labels list) for the 6 months ending at ref (or now)."""
    base = ref or datetime.now().date()
    months = []
    for i in range(5, -1, -1):
        m = base.month - i
        y = base.year
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))
    six_months_ago = date(months[0][0], months[0][1], 1)
    return six_months_ago, months


def _month_bounds(mes: str | None = None):
    """Return (month_start, next_month_start) for the given 'YYYY-MM' string or current month."""
    now = datetime.now()
    month_start = date(now.year, now.month, 1)
    if mes:
        try:
            y, m = mes.split("-")
            month_start = date(int(y), int(m), 1)
        except (ValueError, AttributeError):
            month_start = date(now.year, now.month, 1)
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    return month_start, next_month


async def _get_ventas_mensuales_grouped(db: AsyncSession, six_months_ago: date, months: list, vendedor_id: int | None = None):
    """Single GROUP BY query for monthly sales instead of 6 separate queries."""
    query = (
        select(
            extract('year', Pedido.fecha).label('y'),
            extract('month', Pedido.fecha).label('m'),
            func.coalesce(func.sum(Pedido.importe_total), 0),
        )
        .where(
            and_(
                Pedido.fecha >= six_months_ago,
                Pedido.shipping_status != EstadoDespacho.cancelado,
            )
        )
        .group_by('y', 'm')
        .order_by('y', 'm')
    )
    if vendedor_id is not None:
        query = query.where(Pedido.vendedor_id == vendedor_id)

    result = await db.execute(query)
    rows_map = {(int(r[0]), int(r[1])): float(r[2]) for r in result.all()}

    return [
        {"mes": f"{y}-{m:02d}", "importe": rows_map.get((y, m), 0)}
        for y, m in months
    ]


async def get_ventas_dashboard(db: AsyncSession, user_id: int) -> dict:
    """Dashboard for ventas role - personal stats."""
    now = datetime.now()
    month_start = date(now.year, now.month, 1)

    # Total vendido mes
    result = await db.execute(
        select(func.coalesce(func.sum(Pedido.importe_total), 0))
        .where(and_(
            Pedido.vendedor_id == user_id,
            Pedido.fecha >= month_start,
            Pedido.shipping_status != EstadoDespacho.cancelado,
        ))
    )
    total_vendido = float(result.scalar() or 0)

    # Pedidos del mes
    result = await db.execute(
        select(func.count(Pedido.id))
        .where(and_(Pedido.vendedor_id == user_id, Pedido.fecha >= month_start))
    )
    pedidos_mes = result.scalar() or 0

    # Clientes activos
    result = await db.execute(
        select(func.count(func.distinct(Pedido.cliente_id)))
        .where(Pedido.vendedor_id == user_id)
    )
    clientes_activos = result.scalar() or 0

    # Cobros del mes
    result = await db.execute(
        select(func.coalesce(func.sum(Pago.importe), 0))
        .where(and_(Pago.receptor_id == user_id, func.cast(Pago.fecha_recepcion, Date) >= month_start))
    )
    cobros_mes = float(result.scalar() or 0)

    # Ventas ultimos 6 meses
    six_months_ago, months = _six_months_range()
    ventas_mensuales = await _get_ventas_mensuales_grouped(db, six_months_ago, months, vendedor_id=user_id)

    # Top 5 clientes
    result = await db.execute(
        select(Cliente.nombre, func.sum(Pedido.importe_total).label('total'))
        .join(Pedido, Pedido.cliente_id == Cliente.id)
        .where(and_(
            Pedido.vendedor_id == user_id,
            Pedido.shipping_status != EstadoDespacho.cancelado,
        ))
        .group_by(Cliente.nombre)
        .order_by(func.sum(Pedido.importe_total).desc())
        .limit(5)
    )
    top_clientes = [{"nombre": r[0], "total": float(r[1])} for r in result.all()]

    # Estados de despacho de pedidos
    result = await db.execute(
        select(Pedido.shipping_status, func.count(Pedido.id))
        .where(Pedido.vendedor_id == user_id)
        .group_by(Pedido.shipping_status)
    )
    estados = {(r[0].value if hasattr(r[0], 'value') else str(r[0])): r[1] for r in result.all()}

    # Ultimos 5 pedidos
    result = await db.execute(
        select(Pedido).join(Cliente)
        .where(Pedido.vendedor_id == user_id)
        .order_by(Pedido.created_at.desc())
        .limit(5)
    )
    pedidos = result.scalars().all()
    ultimos_pedidos = [
        {
            "numero_pedido": p.numero_pedido,
            "cliente": "",
            "importe": float(p.importe_total),
            "estado": p.shipping_status.value if hasattr(p.shipping_status, 'value') else str(p.shipping_status),
            "fecha": str(p.fecha),
        }
        for p in pedidos
    ]

    # Pedidos cancelados del mes
    result = await db.execute(
        select(func.count(Pedido.id))
        .where(and_(
            Pedido.vendedor_id == user_id,
            Pedido.fecha >= month_start,
            Pedido.shipping_status == EstadoDespacho.cancelado
        ))
    )
    pedidos_cancelados = result.scalar() or 0

    return {
        "total_vendido": total_vendido,
        "pedidos_mes": pedidos_mes,
        "pedidos_cancelados": pedidos_cancelados,
        "clientes_activos": clientes_activos,
        "cobros_mes": cobros_mes,
        "ventas_mensuales": ventas_mensuales,
        "top_clientes": top_clientes,
        "estados_pedidos": estados,
        "ultimos_pedidos": ultimos_pedidos,
    }


async def get_admin_dashboard(db: AsyncSession, mes: str | None = None) -> dict:
    """Dashboard for admin role - global stats with new metrics, scoped to `mes` ('YYYY-MM')."""
    month_start, next_month = _month_bounds(mes)

    # Stock total
    result = await db.execute(select(func.coalesce(func.sum(Producto.stock_a_cajas), 0)).where(Producto.activo == True))
    stock_total = result.scalar() or 0

    # Ventas totales mes
    result = await db.execute(
        select(func.coalesce(func.sum(Pedido.importe_total), 0))
        .where(and_(
            Pedido.fecha >= month_start,
            Pedido.fecha < next_month,
            Pedido.shipping_status != EstadoDespacho.cancelado,
        ))
    )
    ventas_totales = float(result.scalar() or 0)

    # Pedidos totales mes
    result = await db.execute(
        select(func.count(Pedido.id))
        .where(and_(Pedido.fecha >= month_start, Pedido.fecha < next_month))
    )
    pedidos_totales = result.scalar() or 0

    # Cobros mes — por la fecha REAL del pago (fecha_recepcion), no por created_at
    # (que es cuándo se cargó el registro; una importación masiva lo pone todo "hoy").
    result = await db.execute(
        select(func.coalesce(func.sum(Pago.importe), 0))
        .where(and_(
            func.cast(Pago.fecha_recepcion, Date) >= month_start,
            func.cast(Pago.fecha_recepcion, Date) < next_month,
        ))
    )
    cobros_mes = float(result.scalar() or 0)

    # Ingresos ultimos 6 meses (hasta el mes seleccionado)
    six_months_ago, months = _six_months_range(month_start)
    ingresos_mensuales = await _get_ventas_mensuales_grouped(db, six_months_ago, months)

    # Ventas por vendedor (ultimos 3 meses hasta el mes seleccionado)
    three_months_ago = next_month - timedelta(days=90)
    result = await db.execute(
        select(User.nombre_completo, func.sum(Pedido.importe_total).label('total'))
        .join(Pedido, Pedido.vendedor_id == User.id)
        .where(and_(
            Pedido.fecha >= three_months_ago,
            Pedido.fecha < next_month,
            Pedido.shipping_status != EstadoDespacho.cancelado,
        ))
        .group_by(User.nombre_completo)
        .order_by(func.sum(Pedido.importe_total).desc())
    )
    ventas_vendedor = [{"vendedor": r[0], "total": float(r[1])} for r in result.all()]

    # Top productos por stock
    result = await db.execute(
        select(Producto.nombre, Producto.stock_a_cajas)
        .where(Producto.activo == True)
        .order_by(Producto.stock_a_cajas.desc())
        .limit(10)
    )
    top_stock = [{"nombre": r[0], "stock": r[1]} for r in result.all()]

    # Distribucion tipos de pago
    result = await db.execute(
        select(Pago.tipo_pago, func.count(Pago.id), func.sum(Pago.importe))
        .group_by(Pago.tipo_pago)
    )
    tipos_pago = [
        {
            "tipo": r[0] if isinstance(r[0], str) else (r[0].value if hasattr(r[0], 'value') else str(r[0])),
            "cantidad": r[1],
            "total": float(r[2] or 0),
        }
        for r in result.all()
    ]

    # Top vendedores del mes
    result = await db.execute(
        select(User.nombre_completo, func.sum(Pedido.importe_total).label('total'), func.count(Pedido.id).label('pedidos'))
        .join(Pedido, Pedido.vendedor_id == User.id)
        .where(and_(
            Pedido.fecha >= month_start,
            Pedido.fecha < next_month,
            Pedido.shipping_status != EstadoDespacho.cancelado,
        ))
        .group_by(User.nombre_completo)
        .order_by(func.sum(Pedido.importe_total).desc())
        .limit(5)
    )
    top_vendedores = [{"vendedor": r[0], "total": float(r[1]), "pedidos": r[2]} for r in result.all()]

    # Productos con stock bajo (stock_a_cajas <= stock_minimo_cajas)
    result = await db.execute(
        select(Producto).where(
            and_(Producto.activo == True, Producto.stock_a_cajas <= Producto.stock_minimo_cajas, Producto.stock_minimo_cajas > 0)
        ).order_by(Producto.stock_a_cajas).limit(20)
    )
    stock_bajo = [{"id": p.id, "nombre": p.nombre, "codigo": p.codigo, "stock": p.stock_a_cajas, "stock_minimo": p.stock_minimo_cajas} for p in result.scalars().all()]

    # REP-02: Pagos pendientes de imputacion (recibido state)
    result = await db.execute(
        select(func.count(Pago.id)).where(Pago.estado == EstadoPago.recibido)
    )
    pagos_pendientes_imputacion = result.scalar() or 0

    # REP-02: Clientes en rojo (with high debt)
    from app.services.semaforo_service import calcular_semaforo  # noqa: F401
    result_rojo = await db.execute(
        select(func.count(Cliente.id)).where(
            and_(Cliente.activo == True, Cliente.avg_dias_pago != None, Cliente.avg_dias_pago > 60)
        )
    )
    clientes_en_rojo = result_rojo.scalar() or 0

    # Ultimos 5 pagos
    result = await db.execute(
        select(Pago).join(Cliente).order_by(Pago.created_at.desc()).limit(5)
    )
    ultimos_pagos = []
    for p in result.scalars().all():
        ultimos_pagos.append({
            "numero_recibo": p.numero_recibo,
            "importe": float(p.importe),
            "tipo_pago": p.tipo_pago.value if hasattr(p.tipo_pago, 'value') else str(p.tipo_pago),
            "estado": p.estado.value if hasattr(p.estado, 'value') else str(p.estado),
            "fecha": str(p.fecha_recepcion)[:10],
        })

    # Pedidos cancelados mes
    result = await db.execute(
        select(func.count(Pedido.id))
        .where(and_(
            Pedido.fecha >= month_start,
            Pedido.fecha < next_month,
            Pedido.shipping_status == EstadoDespacho.cancelado
        ))
    )
    pedidos_cancelados = result.scalar() or 0

    return {
        "mes": month_start.strftime("%Y-%m"),
        "stock_total": stock_total,
        "ventas_totales": ventas_totales,
        "pedidos_totales": pedidos_totales,
        "pedidos_cancelados": pedidos_cancelados,
        "cobros_mes": cobros_mes,
        "ingresos_mensuales": ingresos_mensuales,
        "ventas_vendedor": ventas_vendedor,
        "top_stock": top_stock,
        "tipos_pago": tipos_pago,
        "top_vendedores": top_vendedores,
        "stock_bajo": stock_bajo,
        "ultimos_pagos": ultimos_pagos,
        "pagos_pendientes_imputacion": pagos_pendientes_imputacion,
        "clientes_en_rojo": clientes_en_rojo,
    }

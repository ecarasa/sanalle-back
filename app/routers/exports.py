from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
import io
import json

from app.core.database import get_db
from app.models.user import User
from app.models.cliente import Cliente
from app.models.producto import Producto
from app.models.laboratorios import Laboratorio
from app.models.deposito import Deposito
from app.models.stock_producto_deposito import StockProductoDeposito
from app.models.pedido import Pedido
from app.models.pago import Pago
from app.services.pricing_service import LISTAS
from app.utils.deps import get_current_user
from app.services.export_service import (
    export_pdf,
    export_excel,
    export_word,
    export_csv_data,
    export_xml,
    export_rtf,
    export_json_data,
)

router = APIRouter()

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "word": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv",
    "xml": "application/xml",
    "rtf": "application/rtf",
    "json": "application/json",
}

EXTENSIONS = {
    "pdf": "pdf",
    "excel": "xlsx",
    "word": "docx",
    "csv": "csv",
    "xml": "xml",
    "rtf": "rtf",
    "json": "json",
}

VALID_FORMATS = list(CONTENT_TYPES.keys())


def _generate_export(fmt: str, title: str, columns: list[str], rows: list[list], filename: str) -> StreamingResponse:
    """Generate a StreamingResponse for the given export format."""
    if fmt not in VALID_FORMATS:
        raise HTTPException(status_code=400, detail=f"Formato inválido. Use: {', '.join(VALID_FORMATS)}")

    ext = EXTENSIONS[fmt]
    content_type = CONTENT_TYPES[fmt]
    full_filename = f"{filename}.{ext}"

    if fmt == "pdf":
        output = io.BytesIO()
        export_pdf(title, columns, rows, output)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{full_filename}"'},
        )

    elif fmt == "excel":
        output = io.BytesIO()
        export_excel(title, columns, rows, output)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{full_filename}"'},
        )

    elif fmt == "word":
        output = io.BytesIO()
        export_word(title, columns, rows, output)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{full_filename}"'},
        )

    elif fmt == "csv":
        output = io.StringIO()
        export_csv_data(columns, rows, output)
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{full_filename}"'},
        )

    elif fmt == "xml":
        output = io.BytesIO()
        export_xml(title, columns, rows, output)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{full_filename}"'},
        )

    elif fmt == "rtf":
        rtf_content = export_rtf(title, columns, rows)
        return StreamingResponse(
            iter([rtf_content]),
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{full_filename}"'},
        )

    elif fmt == "json":
        json_data = export_json_data(columns, rows)
        json_str = json.dumps(json_data, ensure_ascii=False, indent=2, default=str)
        return StreamingResponse(
            iter([json_str]),
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{full_filename}"'},
        )


@router.get("/clientes")
async def export_clientes(
    format: str = Query("pdf", description="Formato de exportación"),
    search: str = Query("", description="Búsqueda por nombre, CUIT o razón social"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Cliente).where(Cliente.activo == True)

    if search:
        search_filter = f"%{search}%"
        query = query.where(
            Cliente.nombre.ilike(search_filter)
            | Cliente.cuit.ilike(search_filter)
            | Cliente.razon_social.ilike(search_filter)
        )

    query = query.order_by(Cliente.nombre)
    result = await db.execute(query)
    clientes = result.scalars().all()

    columns = ["ID", "Nombre", "Razón Social", "CUIT", "Domicilio", "Localidad", "Teléfono", "Email"]
    rows = [
        [
            c.id,
            c.nombre,
            c.razon_social or "",
            c.cuit or "",
            c.domicilio,
            c.localidad,
            c.telefono or "",
            c.email or "",
        ]
        for c in clientes
    ]

    return _generate_export(format, "Listado de Clientes", columns, rows, "clientes")


@router.get("/pedidos")
async def export_pedidos(
    format: str = Query("pdf", description="Formato de exportación"),
    search: str = Query("", description="Búsqueda por número de pedido"),
    cliente_id: int | None = Query(None, description="Filtrar por cliente"),
    shipping_status: str | None = Query(None, description="Filtrar por estado de despacho"),
    payment_status: str | None = Query(None, description="Filtrar por estado de pago"),
    excluir_borradores: bool = Query(False, description="Deja afuera las cotizaciones"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.pedido import EstadoDespacho, EstadoPago as EstadoPagoPedido
    query = select(Pedido).join(Cliente).join(Pedido.vendedor).options(
        selectinload(Pedido.cliente),
        selectinload(Pedido.vendedor),
    )

    if search:
        query = query.where(Pedido.numero_pedido.ilike(f"%{search}%"))
    if cliente_id:
        query = query.where(Pedido.cliente_id == cliente_id)
    if shipping_status:
        try:
            query = query.where(Pedido.shipping_status == EstadoDespacho(shipping_status))
        except ValueError:
            pass
    # El export tiene que sacar lo mismo que la pantalla desde la que se pide.
    if excluir_borradores and not shipping_status:
        query = query.where(Pedido.shipping_status != EstadoDespacho.borrador)
    if payment_status:
        try:
            query = query.where(Pedido.payment_status == EstadoPagoPedido(payment_status))
        except ValueError:
            pass

    query = query.order_by(Pedido.fecha.desc())
    result = await db.execute(query)
    pedidos = result.scalars().unique().all()

    columns = ["N° Pedido", "Cliente", "Vendedor", "Despacho", "Pago", "Fecha", "Transporte", "Sociedad", "Despachado", "Importe Total"]
    rows = [
        [
            p.numero_pedido,
            p.cliente.nombre if p.cliente else "",
            p.vendedor.nombre_completo if p.vendedor else "",
            p.shipping_status.value if hasattr(p.shipping_status, "value") else str(p.shipping_status),
            p.payment_status.value if hasattr(p.payment_status, "value") else str(p.payment_status),
            str(p.fecha),
            p.transporte or "",
            p.sociedad or "",
            "Sí" if p.despachado else "No",
            float(p.importe_total),
        ]
        for p in pedidos
    ]

    return _generate_export(format, "Listado de Pedidos", columns, rows, "pedidos")


@router.get("/pagos")
async def export_pagos(
    format: str = Query("pdf", description="Formato de exportación"),
    search: str = Query("", description="Búsqueda por número de recibo"),
    cliente_id: int | None = Query(None, description="Filtrar por cliente"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Pago).join(Cliente).join(Pago.receptor).options(
        selectinload(Pago.cliente),
        selectinload(Pago.receptor),
    )

    if search:
        query = query.where(Pago.numero_recibo.ilike(f"%{search}%"))
    if cliente_id:
        query = query.where(Pago.cliente_id == cliente_id)

    query = query.order_by(Pago.fecha_recepcion.desc())
    result = await db.execute(query)
    pagos = result.scalars().unique().all()

    columns = ["N° Recibo", "Cliente", "Tipo Pago", "Importe", "Fecha", "Estado", "Receptor"]
    rows = [
        [
            p.numero_recibo,
            p.cliente.nombre if p.cliente else "",
            p.tipo_pago.value if hasattr(p.tipo_pago, "value") else str(p.tipo_pago),
            float(p.importe),
            str(p.fecha_recepcion)[:10],
            p.estado.value if hasattr(p.estado, "value") else str(p.estado),
            p.receptor.nombre_completo if p.receptor else "",
        ]
        for p in pagos
    ]

    return _generate_export(format, "Listado de Pagos", columns, rows, "pagos")


@router.get("/productos")
async def export_productos(
    format: str = Query("pdf", description="Formato de exportación"),
    search: str = Query("", description="Búsqueda por nombre o código"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Producto).where(Producto.activo == True)

    if search:
        search_filter = f"%{search}%"
        query = query.where(
            Producto.nombre.ilike(search_filter) | Producto.codigo.ilike(search_filter)
        )

    # Mismo orden que la lista de precios pública: primero el orden que fija la
    # droguería para los laboratorios, después el nombre. Hace falta el outerjoin
    # explícito — con `selectinload` solo no se puede ordenar por una columna del
    # laboratorio, porque viaja en una query aparte.
    query = (
        query.outerjoin(Laboratorio, Producto.laboratorio_id == Laboratorio.id)
        .options(selectinload(Producto.laboratorio))
        .order_by(
            func.coalesce(Laboratorio.orden, 999999),
            func.lower(func.coalesce(Laboratorio.nombre, "￿")),
            func.lower(Producto.nombre),
        )
    )
    result = await db.execute(query)
    productos = result.scalars().unique().all()

    # Una columna de stock por depósito activo, en el orden del maestro.
    depositos = (
        await db.execute(
            select(Deposito).where(Deposito.activo == True).order_by(Deposito.orden, Deposito.id)
        )
    ).scalars().all()
    stock_por_producto = {
        (pid, dep_id): cajas
        for pid, dep_id, cajas in (
            await db.execute(
                select(
                    StockProductoDeposito.producto_id,
                    StockProductoDeposito.deposito_id,
                    StockProductoDeposito.cajas,
                )
            )
        ).all()
    }

    columns = [
        "ID", "Código", "Nombre", "Laboratorio", "Categoría", "Presentación",
        *(f"Stock {d.nombre}" for d in depositos), "PVP",
        *(lista.label for lista in LISTAS),
    ]
    rows = [
        [
            p.id,
            p.codigo,
            p.nombre,
            p.laboratorio.nombre if p.laboratorio else "",
            p.categoria_producto or "",
            p.presentacion or "",
            *(stock_por_producto.get((p.id, d.id), 0) for d in depositos),
            float(p.pvp) if p.pvp else "",
            *(
                float(getattr(p, lista.precio_field))
                if getattr(p, lista.precio_field) is not None
                else ""
                for lista in LISTAS
            ),
        ]
        for p in productos
    ]

    return _generate_export(format, "Listado de Productos", columns, rows, "productos")

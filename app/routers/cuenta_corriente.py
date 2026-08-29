from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.cliente import Cliente
from app.models.pedido import ESTADOS_NO_COMPUTABLES, Pedido, EstadoDespacho
from app.models.pago import Pago, EstadoPago
from app.models.nota_credito_debito import NotaCreditoDebito, TipoNota
from app.models.user import User
from app.schemas.cuenta_corriente import MovimientoCC, CuentaCorrienteResponse, SaldoResponse
from app.utils.deps import get_current_user

import os
from fastapi.responses import FileResponse
from app.core.config import settings
from app.services.pdf_service import generate_estado_cuenta_pdf

router = APIRouter()


@router.get("/{cliente_id}/movimientos")
async def get_cuenta_corriente(
    cliente_id: int,
    fecha_desde: date | None = Query(None),
    fecha_hasta: date | None = Query(None),
    tipo_cuenta: str | None = Query(None, description="remito o factura"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate cliente
    cliente_result = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    cliente = cliente_result.scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    movimientos: list[MovimientoCC] = []

    # Add deuda_inicial as first movement if > 0
    di_rem = float(cliente.deuda_inicial_remito)
    di_fac = float(cliente.deuda_inicial_factura)

    if not tipo_cuenta or tipo_cuenta == "remito":
        if di_rem != 0:
            movimientos.append(MovimientoCC(
                fecha=cliente.created_at,
                tipo="deuda_inicial",
                numero="INIT-R",
                descripcion="Deuda inicial Remitos",
                debe=di_rem if di_rem > 0 else 0,
                haber=abs(di_rem) if di_rem < 0 else 0,
            ))
    
    if not tipo_cuenta or tipo_cuenta == "factura":
        if di_fac != 0:
            movimientos.append(MovimientoCC(
                fecha=cliente.created_at,
                tipo="deuda_inicial",
                numero="INIT-F",
                descripcion="Deuda inicial Facturas",
                debe=di_fac if di_fac > 0 else 0,
                haber=abs(di_fac) if di_fac < 0 else 0,
            ))

    # Pedidos (DEBE) - todos excepto cancelados
    pedido_filters = [
        Pedido.cliente_id == cliente_id,
        Pedido.shipping_status.notin_(ESTADOS_NO_COMPUTABLES),
    ]
    if tipo_cuenta:
        pedido_filters.append(Pedido.tipo_documento == tipo_cuenta)
    if fecha_desde:
        pedido_filters.append(Pedido.fecha >= fecha_desde)
    if fecha_hasta:
        pedido_filters.append(Pedido.fecha <= fecha_hasta)

    pedidos_result = await db.execute(
        select(Pedido).where(and_(*pedido_filters)).order_by(Pedido.fecha)
    )
    for p in pedidos_result.scalars().all():
        tipo_doc = p.tipo_documento.value if p.tipo_documento else "pedido"
        movimientos.append(MovimientoCC(
            fecha=datetime.combine(p.fecha, datetime.min.time(), tzinfo=timezone.utc),
            tipo="pedido",
            numero=p.numero_pedido,
            descripcion=f"Pedido {tipo_doc} ({p.shipping_status.value})",
            debe=float(p.importe_total),
            haber=0,
        ))

    # Pagos (HABER)
    pago_filters = [
        Pago.cliente_id == cliente_id,
        Pago.estado.in_([EstadoPago.recibido, EstadoPago.imputado, EstadoPago.acreditado, EstadoPago.pendiente]),
    ]
    if tipo_cuenta:
        pago_filters.append(Pago.tipo_cuenta == tipo_cuenta)
    if fecha_desde:
        pago_filters.append(Pago.fecha_recepcion >= datetime.combine(fecha_desde, datetime.min.time(), tzinfo=timezone.utc))
    if fecha_hasta:
        pago_filters.append(Pago.fecha_recepcion <= datetime.combine(fecha_hasta, datetime.max.time(), tzinfo=timezone.utc))

    pagos_result = await db.execute(
        select(Pago).where(and_(*pago_filters)).order_by(Pago.fecha_recepcion)
    )
    for p in pagos_result.scalars().all():
        movimientos.append(MovimientoCC(
            fecha=p.fecha_recepcion,
            tipo="pago",
            numero=p.numero_recibo,
            descripcion=f"Pago {p.tipo_pago.value} ({p.estado.value}) - Cuenta: {p.tipo_cuenta.value}",
            debe=0,
            haber=float(p.importe),
        ))

    # Notas credito/debito
    nota_filters = [NotaCreditoDebito.cliente_id == cliente_id]
    if tipo_cuenta:
        nota_filters.append(NotaCreditoDebito.tipo_cuenta == tipo_cuenta)
    if fecha_desde:
        nota_filters.append(NotaCreditoDebito.fecha >= fecha_desde)
    if fecha_hasta:
        nota_filters.append(NotaCreditoDebito.fecha <= fecha_hasta)

    notas_result = await db.execute(
        select(NotaCreditoDebito).where(and_(*nota_filters)).order_by(NotaCreditoDebito.fecha)
    )
    for n in notas_result.scalars().all():
        if n.tipo == TipoNota.credito:
            movimientos.append(MovimientoCC(
                fecha=datetime.combine(n.fecha, datetime.min.time(), tzinfo=timezone.utc),
                tipo="nota_credito",
                numero=n.numero,
                descripcion=f"Nota de Crédito ({n.tipo_cuenta.value}) - {n.motivo or ''}",
                debe=0,
                haber=float(n.importe_total),
            ))
        else:
            movimientos.append(MovimientoCC(
                fecha=datetime.combine(n.fecha, datetime.min.time(), tzinfo=timezone.utc),
                tipo="nota_debito",
                numero=n.numero,
                descripcion=f"Nota de Débito ({n.tipo_cuenta.value}) - {n.motivo or ''}",
                debe=float(n.importe_total),
                haber=0,
            ))

    # Sort by date
    movimientos.sort(key=lambda m: m.fecha)

    # Calculate running balance
    saldo = 0.0
    for m in movimientos:
        saldo += m.debe - m.haber
        m.saldo = round(saldo, 2)

    saldo_a_favor = abs(saldo) if saldo < 0 else 0

    return CuentaCorrienteResponse(
        cliente_id=cliente_id,
        cliente_nombre=cliente.nombre,
        movimientos=movimientos,
        saldo_total=round(saldo, 2),
        saldo_a_favor=round(saldo_a_favor, 2),
    )


@router.get("/{cliente_id}/saldo")
async def get_saldo(
    cliente_id: int,
    fecha: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate cliente
    cliente_result = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    cliente = cliente_result.scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    saldo = float(cliente.deuda_inicial_remito) + float(cliente.deuda_inicial_factura)

    # Sum pedidos — todos excepto cancelados
    pedido_filters = [
        Pedido.cliente_id == cliente_id,
        Pedido.shipping_status.notin_(ESTADOS_NO_COMPUTABLES),
    ]
    if fecha:
        pedido_filters.append(Pedido.fecha <= fecha)

    ped_result = await db.execute(
        select(func.coalesce(func.sum(Pedido.importe_total), 0)).where(and_(*pedido_filters))
    )
    saldo += float(ped_result.scalar_one())

    # Subtract pagos
    pago_filters = [
        Pago.cliente_id == cliente_id,
        Pago.estado.in_([EstadoPago.recibido, EstadoPago.imputado, EstadoPago.acreditado, EstadoPago.pendiente]),
    ]
    if fecha:
        pago_filters.append(Pago.fecha_recepcion <= datetime.combine(fecha, datetime.max.time(), tzinfo=timezone.utc))

    pag_result = await db.execute(
        select(func.coalesce(func.sum(Pago.importe), 0)).where(and_(*pago_filters))
    )
    saldo -= float(pag_result.scalar_one())

    # Notas credito/debito
    nota_filters = [NotaCreditoDebito.cliente_id == cliente_id]
    if fecha:
        nota_filters.append(NotaCreditoDebito.fecha <= fecha)

    nc_result = await db.execute(
        select(func.coalesce(func.sum(NotaCreditoDebito.importe_total), 0)).where(
            and_(*nota_filters, NotaCreditoDebito.tipo == TipoNota.credito)
        )
    )
    saldo -= float(nc_result.scalar_one())

    nd_result = await db.execute(
        select(func.coalesce(func.sum(NotaCreditoDebito.importe_total), 0)).where(
            and_(*nota_filters, NotaCreditoDebito.tipo == TipoNota.debito)
        )
    )
    saldo += float(nd_result.scalar_one())

    return SaldoResponse(cliente_id=cliente_id, saldo=round(saldo, 2), fecha=fecha)




@router.get("/{cliente_id}/exportar-pdf")
async def exportar_cuenta_corriente_pdf(
    cliente_id: int,
    fecha_desde: date | None = Query(None),
    fecha_hasta: date | None = Query(None),
    tipo_cuenta: str | None = Query(None, description="remito o factura"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate and download a PDF Statement of Account (Estado de Cuenta).
    """
    # 1. Fetch full client data for the header
    cliente_result = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    cliente = cliente_result.scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
        
    cliente_dict = {
        "id": cliente.id,
        "nombre": cliente.nombre,
        "cuit": cliente.cuit,
        "domicilio": cliente.domicilio,
    }

    # 2. Fetch movements using the existing logic
    cc_response = await get_cuenta_corriente(
        cliente_id=cliente_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        tipo_cuenta=tipo_cuenta,
        db=db,
        current_user=current_user
    )

    # 3. Prepare filters for the PDF header
    filtros = {
        "tipo_cuenta": tipo_cuenta,
        "fecha_desde": fecha_desde.isoformat() if fecha_desde else None,
        "fecha_hasta": fecha_hasta.isoformat() if fecha_hasta else None,
    }

    # 4. Generate PDF
    filename = generate_estado_cuenta_pdf(
        cliente_data=cliente_dict,
        movimientos=cc_response.movimientos,
        saldo_total=cc_response.saldo_total,
        filtros=filtros
    )
    
    filepath = os.path.join(settings.PDF_STORAGE_PATH, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=500, detail="Error al generar el PDF")
        
    return FileResponse(
        filepath, 
        media_type="application/pdf", 
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

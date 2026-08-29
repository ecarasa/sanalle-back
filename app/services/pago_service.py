from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pago import Pago, EstadoPago, TipoCuenta
from app.models.pedido import ESTADOS_NO_COMPUTABLES, Pedido, EstadoPago as EstadoPagoPedido, TipoDocumento
from app.models.pago_imputacion import PagoImputacion

async def imputar_pagos_a_pedido(db: AsyncSession, pedido: Pedido):
    """
    Finds available payments (saldo_restante > 0) for the client and applies them
    to the specific order until it's paid or credits are exhausted.
    """
    # Un borrador todavía no es una venta: imputarle el crédito del cliente lo
    # dejaría "pagado" mientras el vendedor sigue tipeando.
    if pedido.saldo_pendiente <= 0 or pedido.shipping_status in ESTADOS_NO_COMPUTABLES:
        return

    # Find available payments for this client and account type
    # We map Pedido.tipo_documento to Pago.tipo_cuenta
    tipo_cuenta_buscado = None
    
    # Use .value for safer comparison if it's an Enum or string
    tipo_doc_val = pedido.tipo_documento.value if hasattr(pedido.tipo_documento, 'value') else pedido.tipo_documento
    
    if tipo_doc_val == "remito":
        tipo_cuenta_buscado = TipoCuenta.remito
    elif tipo_doc_val == "factura":
        tipo_cuenta_buscado = TipoCuenta.factura

    if not tipo_cuenta_buscado:
        return

    query = (
        select(Pago)
        .where(
            Pago.cliente_id == pedido.cliente_id,
            Pago.saldo_restante > 0,
            Pago.tipo_cuenta == tipo_cuenta_buscado,
            Pago.estado != EstadoPago.rechazado
        )
        .order_by(Pago.fecha_recepcion.asc(), Pago.id.asc())
    )
    
    result = await db.execute(query)
    pagos_disponibles = result.scalars().all()

    for pago in pagos_disponibles:
        if pedido.saldo_pendiente <= 0:
            break
            
        aplicar = min(pago.saldo_restante, pedido.saldo_pendiente)
        
        imputacion = PagoImputacion(
            pago_id=pago.id,
            pedido_id=pedido.id,
            monto=aplicar,
            observacion="Imputación automática desde crédito disponible"
        )
        db.add(imputacion)
        
        # Update Pedido
        pedido.saldo_pendiente -= aplicar
        pedido.payment_status = EstadoPagoPedido.pagado if pedido.saldo_pendiente <= 0 else EstadoPagoPedido.parcial
        
        # Update Pago
        pago.saldo_restante -= aplicar
        if pago.saldo_restante <= 0:
            pago.estado = EstadoPago.imputado
        else:
            pago.estado = EstadoPago.imputado_parcial
            
    await db.flush()


async def imputar_pago_a_pedidos_pendientes(db: AsyncSession, pago: Pago):
    """
    Finds pending orders for the client and applies the specific payment 
    to them until the payment is exhausted or no more pending orders exist.
    """
    if pago.saldo_restante <= 0 or pago.estado == EstadoPago.rechazado:
        return

    # Map Pago.tipo_cuenta to Pedido.tipo_documento
    tipo_doc_buscado = None
    if pago.tipo_cuenta == TipoCuenta.remito:
        tipo_doc_buscado = TipoDocumento.remito
    elif pago.tipo_cuenta == TipoCuenta.factura:
        tipo_doc_buscado = TipoDocumento.factura

    query = (
        select(Pedido)
        .where(
            Pedido.cliente_id == pago.cliente_id,
            Pedido.saldo_pendiente > 0,
            Pedido.shipping_status.notin_(ESTADOS_NO_COMPUTABLES)
        )
    )
    
    if tipo_doc_buscado:
        query = query.where(Pedido.tipo_documento == tipo_doc_buscado)
        
    query = query.order_by(Pedido.fecha.asc(), Pedido.id.asc())
    
    result = await db.execute(query)
    pedidos_pendientes = result.scalars().all()

    for pedido in pedidos_pendientes:
        if pago.saldo_restante <= 0:
            break
            
        aplicar = min(pago.saldo_restante, pedido.saldo_pendiente)
        
        imputacion = PagoImputacion(
            pago_id=pago.id,
            pedido_id=pedido.id,
            monto=aplicar,
            observacion="Imputación automática"
        )
        db.add(imputacion)
        
        # Update Pedido
        pedido.saldo_pendiente -= aplicar
        pedido.payment_status = EstadoPagoPedido.pagado if pedido.saldo_pendiente <= 0 else EstadoPagoPedido.parcial
        
        # Update Pago
        pago.saldo_restante -= aplicar
        
    # Final check for payment status
    if pago.saldo_restante <= 0:
        pago.estado = EstadoPago.imputado
    elif pago.saldo_restante < pago.importe:
        pago.estado = EstadoPago.imputado_parcial
        
    await db.flush()

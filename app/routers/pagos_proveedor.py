# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, status
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession
# pyrefly: ignore [missing-import]
from sqlalchemy import select
# pyrefly: ignore [missing-import]
from typing import List

from app.core.database import get_db
from app.models.pago_proveedor import PagoProveedor
from app.models.proveedor import Proveedor
from app.models.pago import TipoPago, TipoCuenta
from app.models.cuenta_sanalle import TipoMovimiento, CategoriaMovimiento
from app.schemas.pago_proveedor import PagoProveedorCreate, PagoProveedorResponse
from app.services.movimientos_service import registrar_movimiento
from app.utils.deps import get_current_user
from app.models.user import User

router = APIRouter()


@router.post("", response_model=PagoProveedorResponse, status_code=status.HTTP_201_CREATED)
async def create_pago_proveedor(
    body: PagoProveedorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Registra un pago realizado a un proveedor.
    Disminuye el saldo pendiente del proveedor y genera un egreso en la Cuenta Sanalle.
    """
    # Validate proveedor
    res = await db.execute(select(Proveedor).where(Proveedor.id == body.proveedor_id))
    proveedor = res.scalar_one_or_none()
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    # Validate tipo_pago
    try:
        tipo_pago_enum = TipoPago(body.tipo_pago)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Tipo de pago inválido: {body.tipo_pago}")

    # Validate tipo_cuenta
    try:
        tipo_cuenta_enum = TipoCuenta(body.tipo_cuenta)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Tipo de cuenta inválido: {body.tipo_cuenta}")

    pago = PagoProveedor(
        proveedor_id=body.proveedor_id,
        usuario_id=current_user.id,
        pago_id=body.pago_id,
        importe=body.importe,
        fecha_pago=body.fecha_pago,
        tipo_pago=tipo_pago_enum,
        tipo_cuenta=tipo_cuenta_enum,
        referencia_pago=body.referencia_pago,
        observacion=body.observacion
    )
    db.add(pago)
    await db.flush()

    # Actualizar saldo del proveedor según el tipo de cuenta
    if tipo_cuenta_enum == TipoCuenta.remito:
        proveedor.saldo_remito -= pago.importe
    else:
        proveedor.saldo_factura -= pago.importe

    # Registrar movimiento en Cuenta Sanalle (Libro Mayor)
    await registrar_movimiento(
        db=db,
        tipo=TipoMovimiento.egreso,
        categoria=CategoriaMovimiento.pago_proveedor,
        importe=pago.importe,
        metodo_pago=tipo_pago_enum,
        usuario_id=current_user.id,
        descripcion=f"Pago a proveedor: {proveedor.nombre} - Ref: {pago.referencia_pago or 'S/N'}",
        referencia_id=f"PAGOPROV-{pago.id}",
        fecha=pago.fecha_pago
    )

    await db.commit()
    await db.refresh(pago)
    return pago


@router.get("", response_model=List[PagoProveedorResponse])
async def list_pagos_proveedor(
    proveedor_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista los pagos realizados a proveedores.
    """
    query = select(PagoProveedor)
    if proveedor_id:
        query = query.where(PagoProveedor.proveedor_id == proveedor_id)
    query = query.order_by(PagoProveedor.fecha_pago.desc())
    
    res = await db.execute(query)
    return res.scalars().all()

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, status
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession
# pyrefly: ignore [missing-import]
from sqlalchemy import select
# pyrefly: ignore [missing-import]
from typing import List
from decimal import Decimal

from app.core.database import get_db
from app.models.pago_proveedor import PagoProveedor
from app.models.proveedor import Proveedor
from app.models.proveedor_cuenta import ProveedorCuenta
from app.models.pago import Pago, TipoPago, TipoCuenta
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

    # Si el pago está financiado por un cobro pasamanos (cuenta puente), es TRÁNSITO:
    # no impacta la caja real y la salida no puede superar la entrada (el cobro).
    pago_puente = None
    if body.pago_id is not None:
        pago_puente = (await db.execute(select(Pago).where(Pago.id == body.pago_id))).scalar_one_or_none()
    es_transito = pago_puente is not None and pago_puente.es_puente
    if es_transito and float(body.importe) > float(pago_puente.importe) + 0.01:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El pago (${body.importe}) excede el cobro puente (${float(pago_puente.importe)}). "
                "En una cuenta puente la salida no puede superar la entrada."
            ),
        )

    # Cuenta destino: si no la eligen, la marcada por defecto en la libreta del
    # proveedor. Se valida que sea de ESTE proveedor, o se podría dejar registrado
    # un giro a la cuenta de otro.
    proveedor_cuenta_id = body.proveedor_cuenta_id
    if proveedor_cuenta_id is not None:
        pertenece = (
            await db.execute(
                select(ProveedorCuenta.id).where(
                    ProveedorCuenta.id == proveedor_cuenta_id,
                    ProveedorCuenta.proveedor_id == body.proveedor_id,
                )
            )
        ).scalar_one_or_none()
        if pertenece is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La cuenta elegida no pertenece a este proveedor.",
            )
    else:
        proveedor_cuenta_id = (
            await db.execute(
                select(ProveedorCuenta.id).where(
                    ProveedorCuenta.proveedor_id == body.proveedor_id,
                    ProveedorCuenta.activo.is_(True),
                    ProveedorCuenta.es_default.is_(True),
                )
            )
        ).scalar_one_or_none()

    pago = PagoProveedor(
        proveedor_id=body.proveedor_id,
        usuario_id=current_user.id,
        pago_id=body.pago_id,
        cuenta_id=body.cuenta_id,
        proveedor_cuenta_id=proveedor_cuenta_id,
        # El schema declara `importe: float` y los saldos del proveedor son
        # Decimal. Sin convertir acá, el `-=` de más abajo revienta con
        # "unsupported operand type(s) for -=: 'Decimal' and 'float'" —
        # SQLAlchemy no convierte el atributo al hacer flush, se queda con el
        # valor de Python tal cual se lo pasaron.
        importe=Decimal(str(body.importe)),
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
        categoria=CategoriaMovimiento.transito if es_transito else CategoriaMovimiento.pago_proveedor,
        importe=pago.importe,
        metodo_pago=tipo_pago_enum,
        usuario_id=current_user.id,
        descripcion=(
            f"Tránsito (pasamanos) → Pago a proveedor: {proveedor.nombre} - Ref: {pago.referencia_pago or 'S/N'}"
            if es_transito
            else f"Pago a proveedor: {proveedor.nombre} - Ref: {pago.referencia_pago or 'S/N'}"
        ),
        referencia_id=f"PAGOPROV-{pago.id}",
        fecha=pago.fecha_pago
    )

    await db.commit()
    await db.refresh(pago)
    # Construir la respuesta a mano (los enums son enum.Enum puros, no str: evitamos
    # que la serialización por response_model falle).
    return PagoProveedorResponse(
        id=pago.id,
        proveedor_id=pago.proveedor_id,
        proveedor_nombre=proveedor.nombre,
        usuario_id=pago.usuario_id,
        pago_id=pago.pago_id,
        cuenta_id=pago.cuenta_id,
        proveedor_cuenta_id=pago.proveedor_cuenta_id,
        importe=float(pago.importe),
        fecha_pago=pago.fecha_pago,
        tipo_pago=pago.tipo_pago.value,
        tipo_cuenta=pago.tipo_cuenta.value,
        referencia_pago=pago.referencia_pago,
        observacion=pago.observacion,
        imputaciones=[],
        created_at=pago.created_at,
        updated_at=pago.updated_at,
    )


@router.get("", response_model=List[PagoProveedorResponse])
async def list_pagos_proveedor(
    proveedor_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista los pagos realizados a proveedores (con el nombre del proveedor).
    """
    query = select(PagoProveedor, Proveedor.nombre).outerjoin(
        Proveedor, PagoProveedor.proveedor_id == Proveedor.id
    )
    if proveedor_id:
        query = query.where(PagoProveedor.proveedor_id == proveedor_id)
    query = query.order_by(PagoProveedor.fecha_pago.desc())

    rows = (await db.execute(query)).all()
    return [
        PagoProveedorResponse(
            id=pp.id,
            proveedor_id=pp.proveedor_id,
            proveedor_nombre=prov_nombre,
            usuario_id=pp.usuario_id,
            pago_id=pp.pago_id,
            cuenta_id=pp.cuenta_id,
            proveedor_cuenta_id=pp.proveedor_cuenta_id,
            importe=float(pp.importe),
            fecha_pago=pp.fecha_pago,
            tipo_pago=pp.tipo_pago.value,
            tipo_cuenta=pp.tipo_cuenta.value,
            referencia_pago=pp.referencia_pago,
            observacion=pp.observacion,
            imputaciones=[],
            created_at=pp.created_at,
            updated_at=pp.updated_at,
        )
        for pp, prov_nombre in rows
    ]

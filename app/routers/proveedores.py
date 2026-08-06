from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.proveedor import Proveedor
from app.models.ingreso_mercaderia import IngresoMercaderia
from app.models.notas_proveedor import NotaProveedor, TipoNota
from app.models.cuenta_sanalle import CuentaSanalle, TipoMovimiento, CategoriaMovimiento
from app.models.laboratorios import Laboratorio
from app.models.pago import Pago, TipoPago, TipoCuenta
from app.models.pago_proveedor import PagoProveedor, PagoProveedorImputacion
from app.schemas.proveedor import (
    ProveedorCreate, ProveedorUpdate, ProveedorResponse,
    PagoPendienteInfo, NotaProveedorInfo, PagoDeudaProveedorRequest,
)
from app.services.movimientos_service import registrar_movimiento
from app.utils.deps import get_current_user, require_role

router = APIRouter()


async def _build_proveedor_dict(p: Proveedor, db: AsyncSession) -> dict:
    """Fetch related data and return a complete proveedor response dict."""
    pendientes_res = await db.execute(
        select(IngresoMercaderia).where(
            and_(
                IngresoMercaderia.proveedor_id == p.id,
                IngresoMercaderia.saldo_pendiente > 0,
            )
        ).order_by(IngresoMercaderia.fecha.asc())
    )
    pendientes = pendientes_res.scalars().all()
    saldo_total = sum((item.saldo_pendiente for item in pendientes), Decimal("0"))

    notas_res = await db.execute(
        select(NotaProveedor)
        .where(NotaProveedor.proveedor_id == p.id)
        .order_by(NotaProveedor.fecha.desc())
    )
    notas = notas_res.scalars().all()
    total_notas_credito = sum(
        (n.importe_total for n in notas if n.tipo == TipoNota.credito),
        Decimal("0"),
    )

    p_dict = ProveedorResponse.model_validate(p).model_dump()
    p_dict["saldo_pendiente_total"] = saldo_total
    p_dict["pagos_pendientes"] = [PagoPendienteInfo.model_validate(item).model_dump() for item in pendientes]
    p_dict["notas"] = [NotaProveedorInfo.model_validate(n).model_dump() for n in notas]
    p_dict["total_notas_credito"] = total_notas_credito
    return p_dict


@router.get("")
async def list_proveedores(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=1000),
    search: str = Query("", max_length=100),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = []
    if not include_inactive:
        filters.append(Proveedor.activo == True)
    if search:
        filters.append(Proveedor.nombre.ilike(f"%{search}%"))

    base_query = select(Proveedor).where(and_(*filters))

    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = base_query.order_by(Proveedor.nombre).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    proveedores = result.scalars().all()

    items = [await _build_proveedor_dict(p, db) for p in proveedores]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{id}")
async def get_proveedor(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Proveedor).where(Proveedor.id == id))
    proveedor = result.scalar_one_or_none()
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return await _build_proveedor_dict(proveedor, db)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_proveedor(
    data: ProveedorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    existing = await db.execute(select(Proveedor).where(Proveedor.nombre == data.nombre))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Ya existe un proveedor con ese nombre")

    proveedor = Proveedor(**data.model_dump())

    if data.tipo == "laboratorio":
        lab_res = await db.execute(select(Laboratorio).where(Laboratorio.nombre == data.nombre))
        if not lab_res.scalar_one_or_none():
            laboratorio = Laboratorio(nombre=data.nombre)
            db.add(laboratorio)
            
    db.add(proveedor)
    await db.commit()
    await db.refresh(proveedor)
    return ProveedorResponse.model_validate(proveedor).model_dump()


@router.put("/{id}")
async def update_proveedor(
    id: int,
    data: ProveedorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Proveedor).where(Proveedor.id == id))
    proveedor = result.scalar_one_or_none()
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(proveedor, key, value)

    await db.commit()
    await db.refresh(proveedor)
    return ProveedorResponse.model_validate(proveedor).model_dump()


@router.post("/{proveedor_id}/pagar")
async def pagar_deuda_proveedor(
    proveedor_id: int,
    body: PagoDeudaProveedorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    proveedor_res = await db.execute(select(Proveedor).where(Proveedor.id == proveedor_id))
    proveedor = proveedor_res.scalar_one_or_none()
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    if not body.ingresos:
        raise HTTPException(status_code=400, detail="Debe seleccionar al menos un comprobante")

    ingreso_ids = [item.id for item in body.ingresos]
    monto_map = {item.id: item.monto for item in body.ingresos}

    ingresos_res = await db.execute(
        select(IngresoMercaderia).where(
            and_(
                IngresoMercaderia.id.in_(ingreso_ids),
                IngresoMercaderia.proveedor_id == proveedor_id,
                IngresoMercaderia.saldo_pendiente > 0,
            )
        )
    )
    ingresos = ingresos_res.scalars().all()
    if len(ingresos) != len(ingreso_ids):
        raise HTTPException(status_code=400, detail="Algunos comprobantes no son válidos o ya están saldados")

    descuento = proveedor.descuento if body.aplicar_descuento else Decimal("0")
    factor = (Decimal("100") - descuento) / Decimal("100")

    # Validate amounts and compute total
    total_a_pagar = Decimal("0")
    for ingreso in ingresos:
        monto = Decimal(str(monto_map[ingreso.id])).quantize(Decimal("0.01"))
        max_monto = (ingreso.saldo_pendiente * factor).quantize(Decimal("0.01"))
        if monto <= 0:
            raise HTTPException(status_code=400, detail=f"El monto para {ingreso.numero} debe ser mayor a 0")
        if monto > max_monto + Decimal("0.01"):
            raise HTTPException(
                status_code=400,
                detail=f"El monto ${monto} para {ingreso.numero} excede el máximo de ${max_monto}",
            )
        total_a_pagar += monto

    total_a_pagar = total_a_pagar.quantize(Decimal("0.01"))

    # Check Cuenta Sanalle balance
    ing_q = await db.execute(
        select(func.coalesce(func.sum(CuentaSanalle.importe), 0)).where(
            CuentaSanalle.tipo == TipoMovimiento.ingreso
        )
    )
    egr_q = await db.execute(
        select(func.coalesce(func.sum(CuentaSanalle.importe), 0)).where(
            CuentaSanalle.tipo == TipoMovimiento.egreso
        )
    )
    balance = float(ing_q.scalar_one()) - float(egr_q.scalar_one())

    if balance < float(total_a_pagar):
        raise HTTPException(
            status_code=400,
            detail=f"Saldo insuficiente en Cuenta Sanalle. Balance disponible: ${balance:,.2f}",
        )

    # Apply payments
    for ingreso in ingresos:
        monto = Decimal(str(monto_map[ingreso.id])).quantize(Decimal("0.01"))
        max_monto = (ingreso.saldo_pendiente * factor).quantize(Decimal("0.01"))
        if monto >= max_monto - Decimal("0.01"):
            ingreso.saldo_pendiente = Decimal("0")
        else:
            saldo_reduction = (monto / factor).quantize(Decimal("0.01")) if factor > 0 else ingreso.saldo_pendiente
            ingreso.saldo_pendiente = max(Decimal("0"), ingreso.saldo_pendiente - saldo_reduction)

    # Record egress in Cuenta Sanalle
    try:
        metodo_enum = TipoPago(body.metodo_pago)
    except ValueError:
        raise HTTPException(status_code=400, detail="Método de pago inválido")

    descripcion = f"Pago a {proveedor.nombre} — {len(ingresos)} comprobante(s)"
    if descuento > 0:
        descripcion += f" (desc. {descuento}%)"

    fecha_pago = body.fecha or datetime.now(timezone.utc)

    movimiento = await registrar_movimiento(
        db=db,
        tipo=TipoMovimiento.egreso,
        categoria=CategoriaMovimiento.pago_proveedor,
        importe=total_a_pagar,
        metodo_pago=metodo_enum,
        usuario_id=current_user.id,
        descripcion=descripcion,
        referencia_id=f"PROV-{proveedor_id}",
        fecha=fecha_pago,
    )

    # Create cashback credit note if requested
    nota_id = None
    cashback_importe = Decimal("0")
    if body.aplicar_cashback and proveedor.cashback > 0:
        cashback_importe = (total_a_pagar * proveedor.cashback / Decimal("100")).quantize(Decimal("0.01"))
        nc_numero = f"NC-PROV-{proveedor_id}-{int(datetime.utcnow().timestamp())}"
        nota = NotaProveedor(
            numero=nc_numero,
            tipo=TipoNota.credito,
            proveedor_id=proveedor_id,
            fecha=date.today(),
            importe_total=cashback_importe,
            creado_por_id=current_user.id,
        )
        db.add(nota)
        await db.flush()
        nota_id = nota.id

    # Resolve optional pago_id
    pago_id_resuelto = None
    if body.pago_id is not None:
        pago_check = await db.execute(select(Pago).where(Pago.id == body.pago_id))
        if pago_check.scalar_one_or_none():
            pago_id_resuelto = body.pago_id

    # Always create PagoProveedor for full traceability
    pp = PagoProveedor(
        proveedor_id=proveedor_id,
        usuario_id=current_user.id,
        pago_id=pago_id_resuelto,
        importe=total_a_pagar,
        fecha_pago=fecha_pago,
        tipo_pago=metodo_enum,
        tipo_cuenta=TipoCuenta.remito,
        referencia_pago=f"PROV-{proveedor_id}",
        observacion=descripcion,
    )
    db.add(pp)
    await db.flush()

    # Create imputaciones linking this payment to each ingreso
    for ingreso in ingresos:
        monto = Decimal(str(monto_map[ingreso.id])).quantize(Decimal("0.01"))
        imputacion = PagoProveedorImputacion(
            pago_proveedor_id=pp.id,
            ingreso_mercaderia_id=ingreso.id,
            importe_aplicado=monto,
        )
        db.add(imputacion)

    await db.commit()
    await db.refresh(movimiento)

    return {
        "total_pagado": float(total_a_pagar),
        "movimiento_id": movimiento.id,
        "ingresos_saldados": [i.id for i in ingresos if i.saldo_pendiente == 0],
        "descuento_aplicado": float(descuento),
        "nota_credito_id": nota_id,
        "cashback_importe": float(cashback_importe),
    }


@router.get("/{proveedor_id}/ingresos-pendientes")
async def get_ingresos_pendientes(
    proveedor_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Proveedor).where(Proveedor.id == proveedor_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    ingresos_res = await db.execute(
        select(IngresoMercaderia)
        .where(
            IngresoMercaderia.proveedor_id == proveedor_id,
            IngresoMercaderia.saldo_pendiente > 0,
        )
        .order_by(IngresoMercaderia.fecha.asc())
    )
    ingresos = ingresos_res.scalars().all()
    return [PagoPendienteInfo.model_validate(i).model_dump() for i in ingresos]


@router.delete("/{id}")
async def delete_proveedor(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Proveedor).where(Proveedor.id == id))
    proveedor = result.scalar_one_or_none()
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    proveedor.activo = False
    await db.commit()
    return {"message": "Proveedor desactivado correctamente"}

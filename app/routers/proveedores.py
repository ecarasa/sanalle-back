from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.proveedor import Proveedor
from app.models.proveedor_cuenta import ProveedorCuenta
from app.models.ingreso_mercaderia import IngresoMercaderia
from app.models.notas_proveedor import NotaProveedor, TipoNota
from app.models.cashback_proveedor import CashbackProveedor
from app.models.cuenta_sanalle import CuentaSanalle, TipoMovimiento, CategoriaMovimiento
from app.models.laboratorios import Laboratorio
from app.models.pago import Pago, TipoPago, TipoCuenta
from app.models.pago_proveedor import PagoProveedor, PagoProveedorImputacion
from app.schemas.proveedor import (
    ProveedorCreate, ProveedorUpdate, ProveedorResponse,
    ProveedorCuentaCreate, ProveedorCuentaUpdate, ProveedorCuentaResponse,
    PagoPendienteInfo, NotaProveedorInfo, PagoDeudaProveedorRequest,
)
from app.services.movimientos_service import registrar_movimiento
from app.utils.deps import get_current_user, require_role
from app.utils.tz import hoy_ar

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

    cashback_pendiente = (await db.execute(
        select(func.coalesce(func.sum(CashbackProveedor.importe), 0)).where(
            and_(CashbackProveedor.proveedor_id == p.id, CashbackProveedor.estado == "pendiente")
        )
    )).scalar_one()

    # Cuentas bancarias del proveedor: van en la misma respuesta porque la pantalla
    # las muestra junto al saldo y pedirlas aparte serían N llamadas en el listado.
    cuentas = (
        await db.execute(
            select(ProveedorCuenta)
            .where(ProveedorCuenta.proveedor_id == p.id, ProveedorCuenta.activo.is_(True))
            .order_by(ProveedorCuenta.es_default.desc(), ProveedorCuenta.id)
        )
    ).scalars().all()

    p_dict = ProveedorResponse.model_validate(p).model_dump()
    p_dict["saldo_pendiente_total"] = saldo_total
    p_dict["pagos_pendientes"] = [PagoPendienteInfo.model_validate(item).model_dump() for item in pendientes]
    p_dict["notas"] = [NotaProveedorInfo.model_validate(n).model_dump() for n in notas]
    p_dict["total_notas_credito"] = total_notas_credito
    p_dict["cashback_pendiente"] = Decimal(str(cashback_pendiente))
    p_dict["cuentas"] = [ProveedorCuentaResponse.model_validate(c).model_dump() for c in cuentas]
    return p_dict


# --- Libreta de cuentas bancarias del proveedor -------------------------------
# Mismo patrón que las direcciones del cliente (`/clientes/{id}/direcciones`):
# tabla hija, una marcada por defecto, baja lógica.


async def _proveedor_o_404(db: AsyncSession, proveedor_id: int) -> Proveedor:
    proveedor = (
        await db.execute(select(Proveedor).where(Proveedor.id == proveedor_id))
    ).scalar_one_or_none()
    if proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado")
    return proveedor


async def _desmarcar_otras_default(db: AsyncSession, proveedor_id: int, excepto_id: int | None) -> None:
    """Solo una cuenta puede ser la propuesta por defecto."""
    q = sa_update(ProveedorCuenta).where(ProveedorCuenta.proveedor_id == proveedor_id)
    if excepto_id is not None:
        q = q.where(ProveedorCuenta.id != excepto_id)
    await db.execute(q.values(es_default=False))


async def _cuenta_o_404(db: AsyncSession, proveedor_id: int, cuenta_id: int) -> ProveedorCuenta:
    cuenta = (
        await db.execute(
            select(ProveedorCuenta).where(
                ProveedorCuenta.id == cuenta_id,
                ProveedorCuenta.proveedor_id == proveedor_id,
            )
        )
    ).scalar_one_or_none()
    if cuenta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    return cuenta


@router.get("/{proveedor_id}/cuentas", response_model=list[ProveedorCuentaResponse])
async def list_cuentas_proveedor(
    proveedor_id: int,
    incluir_inactivas: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    await _proveedor_o_404(db, proveedor_id)
    q = select(ProveedorCuenta).where(ProveedorCuenta.proveedor_id == proveedor_id)
    if not incluir_inactivas:
        q = q.where(ProveedorCuenta.activo.is_(True))
    filas = (
        await db.execute(q.order_by(ProveedorCuenta.es_default.desc(), ProveedorCuenta.id))
    ).scalars().all()
    return [ProveedorCuentaResponse.model_validate(c) for c in filas]


@router.post(
    "/{proveedor_id}/cuentas",
    response_model=ProveedorCuentaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_cuenta_proveedor(
    proveedor_id: int,
    body: ProveedorCuentaCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    await _proveedor_o_404(db, proveedor_id)
    cuenta = ProveedorCuenta(proveedor_id=proveedor_id, **body.model_dump())
    db.add(cuenta)
    await db.flush()
    # La primera cuenta es la default aunque no la hayan marcado: si no, el combo
    # de pago arrancaría vacío teniendo una sola opción.
    ya_habia = (
        await db.execute(
            select(func.count())
            .select_from(ProveedorCuenta)
            .where(
                ProveedorCuenta.proveedor_id == proveedor_id,
                ProveedorCuenta.id != cuenta.id,
                ProveedorCuenta.activo.is_(True),
            )
        )
    ).scalar_one()
    if cuenta.es_default or ya_habia == 0:
        cuenta.es_default = True
        await _desmarcar_otras_default(db, proveedor_id, cuenta.id)
    await db.commit()

    cuenta = (
        await db.execute(select(ProveedorCuenta).where(ProveedorCuenta.id == cuenta.id))
    ).scalar_one()
    return ProveedorCuentaResponse.model_validate(cuenta)


@router.put("/{proveedor_id}/cuentas/{cuenta_id}", response_model=ProveedorCuentaResponse)
async def update_cuenta_proveedor(
    proveedor_id: int,
    cuenta_id: int,
    body: ProveedorCuentaUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    cuenta = await _cuenta_o_404(db, proveedor_id, cuenta_id)

    for campo, valor in body.model_dump(exclude_unset=True).items():
        setattr(cuenta, campo, valor)

    if cuenta.es_default:
        await _desmarcar_otras_default(db, proveedor_id, cuenta.id)
    await db.commit()

    cuenta = (
        await db.execute(select(ProveedorCuenta).where(ProveedorCuenta.id == cuenta_id))
    ).scalar_one()
    return ProveedorCuentaResponse.model_validate(cuenta)


@router.delete("/{proveedor_id}/cuentas/{cuenta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cuenta_proveedor(
    proveedor_id: int,
    cuenta_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Baja lógica. Los pagos ya hechos referencian la cuenta a la que se giró:
    borrar la fila dejaría esos pagos sin poder decir a dónde fue la plata."""
    cuenta = await _cuenta_o_404(db, proveedor_id, cuenta_id)
    era_default = cuenta.es_default
    cuenta.activo = False
    cuenta.es_default = False
    await db.flush()

    # Si se dio de baja la default, se promueve la siguiente activa: dejar al
    # proveedor sin ninguna marcada haría que el combo de pago arranque vacío.
    if era_default:
        siguiente = (
            await db.execute(
                select(ProveedorCuenta)
                .where(
                    ProveedorCuenta.proveedor_id == proveedor_id,
                    ProveedorCuenta.activo.is_(True),
                )
                .order_by(ProveedorCuenta.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if siguiente is not None:
            siguiente.es_default = True

    await db.commit()


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

    # Resolver el cobro de cliente que (opcionalmente) financia este pago. Si ese cobro
    # es un pasamanos (cuenta puente), el egreso se registra como TRÁNSITO y no impacta
    # la caja real. Validamos que el cobro alcance para cubrir lo que se paga.
    pago_puente = None
    if body.pago_id is not None:
        pago_puente = (await db.execute(select(Pago).where(Pago.id == body.pago_id))).scalar_one_or_none()
    es_transito = pago_puente is not None and pago_puente.es_puente
    if es_transito and total_a_pagar > pago_puente.importe + Decimal("0.01"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"El pago (${total_a_pagar}) excede el cobro puente (${pago_puente.importe}). "
                "En una cuenta puente la salida no puede superar la entrada."
            ),
        )

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

    # Apply payments. Guardamos, por renglón, el monto pagado y si el comprobante quedó
    # saldado (para inferir cashback total vs parcial).
    lineas_pago: list[tuple[Decimal, bool]] = []
    for ingreso in ingresos:
        monto = Decimal(str(monto_map[ingreso.id])).quantize(Decimal("0.01"))
        max_monto = (ingreso.saldo_pendiente * factor).quantize(Decimal("0.01"))
        if monto >= max_monto - Decimal("0.01"):
            ingreso.saldo_pendiente = Decimal("0")
            lineas_pago.append((monto, True))   # saldado -> tasa total
        else:
            saldo_reduction = (monto / factor).quantize(Decimal("0.01")) if factor > 0 else ingreso.saldo_pendiente
            ingreso.saldo_pendiente = max(Decimal("0"), ingreso.saldo_pendiente - saldo_reduction)
            lineas_pago.append((monto, False))  # queda saldo -> tasa parcial

    # Record egress in Cuenta Sanalle
    try:
        metodo_enum = TipoPago(body.metodo_pago)
    except ValueError:
        raise HTTPException(status_code=400, detail="Método de pago inválido")

    descripcion = f"Pago a {proveedor.nombre} — {len(ingresos)} comprobante(s)"
    if descuento > 0:
        descripcion += f" (desc. {descuento}%)"
    if es_transito:
        descripcion = f"Tránsito (pasamanos) → {descripcion}"

    fecha_pago = body.fecha or datetime.now(timezone.utc)

    movimiento = await registrar_movimiento(
        db=db,
        tipo=TipoMovimiento.egreso,
        categoria=CategoriaMovimiento.transito if es_transito else CategoriaMovimiento.pago_proveedor,
        importe=total_a_pagar,
        metodo_pago=metodo_enum,
        usuario_id=current_user.id,
        descripcion=descripcion,
        referencia_id=f"PROV-{proveedor_id}",
        fecha=fecha_pago,
    )

    # Cashback: por renglón, tasa total si el comprobante quedó saldado, si no parcial.
    # NO se emite nota de crédito acá: se acumula (ver /acreditar-cashback).
    cashback_importe = Decimal("0")
    if body.aplicar_cashback:
        for monto_linea, saldado in lineas_pago:
            tasa = proveedor.cashback_total if saldado else proveedor.cashback_parcial
            if tasa and tasa > 0:
                cashback_importe += (monto_linea * tasa / Decimal("100")).quantize(Decimal("0.01"))

    # pago_id ya resuelto arriba (pago_puente). Se guarda para trazabilidad del pasamanos.
    pago_id_resuelto = pago_puente.id if pago_puente is not None else None

    # Always create PagoProveedor for full traceability
    # Cuenta destino: si no la eligen, se usa la marcada por defecto en la libreta
    # del proveedor. Se valida que sea de ESTE proveedor: sin el chequeo se podría
    # dejar registrado un giro a la cuenta de otro.
    proveedor_cuenta_id = body.proveedor_cuenta_id
    if proveedor_cuenta_id is not None:
        await _cuenta_o_404(db, proveedor_id, proveedor_cuenta_id)
    else:
        default = (
            await db.execute(
                select(ProveedorCuenta.id).where(
                    ProveedorCuenta.proveedor_id == proveedor_id,
                    ProveedorCuenta.activo.is_(True),
                    ProveedorCuenta.es_default.is_(True),
                )
            )
        ).scalar_one_or_none()
        proveedor_cuenta_id = default

    pp = PagoProveedor(
        proveedor_id=proveedor_id,
        usuario_id=current_user.id,
        pago_id=pago_id_resuelto,
        cuenta_id=body.cuenta_id,
        proveedor_cuenta_id=proveedor_cuenta_id,
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

    # Acumular el cashback como pendiente (se acredita después en una sola NC).
    if cashback_importe > 0:
        db.add(CashbackProveedor(
            proveedor_id=proveedor_id,
            pago_proveedor_id=pp.id,
            importe=cashback_importe,
            estado="pendiente",
            fecha=hoy_ar(),
        ))

    await db.commit()
    await db.refresh(movimiento)

    return {
        "total_pagado": float(total_a_pagar),
        "movimiento_id": movimiento.id,
        "ingresos_saldados": [i.id for i in ingresos if i.saldo_pendiente == 0],
        "descuento_aplicado": float(descuento),
        "cashback_acumulado": float(cashback_importe),
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


@router.get("/{proveedor_id}/cashback")
async def list_cashback(
    proveedor_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Historial de cashback acumulado del proveedor (pendiente + acreditado)."""
    rows = (await db.execute(
        select(CashbackProveedor).where(CashbackProveedor.proveedor_id == proveedor_id)
        .order_by(CashbackProveedor.created_at.desc())
    )).scalars().all()
    pendiente = sum((r.importe for r in rows if r.estado == "pendiente"), Decimal("0"))
    return {
        "pendiente": float(pendiente),
        "items": [
            {
                "id": r.id,
                "importe": float(r.importe),
                "estado": r.estado,
                "fecha": r.fecha.isoformat(),
                "pago_proveedor_id": r.pago_proveedor_id,
                "nota_proveedor_id": r.nota_proveedor_id,
            }
            for r in rows
        ],
    }


@router.post("/{proveedor_id}/acreditar-cashback")
async def acreditar_cashback(
    proveedor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Emite UNA nota de crédito por todo el cashback pendiente y lo marca acreditado."""
    prov = (await db.execute(select(Proveedor).where(Proveedor.id == proveedor_id))).scalar_one_or_none()
    if not prov:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    pendientes = (await db.execute(
        select(CashbackProveedor).where(
            and_(CashbackProveedor.proveedor_id == proveedor_id, CashbackProveedor.estado == "pendiente")
        )
    )).scalars().all()
    if not pendientes:
        raise HTTPException(status_code=400, detail="No hay cashback pendiente para acreditar")

    total = sum((c.importe for c in pendientes), Decimal("0")).quantize(Decimal("0.01"))

    nota = NotaProveedor(
        numero=f"NC-PROV-{proveedor_id}-{int(datetime.utcnow().timestamp())}",
        tipo=TipoNota.credito,
        proveedor_id=proveedor_id,
        fecha=hoy_ar(),
        importe_total=total,
        creado_por_id=current_user.id,
    )
    db.add(nota)
    await db.flush()

    for c in pendientes:
        c.estado = "acreditado"
        c.nota_proveedor_id = nota.id

    await db.commit()
    return {"nota_id": nota.id, "total": float(total), "cantidad": len(pendientes)}


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

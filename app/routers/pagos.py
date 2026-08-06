import os
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.cliente import Cliente
from app.models.pago import Pago, TipoPago, EstadoPago, TipoCuenta
from app.models.pago_imputacion import PagoImputacion
from app.models.pago_proveedor import PagoProveedor
from app.models.pedido import Pedido, EstadoDespacho, EstadoPago as EstadoPagoPedido
from app.models.user import User
from app.schemas.pago import (
    PagoCreate,
    PagoUpdate,
    PagoResponse,
    PagoImputarRequest,
    PagoBulkImputarRequest,
    PagoImputacionResponse,
)
from app.schemas.pago_proveedor import PagoProveedorResponse
from app.models.cuenta_sanalle import TipoMovimiento, CategoriaMovimiento
from app.services.movimientos_service import registrar_movimiento
from app.services.pago_service import imputar_pago_a_pedidos_pendientes
from app.services.pdf_service import generate_pago_recibo_pdf
from app.utils.deps import get_current_user, require_role
from app.utils.filters import apply_column_filters

router = APIRouter()


def _build_pago_response(
    pago: Pago,
    imputaciones: list | None = None,
    pagos_proveedor: list | None = None,
) -> PagoResponse:
    return PagoResponse(
        id=pago.id,
        cliente_id=pago.cliente_id,
        cliente_nombre=pago.cliente.nombre if pago.cliente else None,
        receptor_id=pago.receptor_id,
        receptor_nombre=pago.receptor.nombre_completo if pago.receptor else None,
        tipo_pago=pago.tipo_pago.value,
        importe=float(pago.importe),
        fecha_recepcion=pago.fecha_recepcion,
        estado=pago.estado.value,
        observacion=pago.observacion,
        recibo_pdf_path=pago.recibo_pdf_path,
        numero_recibo=pago.numero_recibo,
        saldo_restante=float(pago.saldo_restante),
        banco_id=pago.banco_id,
        ch_numero=pago.ch_numero,
        ch_banco=pago.ch_banco,
        ch_fecha=pago.ch_fecha,
        ch_vto=pago.ch_vto,
        retencion_tipo=pago.retencion_tipo,
        retencion_numero=pago.retencion_numero,
        retencion_fecha=pago.retencion_fecha,
        transferencia_numero=pago.transferencia_numero,
        transferencia_fecha=pago.transferencia_fecha,
        transferencia_cuenta_origen=pago.transferencia_cuenta_origen,
        grupo_recibo_id=pago.grupo_recibo_id,
        tipo_cuenta=pago.tipo_cuenta.value,
        created_at=pago.created_at,
        updated_at=pago.updated_at,
        imputaciones=[
            PagoImputacionResponse(
                id=imp.id,
                pago_id=imp.pago_id,
                pedido_id=imp.pedido_id,
                numero_pedido=imp.pedido.numero_pedido if imp.pedido else None,
                monto=float(imp.monto),
                observacion=imp.observacion,
                created_at=imp.created_at,
            )
            for imp in (imputaciones or [])
        ],
        pagos_proveedor=[
            PagoProveedorResponse(
                id=pp.id,
                proveedor_id=pp.proveedor_id,
                proveedor_nombre=pp.proveedor.nombre if pp.proveedor else None,
                usuario_id=pp.usuario_id,
                pago_id=pp.pago_id,
                importe=float(pp.importe),
                fecha_pago=pp.fecha_pago,
                tipo_pago=pp.tipo_pago.value,
                tipo_cuenta=pp.tipo_cuenta.value,
                referencia_pago=pp.referencia_pago,
                observacion=pp.observacion,
                created_at=pp.created_at,
                updated_at=pp.updated_at,
            )
            for pp in (pagos_proveedor or [])
        ],
    )


@router.get("")
async def list_pagos(
    cliente_id: int | None = Query(None),
    estado: str | None = Query(None),
    column_filters: str | None = Query(None, alias="filters", description="JSON column filters"),
    sort_by: str | None = Query(None, description="Columna por la que ordenar"),
    sort_dir: str = Query("desc", description="Dirección de orden: asc o desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base_query = select(Pago).join(Cliente, Pago.cliente_id == Cliente.id).outerjoin(
        User, Pago.receptor_id == User.id
    )

    filters = []

    if current_user.rol.value == "ventas":
        filters.append(Pago.receptor_id == current_user.id)

    if cliente_id is not None:
        filters.append(Pago.cliente_id == cliente_id)

    if estado is not None:
        try:
            filters.append(Pago.estado == EstadoPago(estado))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Estado inválido: {estado}")

    if filters:
        base_query = base_query.where(*filters)

    base_query = apply_column_filters(
        base_query,
        Pago,
        column_filters,
        allowed_columns={"tipo_pago", "estado", "importe", "fecha_recepcion", "cliente_nombre", "receptor_nombre", "ch_numero", "ch_banco", "ch_fecha", "ch_vto"},
        extra_mappings={
            "cliente_nombre": Cliente.nombre,
            "receptor_nombre": User.nombre_completo,
        },
    )

    count_query = select(func.count()).select_from(
        base_query.with_only_columns(Pago.id).subquery()
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    _sort_columns = {
        "id": Pago.id,
        "cliente_nombre": Cliente.nombre,
        "tipo_pago": Pago.tipo_pago,
        "fecha_recepcion": Pago.fecha_recepcion,
        "importe": Pago.importe,
        "saldo_restante": Pago.saldo_restante,
        "estado": Pago.estado,
    }
    sort_col = _sort_columns.get(sort_by) if sort_by else None
    if sort_col is not None:
        order_expr = sort_col.asc() if sort_dir == "asc" else sort_col.desc()
    else:
        order_expr = Pago.id.desc()

    data_query = (
        base_query.options(
            selectinload(Pago.cliente),
            selectinload(Pago.receptor),
            selectinload(Pago.imputaciones).selectinload(PagoImputacion.pedido),
            selectinload(Pago.pagos_proveedor).selectinload(PagoProveedor.proveedor),
        )
        .order_by(order_expr)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(data_query)
    pagos = result.scalars().unique().all()

    items = [_build_pago_response(p, p.imputaciones, p.pagos_proveedor) for p in pagos]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/cliente/{cliente_id}")
async def list_pagos_by_cliente(
    cliente_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    cliente_result = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    cliente = cliente_result.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )

    query = (
        select(Pago)
        .where(Pago.cliente_id == cliente_id)
        .options(
            selectinload(Pago.cliente),
            selectinload(Pago.receptor),
            selectinload(Pago.imputaciones).selectinload(PagoImputacion.pedido),
            selectinload(Pago.pagos_proveedor).selectinload(PagoProveedor.proveedor),
        )
        .order_by(Pago.id.desc())
    )
    result = await db.execute(query)
    pagos = result.scalars().unique().all()

    return [_build_pago_response(p, p.imputaciones, p.pagos_proveedor) for p in pagos]


@router.get("/{id}")
async def get_pago(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = (
        select(Pago)
        .where(Pago.id == id)
        .options(
            selectinload(Pago.cliente),
            selectinload(Pago.receptor),
            selectinload(Pago.imputaciones).selectinload(PagoImputacion.pedido),
            selectinload(Pago.pagos_proveedor).selectinload(PagoProveedor.proveedor),
        )
    )
    result = await db.execute(query)
    pago = result.scalar_one_or_none()
    if pago is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pago no encontrado",
        )
    return _build_pago_response(pago, pago.imputaciones, pago.pagos_proveedor)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_pago(
    body: PagoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate cliente exists
    cliente_result = await db.execute(select(Cliente).where(Cliente.id == body.cliente_id).options(selectinload(Cliente.localidad_rel)))
    cliente = cliente_result.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )

    # Validate tipo_pago
    try:
        tipo_pago_enum = TipoPago(body.tipo_pago)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de pago inválido: {body.tipo_pago}. Valores válidos: {[t.value for t in TipoPago]}",
        )

    # Validate tipo_cuenta
    try:
        tipo_cuenta_enum = TipoCuenta(body.tipo_cuenta)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de cuenta inválido: {body.tipo_cuenta}. Valores válidos: {[t.value for t in TipoCuenta]}",
        )

    # Auto-generate numero_recibo
    max_result = await db.execute(
        select(func.max(Pago.numero_recibo)).where(Pago.numero_recibo.like("REC-%"))
    )
    max_numero = max_result.scalar_one()
    if max_numero:
        current_num = int(max_numero.replace("REC-", ""))
        next_num = current_num + 1
    else:
        next_num = 1
    numero_recibo = f"REC-{next_num:05d}"

    fecha_recepcion = body.fecha_recepcion if body.fecha_recepcion else datetime.now(timezone.utc)

    pago = Pago(
        cliente_id=body.cliente_id,
        receptor_id=current_user.id,
        tipo_pago=tipo_pago_enum,
        importe=body.importe,
        fecha_recepcion=fecha_recepcion,
        estado=EstadoPago.recibido,
        observacion=body.observacion,
        numero_recibo=numero_recibo,
        banco_id=body.banco_id,
        ch_numero=body.ch_numero,
        ch_banco=body.ch_banco,
        ch_fecha=body.ch_fecha,
        ch_vto=body.ch_vto,
        retencion_tipo=body.retencion_tipo,
        retencion_numero=body.retencion_numero,
        retencion_fecha=body.retencion_fecha,
        transferencia_numero=body.transferencia_numero,
        transferencia_fecha=body.transferencia_fecha,
        transferencia_cuenta_origen=body.transferencia_cuenta_origen,
        grupo_recibo_id=body.grupo_recibo_id,
        tipo_cuenta=tipo_cuenta_enum,
        saldo_restante=Decimal(str(body.importe)),
    )
    db.add(pago)
    await db.flush()

    # Register CuentaSanalle ingreso
    await registrar_movimiento(
        db=db,
        tipo=TipoMovimiento.ingreso,
        categoria=CategoriaMovimiento.cobro_cliente,
        importe=pago.importe,
        metodo_pago=pago.tipo_pago,
        usuario_id=current_user.id,
        descripcion=f"Cobro cliente: {cliente.nombre} (Recibo {pago.numero_recibo})",
        referencia_id=f"PAGO-{pago.id}",
        fecha=pago.fecha_recepcion
    )

    # Auto-imputar: greedily apply payment to oldest pending pedidos
    if body.auto_imputar:
        await imputar_pago_a_pedidos_pendientes(db, pago)

    # Recompute estado based on final saldo_restante
    importe_decimal = Decimal(str(body.importe))
    if pago.saldo_restante <= 0:
        pago.estado = EstadoPago.imputado
    elif pago.saldo_restante < importe_decimal:
        pago.estado = EstadoPago.imputado_parcial
    # else: remains recibido

    # Generate PDF recibo
    try:
        pago_data = {
            "id": pago.id,
            "numero_recibo": pago.numero_recibo,
            "tipo_pago": pago.tipo_pago.value,
            "importe": float(pago.importe),
            "fecha_recepcion": pago.fecha_recepcion.isoformat(),
            "estado": pago.estado.value,
            "observacion": pago.observacion,
            "ch_numero": pago.ch_numero,
            "ch_banco": pago.ch_banco,
            "ch_fecha": pago.ch_fecha.isoformat() if pago.ch_fecha else None,
            "ch_vto": pago.ch_vto.isoformat() if pago.ch_vto else None,
            "transferencia_numero": pago.transferencia_numero,
            "transferencia_fecha": pago.transferencia_fecha.isoformat() if pago.transferencia_fecha else None,
            "retencion_tipo": pago.retencion_tipo,
            "retencion_numero": pago.retencion_numero,
        }
        cliente_data = {
            "id": cliente.id,
            "nombre": cliente.nombre,
            "cuit": cliente.cuit,
            "domicilio": cliente.domicilio,
            "localidad": cliente.localidad_rel.nombre if cliente.localidad_rel else "",
        }
        receptor_nombre = current_user.nombre_completo
        pdf_path = generate_pago_recibo_pdf(pago_data, cliente_data, receptor_nombre)
        pago.recibo_pdf_path = pdf_path
    except Exception:
        pass

    await db.commit()

    # Reload with all relationships for the response
    reload_query = (
        select(Pago)
        .where(Pago.id == pago.id)
        .options(
            selectinload(Pago.cliente),
            selectinload(Pago.receptor),
            selectinload(Pago.imputaciones).selectinload(PagoImputacion.pedido),
            selectinload(Pago.pagos_proveedor).selectinload(PagoProveedor.proveedor),
        )
    )
    result = await db.execute(reload_query)
    pago = result.scalar_one()

    return _build_pago_response(pago, pago.imputaciones, pago.pagos_proveedor)


@router.patch("/{id}/estado")
async def update_pago_estado(
    id: int,
    body: PagoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(
        select(Pago).where(Pago.id == id).options(
            selectinload(Pago.cliente),
            selectinload(Pago.receptor),
            selectinload(Pago.imputaciones).selectinload(PagoImputacion.pedido),
            selectinload(Pago.pagos_proveedor).selectinload(PagoProveedor.proveedor),
        )
    )
    pago = result.scalar_one_or_none()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")

    if body.estado:
        try:
            pago.estado = EstadoPago(body.estado)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Estado inválido: {body.estado}")

    if body.observacion is not None:
        pago.observacion = body.observacion

    await db.commit()
    await db.refresh(pago)
    return _build_pago_response(pago, pago.imputaciones, pago.pagos_proveedor)


@router.post("/{id}/imputar")
async def imputar_pago(
    id: int,
    body: PagoBulkImputarRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(
        select(Pago).where(Pago.id == id).options(selectinload(Pago.cliente), selectinload(Pago.receptor))
    )
    pago = result.scalar_one_or_none()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")

    existing_total_result = await db.execute(
        select(func.coalesce(func.sum(PagoImputacion.monto), 0)).where(PagoImputacion.pago_id == id)
    )
    existing_total = float(existing_total_result.scalar_one())

    total_new = sum(imp.monto for imp in body.imputaciones)
    if existing_total + total_new > float(pago.importe):
        raise HTTPException(
            status_code=400,
            detail=f"El total de imputaciones ({existing_total + total_new}) excede el importe del pago ({float(pago.importe)})",
        )

    if total_new > float(pago.saldo_restante):
        raise HTTPException(
            status_code=400,
            detail=f"El monto a imputar ({total_new}) excede el saldo restante del pago ({float(pago.saldo_restante)})",
        )

    created_imputaciones = []
    for imp in body.imputaciones:
        ped_result = await db.execute(select(Pedido).where(Pedido.id == imp.pedido_id))
        pedido = ped_result.scalar_one_or_none()
        if not pedido:
            raise HTTPException(status_code=404, detail=f"Pedido id {imp.pedido_id} no encontrado")
        if pedido.cliente_id != pago.cliente_id:
            raise HTTPException(status_code=400, detail=f"Pedido {imp.pedido_id} no pertenece al mismo cliente")

        imputacion = PagoImputacion(
            pago_id=id,
            pedido_id=imp.pedido_id,
            monto=Decimal(str(imp.monto)),
            observacion=imp.observacion,
        )
        db.add(imputacion)
        created_imputaciones.append(imputacion)

        pedido.saldo_pendiente -= Decimal(str(imp.monto))
        pedido.payment_status = EstadoPagoPedido.pagado if pedido.saldo_pendiente <= 0 else EstadoPagoPedido.parcial

    pago.saldo_restante -= Decimal(str(total_new))
    pago.estado = EstadoPago.imputado if pago.saldo_restante <= 0 else EstadoPago.imputado_parcial
    await db.commit()

    return {
        "message": f"{len(created_imputaciones)} imputaciones creadas",
        "pago_estado": pago.estado.value,
        "imputaciones": [
            PagoImputacionResponse(
                id=imp.id,
                pago_id=imp.pago_id,
                pedido_id=imp.pedido_id,
                monto=float(imp.monto),
                observacion=imp.observacion,
                created_at=imp.created_at,
            )
            for imp in created_imputaciones
        ],
    }


@router.post("/imputar-bulk")
async def imputar_bulk(
    pago_ids: list[int],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    updated = 0
    for pid in pago_ids:
        result = await db.execute(select(Pago).where(Pago.id == pid))
        pago = result.scalar_one_or_none()
        if pago and pago.estado == EstadoPago.recibido:
            pago.estado = EstadoPago.imputado
            updated += 1

    await db.commit()
    return {"message": f"{updated} pagos imputados", "updated": updated}


@router.get("/{id}/recibo")
async def get_recibo_pdf(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Pago)
        .where(Pago.id == id)
        .options(
            selectinload(Pago.cliente).selectinload(Cliente.localidad_rel),
            selectinload(Pago.receptor),
        )
    )
    pago = result.scalar_one_or_none()
    if pago is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pago no encontrado",
        )

    pago_data = {
        "id": pago.id,
        "numero_recibo": pago.numero_recibo,
        "tipo_pago": pago.tipo_pago.value,
        "importe": float(pago.importe),
        "fecha_recepcion": pago.fecha_recepcion.isoformat() if pago.fecha_recepcion else "",
        "estado": pago.estado.value,
        "observacion": pago.observacion,
        "ch_numero": pago.ch_numero,
        "ch_banco": pago.ch_banco,
        "ch_fecha": pago.ch_fecha.isoformat() if pago.ch_fecha else None,
        "ch_vto": pago.ch_vto.isoformat() if pago.ch_vto else None,
        "transferencia_numero": pago.transferencia_numero,
        "transferencia_fecha": pago.transferencia_fecha.isoformat() if pago.transferencia_fecha else None,
        "retencion_tipo": pago.retencion_tipo,
        "retencion_numero": pago.retencion_numero,
    }
    cliente_data = {
        "nombre": pago.cliente.nombre if pago.cliente else "",
        "cuit": pago.cliente.cuit if pago.cliente else "-",
        "domicilio": pago.cliente.domicilio if pago.cliente else "",
        "localidad": pago.cliente.localidad_rel.nombre if pago.cliente and pago.cliente.localidad_rel else "",
        "razon_social": pago.cliente.razon_social if pago.cliente else "-",
        "telefono": pago.cliente.telefono if pago.cliente else "-",
    }
    receptor_nombre = pago.receptor.nombre_completo if pago.receptor else ""

    filename = generate_pago_recibo_pdf(pago_data, cliente_data, receptor_nombre)

    full_path = os.path.join(settings.PDF_STORAGE_PATH, filename)
    return FileResponse(
        path=full_path,
        media_type="application/pdf",
        filename=filename,
    )

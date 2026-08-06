import asyncio
from decimal import Decimal
from datetime import timedelta, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.producto import Producto
from app.models.proveedor import Proveedor
from app.models.ingreso_mercaderia import IngresoMercaderia, IngresoMercaderiaItem
from app.models.pago_proveedor import PagoProveedorImputacion
from app.schemas.ingreso_mercaderia import (
    IngresoImputacionResponse,
    IngresoMercaderiaCreate,
    IngresoMercaderiaResponse,
    IngresoMercaderiaItemResponse,
)
from app.services.pdf_service import generate_orden_compra_pdf
from app.services.s3_service import upload_ingreso_archivo, delete_s3_file
from app.utils.deps import get_current_user, require_role

router = APIRouter()


def _build_response(ingreso: IngresoMercaderia) -> IngresoMercaderiaResponse:
    items = [
        IngresoMercaderiaItemResponse(
            id=item.id,
            producto_id=item.producto_id,
            producto_nombre=item.producto.nombre if item.producto else None,
            cantidad_cajas=item.cantidad_cajas,
            cantidad_blisters=item.cantidad_blisters,
            costo_unitario=float(item.costo_unitario) if item.costo_unitario else None,
        )
        for item in ingreso.items
    ]
    imputaciones = [
        IngresoImputacionResponse(
            id=imp.id,
            pago_proveedor_id=imp.pago_proveedor_id,
            importe_aplicado=imp.importe_aplicado,
            fecha_pago=imp.pago_proveedor.fecha_pago if imp.pago_proveedor else imp.created_at,
            tipo_pago=imp.pago_proveedor.tipo_pago.value if imp.pago_proveedor else "",
            referencia_pago=imp.pago_proveedor.referencia_pago if imp.pago_proveedor else None,
        )
        for imp in ingreso.imputaciones
    ]
    return IngresoMercaderiaResponse(
        id=ingreso.id,
        numero=ingreso.numero,
        fecha=ingreso.fecha,
        destino=ingreso.destino or "A",
        proveedor_id=ingreso.proveedor_id,
        proveedor_nombre=ingreso.proveedor.nombre if ingreso.proveedor else None,
        numero_comprobante=ingreso.numero_comprobante or "",
        observacion=ingreso.observacion,
        creado_por_id=ingreso.creado_por_id,
        creado_por_nombre=ingreso.creado_por.nombre_completo if ingreso.creado_por else None,
        items=items,
        imputaciones=imputaciones,
        importe_total=float(ingreso.importe_total),
        saldo_pendiente=float(ingreso.saldo_pendiente),
        fecha_vencimiento=ingreso.fecha_vencimiento,
        dias_plazo=ingreso.dias_plazo,
        created_at=ingreso.created_at,
        updated_at=ingreso.updated_at,
        archivo_url=ingreso.archivo_url,
    )


async def _load_ingreso(id: int, db: AsyncSession) -> IngresoMercaderia:
    result = await db.execute(
        select(IngresoMercaderia)
        .where(IngresoMercaderia.id == id)
        .options(
            selectinload(IngresoMercaderia.proveedor),
            selectinload(IngresoMercaderia.creado_por),
            selectinload(IngresoMercaderia.items).selectinload(IngresoMercaderiaItem.producto),
            selectinload(IngresoMercaderia.imputaciones).selectinload(PagoProveedorImputacion.pago_proveedor),
        )
    )
    ingreso = result.scalar_one_or_none()
    if not ingreso:
        raise HTTPException(status_code=404, detail="Ingreso no encontrado")
    return ingreso


@router.get("")
async def list_ingresos(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    solo_pendientes: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base_query = select(IngresoMercaderia)

    if solo_pendientes:
        base_query = base_query.where(IngresoMercaderia.saldo_pendiente > 0)

    count_q = select(func.count()).select_from(base_query.with_only_columns(IngresoMercaderia.id).subquery())
    total = (await db.execute(count_q)).scalar_one()

    data_query = (
        base_query.options(
            selectinload(IngresoMercaderia.proveedor),
            selectinload(IngresoMercaderia.creado_por),
            selectinload(IngresoMercaderia.items).selectinload(IngresoMercaderiaItem.producto),
            selectinload(IngresoMercaderia.imputaciones).selectinload(PagoProveedorImputacion.pago_proveedor),
        )
        .order_by(IngresoMercaderia.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(data_query)
    ingresos = result.scalars().unique().all()

    return {
        "items": [_build_response(i) for i in ingresos],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ingreso(
    body: IngresoMercaderiaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    # Auto-generate numero
    max_result = await db.execute(
        select(func.max(IngresoMercaderia.numero)).where(IngresoMercaderia.numero.like("ING-%"))
    )
    max_num = max_result.scalar_one()
    next_num = int(max_num.replace("ING-", "")) + 1 if max_num else 1
    numero = f"ING-{next_num:05d}"

    ingreso = IngresoMercaderia(
        numero=numero,
        fecha=body.fecha,
        proveedor_id=body.proveedor_id,
        numero_comprobante=body.numero_comprobante,
        observacion=body.observacion,
        creado_por_id=current_user.id,
        fecha_vencimiento=body.fecha_vencimiento,
        dias_plazo=body.dias_plazo,
        destino=body.destino.upper(),
    )

    # Auto-calculate fecha_vencimiento if not provided but dias_plazo exists
    if not ingreso.fecha_vencimiento and ingreso.dias_plazo:
        ingreso.fecha_vencimiento = datetime.combine(ingreso.fecha, datetime.min.time()) + timedelta(days=ingreso.dias_plazo)

    db.add(ingreso)
    await db.flush()

    for item_data in body.items:
        # Validate and update stock/pricing
        prod_result = await db.execute(
            select(Producto).where(Producto.id == item_data.producto_id).with_for_update()
        )
        producto = prod_result.scalar_one_or_none()
        if not producto:
            raise HTTPException(status_code=404, detail=f"Producto id {item_data.producto_id} no encontrado")

        # Update Stock
        if body.destino.upper() == "B":
            producto.modify_stock_b(item_data.cantidad_cajas, item_data.cantidad_blisters)
        else:
            producto.modify_stock_a(item_data.cantidad_cajas, item_data.cantidad_blisters)

        costo_unit = Decimal(str(item_data.costo_unitario)) if item_data.costo_unitario else Decimal("0")
        total_ingreso_item = costo_unit * item_data.cantidad_cajas

        item = IngresoMercaderiaItem(
            ingreso_id=ingreso.id,
            producto_id=item_data.producto_id,
            cantidad_cajas=item_data.cantidad_cajas,
            cantidad_blisters=item_data.cantidad_blisters,
            costo_unitario=costo_unit,
        )
        db.add(item)
        ingreso.importe_total += total_ingreso_item

    # Actualizar saldo del proveedor
    if ingreso.proveedor_id:
        prov_result = await db.execute(select(Proveedor).where(Proveedor.id == ingreso.proveedor_id))
        proveedor = prov_result.scalar_one_or_none()
        if proveedor:
            proveedor.saldo_remito += ingreso.importe_total
            ingreso.saldo_pendiente = ingreso.importe_total

    await db.commit()

    # Reload
    ingreso = await _load_ingreso(ingreso.id, db)
    return _build_response(ingreso)


@router.get("/{id}/pdf")
async def get_ingreso_pdf(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    ingreso = await _load_ingreso(id, db)

    ingreso_data = {
        "numero": ingreso.numero,
        "fecha": str(ingreso.fecha),
        "numero_comprobante": ingreso.numero_comprobante,
        "destino": ingreso.destino,
        "observacion": ingreso.observacion,
        "dias_plazo": ingreso.dias_plazo,
        "fecha_vencimiento": str(ingreso.fecha_vencimiento)[:10] if ingreso.fecha_vencimiento else None,
        "importe_total": float(ingreso.importe_total),
        "saldo_pendiente": float(ingreso.saldo_pendiente),
        "creado_por_nombre": ingreso.creado_por.nombre_completo if ingreso.creado_por else None,
        "created_at": str(ingreso.created_at),
    }

    proveedor = ingreso.proveedor
    proveedor_data = {
        "nombre": proveedor.nombre if proveedor else None,
        "direccion": proveedor.direccion if proveedor else None,
        "telefono": proveedor.telefono if proveedor else None,
        "contacto_nombre": proveedor.contacto_nombre if proveedor else None,
        "contacto_telefono": proveedor.contacto_telefono if proveedor else None,
        "contacto_email": proveedor.contacto_email if proveedor else None,
    }

    items = [
        {
            "producto_id": item.producto_id,
            "producto_nombre": item.producto.nombre if item.producto else None,
            "cantidad_cajas": item.cantidad_cajas,
            "cantidad_blisters": item.cantidad_blisters,
            "costo_unitario": float(item.costo_unitario) if item.costo_unitario else None,
        }
        for item in ingreso.items
    ]

    pagos = [
        {
            "fecha_pago": str(imp.pago_proveedor.fecha_pago) if imp.pago_proveedor else str(imp.created_at),
            "tipo_pago": imp.pago_proveedor.tipo_pago.value if imp.pago_proveedor else "",
            "referencia_pago": imp.pago_proveedor.referencia_pago if imp.pago_proveedor else None,
            "importe_aplicado": float(imp.importe_aplicado),
        }
        for imp in ingreso.imputaciones
    ] or None

    import os
    filename = generate_orden_compra_pdf(ingreso_data, proveedor_data, items, pagos=pagos)
    full_path = os.path.join(settings.PDF_STORAGE_PATH, filename)
    return FileResponse(path=full_path, media_type="application/pdf", filename=filename)


@router.post("/{id}/archivo")
async def upload_archivo(
    id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF")

    ingreso = await _load_ingreso(id, db)
    content = await file.read()
    proveedor_nombre = ingreso.proveedor.nombre if ingreso.proveedor else ""
    _, url = await asyncio.to_thread(
        upload_ingreso_archivo,
        content,
        file.content_type,
        proveedor_nombre,
        ingreso.numero,
        file.filename or "factura.pdf",
    )
    ingreso.archivo_url = url
    await db.commit()
    ingreso = await _load_ingreso(id, db)
    return _build_response(ingreso)


@router.delete("/{id}/archivo")
async def delete_archivo(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    ingreso = await _load_ingreso(id, db)
    if not ingreso.archivo_url:
        raise HTTPException(status_code=404, detail="No hay archivo adjunto")

    key = ingreso.archivo_url.replace(f"{settings.S3_URL}/", "")
    await asyncio.to_thread(delete_s3_file, key)
    ingreso.archivo_url = None
    await db.commit()
    ingreso = await _load_ingreso(id, db)
    return _build_response(ingreso)

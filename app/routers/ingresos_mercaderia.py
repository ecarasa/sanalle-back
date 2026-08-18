import asyncio
from decimal import Decimal
from datetime import timedelta, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.producto import Producto
from app.models.proveedor import Proveedor
from app.models.ingreso_mercaderia import IngresoMercaderia, IngresoMercaderiaItem, IngresoImpuesto
from app.models.pago_proveedor import PagoProveedorImputacion
from app.schemas.ingreso_mercaderia import (
    IngresoImputacionResponse,
    IngresoImpuestoResponse,
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
    impuestos = [
        IngresoImpuestoResponse(
            id=imp.id,
            tipo_iva_id=imp.tipo_iva_id,
            concepto=imp.concepto,
            base=float(imp.base),
            tasa=float(imp.tasa),
            importe=float(imp.importe),
        )
        for imp in ingreso.impuestos
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
        impuestos=impuestos,
        imputaciones=imputaciones,
        subtotal_neto=float(ingreso.subtotal_neto),
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
            selectinload(IngresoMercaderia.impuestos),
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
            selectinload(IngresoMercaderia.impuestos),
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

    subtotal_neto = Decimal("0")
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

        # Neto del renglón: costo por caja contemplando también los blisters (fracción de caja).
        costo_unit = Decimal(str(item_data.costo_unitario)) if item_data.costo_unitario else Decimal("0")
        blisters_por_caja = Decimal(str(producto.get_blisters_por_caja() or 1))
        cantidad_en_cajas = Decimal(item_data.cantidad_cajas) + (
            Decimal(item_data.cantidad_blisters) / blisters_por_caja if blisters_por_caja else Decimal("0")
        )
        neto_item = (costo_unit * cantidad_en_cajas).quantize(Decimal("0.01"))

        item = IngresoMercaderiaItem(
            ingreso_id=ingreso.id,
            producto_id=item_data.producto_id,
            cantidad_cajas=item_data.cantidad_cajas,
            cantidad_blisters=item_data.cantidad_blisters,
            costo_unitario=costo_unit,
        )
        db.add(item)
        subtotal_neto += neto_item

    # Impuestos / percepciones de cabecera (IVA 21, 10.5, IIBB…): sobre el neto por defecto.
    total_impuestos = Decimal("0")
    for imp_data in body.impuestos:
        base = Decimal(str(imp_data.base)) if imp_data.base is not None else subtotal_neto
        tasa = Decimal(str(imp_data.tasa or 0))
        if imp_data.importe is not None:
            importe = Decimal(str(imp_data.importe))
        else:
            importe = (base * tasa / Decimal("100")).quantize(Decimal("0.01"))
        db.add(IngresoImpuesto(
            ingreso_id=ingreso.id,
            tipo_iva_id=imp_data.tipo_iva_id,
            concepto=imp_data.concepto,
            base=base.quantize(Decimal("0.01")),
            tasa=tasa,
            importe=importe,
        ))
        total_impuestos += importe

    ingreso.subtotal_neto = subtotal_neto.quantize(Decimal("0.01"))
    ingreso.importe_total = (subtotal_neto + total_impuestos).quantize(Decimal("0.01"))

    # Actualizar saldo del proveedor (deuda por el total con impuestos)
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


@router.delete("")
async def eliminar_todos_ingresos(
    confirmar: str = Query(..., description="Debe ser 'ELIMINAR' para confirmar el borrado total"),
    revertir_stock: bool = Query(True, description="Descuenta del stock lo que estas compras habían ingresado"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Elimina TODOS los registros de compra (ingresos de mercadería) con sus items,
    impuestos e imputaciones de pago.

    Operación destructiva e irreversible. Deja el estado consistente:
    - Si `revertir_stock` (por defecto), descuenta del stock las cantidades que cada
      compra había ingresado (según su destino A/B).
    - Resta del `saldo_remito` de cada proveedor el `importe_total` que la compra le había sumado.

    Nota: no borra los pagos a proveedor (`pagos_proveedor`); solo desvincula sus
    imputaciones contra estas compras. Si querés borrar también los pagos, usá el
    botón de "Eliminar todas" en Transacciones.
    """
    if confirmar != "ELIMINAR":
        raise HTTPException(status_code=400, detail="Confirmación inválida")

    # Cargar todo con items + producto para poder revertir stock y saldo de proveedor.
    result = await db.execute(
        select(IngresoMercaderia).options(
            selectinload(IngresoMercaderia.items).selectinload(IngresoMercaderiaItem.producto),
        )
    )
    ingresos = result.scalars().unique().all()

    if not ingresos:
        return {"eliminados": 0, "detalle": {"ingresos": 0, "items": 0, "impuestos": 0, "imputaciones": 0}}

    # Revertir stock (opcional) y acumular la deuda a restar por proveedor.
    proveedor_deltas: dict[int, Decimal] = {}
    for ing in ingresos:
        if revertir_stock:
            destino_b = (ing.destino or "A").upper() == "B"
            for item in ing.items:
                if not item.producto:
                    continue
                if destino_b:
                    item.producto.modify_stock_b(-item.cantidad_cajas, -item.cantidad_blisters)
                else:
                    item.producto.modify_stock_a(-item.cantidad_cajas, -item.cantidad_blisters)
        if ing.proveedor_id:
            proveedor_deltas[ing.proveedor_id] = (
                proveedor_deltas.get(ing.proveedor_id, Decimal("0")) + (ing.importe_total or Decimal("0"))
            )

    if proveedor_deltas:
        provs = (
            await db.execute(select(Proveedor).where(Proveedor.id.in_(proveedor_deltas.keys())))
        ).scalars().all()
        for p in provs:
            p.saldo_remito = (p.saldo_remito or Decimal("0")) - proveedor_deltas.get(p.id, Decimal("0"))

    await db.flush()

    # Borrado en orden seguro respecto de las FKs.
    # pago_proveedor_imputaciones.ingreso_mercaderia_id es ondelete=RESTRICT: borrarlas primero.
    borrados: dict[str, int] = {}
    borrados["imputaciones"] = (await db.execute(sa_delete(PagoProveedorImputacion))).rowcount
    # items e impuestos tienen ondelete=CASCADE, pero los borramos explícito para reportar el conteo.
    borrados["impuestos"] = (await db.execute(sa_delete(IngresoImpuesto))).rowcount
    borrados["items"] = (await db.execute(sa_delete(IngresoMercaderiaItem))).rowcount
    borrados["ingresos"] = (await db.execute(sa_delete(IngresoMercaderia))).rowcount

    await db.commit()

    return {"eliminados": borrados["ingresos"], "detalle": borrados}


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

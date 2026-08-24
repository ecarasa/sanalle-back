from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from decimal import Decimal

from app.core.database import get_db
from app.models.user import User
from app.models.cliente import Cliente
from app.models.nota_credito_debito import NotaCreditoDebito, NotaCreditoItem, TipoNota
from app.models.producto import Producto
from app.models.movimiento_stock import MovimientoStock
from app.models.pago import TipoCuenta
from app.services import stock_service
from app.schemas.nota_credito_debito import (
    NotaCreditoDebitoCreate,
    NotaCreditoDebitoResponse,
    NotaCreditoItemResponse,
)
from app.utils.deps import get_current_user, require_role

router = APIRouter()


def _build_response(nota: NotaCreditoDebito) -> NotaCreditoDebitoResponse:
    items = [
        NotaCreditoItemResponse(
            id=item.id,
            producto_id=item.producto_id,
            descripcion=item.descripcion,
            cantidad_cajas=item.cantidad_cajas,
            cantidad_blisters=item.cantidad_blisters,
            precio_unitario=float(item.precio_unitario),
            precio_total=float(item.precio_total),
        )
        for item in nota.items
    ]
    return NotaCreditoDebitoResponse(
        id=nota.id,
        numero=nota.numero,
        tipo=nota.tipo.value,
        cliente_id=nota.cliente_id,
        cliente_nombre=nota.cliente.nombre if nota.cliente else None,
        fecha=nota.fecha,
        importe_total=float(nota.importe_total),
        motivo=nota.motivo,
        pedido_id=nota.pedido_id,
        creado_por_id=nota.creado_por_id,
        creado_por_nombre=nota.creado_por.nombre_completo if nota.creado_por else None,
        tipo_cuenta=nota.tipo_cuenta.value,
        afecta_stock=nota.afecta_stock,
        deposito_id=nota.deposito_id,
        deposito_nombre=nota.deposito.nombre if nota.deposito else None,
        items=items,
        created_at=nota.created_at,
    )


@router.get("")
async def list_notas(
    tipo: str | None = Query(None),
    cliente_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base_query = select(NotaCreditoDebito)
    filters = []
    if tipo:
        filters.append(NotaCreditoDebito.tipo == TipoNota(tipo))
    if cliente_id:
        filters.append(NotaCreditoDebito.cliente_id == cliente_id)
    if filters:
        base_query = base_query.where(*filters)

    count_q = select(func.count()).select_from(base_query.with_only_columns(NotaCreditoDebito.id).subquery())
    total = (await db.execute(count_q)).scalar_one()

    data_query = (
        base_query.options(
            selectinload(NotaCreditoDebito.cliente),
            selectinload(NotaCreditoDebito.creado_por),
            selectinload(NotaCreditoDebito.items),
        )
        .order_by(NotaCreditoDebito.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(data_query)
    notas = result.scalars().unique().all()

    return {
        "items": [_build_response(n) for n in notas],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{id}")
async def get_nota(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(NotaCreditoDebito)
        .where(NotaCreditoDebito.id == id)
        .options(
            selectinload(NotaCreditoDebito.cliente),
            selectinload(NotaCreditoDebito.creado_por),
            selectinload(NotaCreditoDebito.items),
        )
    )
    result = await db.execute(query)
    nota = result.scalar_one_or_none()
    if not nota:
        raise HTTPException(status_code=404, detail="Nota no encontrada")
    return _build_response(nota)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_nota(
    body: NotaCreditoDebitoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    # Validate cliente
    cliente_result = await db.execute(select(Cliente).where(Cliente.id == body.cliente_id))
    if not cliente_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    # Validate tipo
    try:
        tipo_enum = TipoNota(body.tipo)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Tipo inválido: {body.tipo}")

    # Validate tipo_cuenta
    try:
        tipo_cuenta_enum = TipoCuenta(body.tipo_cuenta)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de cuenta inválido: {body.tipo_cuenta}. Valores válidos: {[t.value for t in TipoCuenta]}",
        )

    # Auto-generate numero
    prefix = "NC" if tipo_enum == TipoNota.credito else "ND"
    max_result = await db.execute(
        select(func.max(NotaCreditoDebito.numero)).where(
            NotaCreditoDebito.numero.like(f"{prefix}-%")
        )
    )
    max_num = max_result.scalar_one()
    if max_num:
        next_num = int(max_num.replace(f"{prefix}-", "")) + 1
    else:
        next_num = 1
    numero = f"{prefix}-{next_num:05d}"

    # Calculate total from items
    importe_total = sum(Decimal(str(item.precio_total)) for item in body.items)

    # Una nota que mueve stock tiene que decir de qué depósito lo mueve; si no,
    # no habría forma de saber a qué góndola vuelve la devolución.
    deposito_id = None
    if body.afecta_stock:
        deposito_id = (await stock_service.validar_deposito(db, body.deposito_id)).id

    nota = NotaCreditoDebito(
        numero=numero,
        tipo=tipo_enum,
        cliente_id=body.cliente_id,
        fecha=body.fecha,
        importe_total=importe_total,
        motivo=body.motivo,
        pedido_id=body.pedido_id,
        creado_por_id=current_user.id,
        tipo_cuenta=tipo_cuenta_enum,
        afecta_stock=body.afecta_stock,
        deposito_id=deposito_id,
    )
    db.add(nota)
    await db.flush()

    for item_data in body.items:
        item = NotaCreditoItem(
            nota_id=nota.id,
            producto_id=item_data.producto_id,
            descripcion=item_data.descripcion,
            cantidad_cajas=item_data.cantidad_cajas,
            cantidad_blisters=item_data.cantidad_blisters,
            unidad_venta=getattr(item_data, "unidad_venta", "caja") or "caja",
            precio_unitario=Decimal(str(item_data.precio_unitario)),
            precio_total=Decimal(str(item_data.precio_total)),
        )
        db.add(item)
        
        # Handle stock impact
        if body.afecta_stock and item_data.producto_id:
            prod_res = await db.execute(select(Producto).where(Producto.id == item_data.producto_id))
            producto = prod_res.scalar_one_or_none()
            if producto:
                # Nota de crédito = devolución: la mercadería vuelve al depósito.
                # Nota de débito = salida extra: sale del depósito.
                es_credito = tipo_enum == TipoNota.credito
                multiplier = 1 if es_credito else -1
                await stock_service.ajustar(
                    db,
                    producto,
                    deposito_id,
                    item_data.cantidad_cajas * multiplier,
                    item_data.cantidad_blisters * multiplier,
                )

                db.add(
                    MovimientoStock(
                        producto_id=producto.id,
                        usuario_id=current_user.id,
                        tipo_operacion="NC_RETURN" if es_credito else "ND_ADJUST",
                        deposito_origen_id=None if es_credito else deposito_id,
                        deposito_destino_id=deposito_id if es_credito else None,
                        cantidad_cajas=item_data.cantidad_cajas,
                        cantidad_blisters=item_data.cantidad_blisters,
                        observacion=f"{prefix} {numero}: {body.motivo or ''}",
                    )
                )

    await db.commit()

    # Reload
    reload_query = (
        select(NotaCreditoDebito)
        .where(NotaCreditoDebito.id == nota.id)
        .options(
            selectinload(NotaCreditoDebito.cliente),
            selectinload(NotaCreditoDebito.creado_por),
            selectinload(NotaCreditoDebito.items),
        )
    )
    result = await db.execute(reload_query)
    nota = result.scalar_one()
    return _build_response(nota)

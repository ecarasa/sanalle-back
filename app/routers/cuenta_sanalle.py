from app.services import movimientos_service
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Optional

from app.core.database import get_db
from app.models.cuenta_sanalle import CuentaSanalle, TipoMovimiento, CategoriaMovimiento
from app.models.pago import TipoPago
from app.schemas.cuenta_sanalle import CuentaSanalleCreate, CuentaSanalleResponse
from app.services.movimientos_service import registrar_movimiento
from app.utils.deps import get_current_user, require_role
from app.models.user import User

router = APIRouter()


@router.get("")
async def list_movimientos(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    tipo: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista los movimientos del Libro Mayor (Cuenta Sanalle).
    """
    base_query = select(CuentaSanalle)

    filters = []
    categoria_filters = []

    if tipo:
        try:
            filters.append(CuentaSanalle.tipo == TipoMovimiento(tipo))
        except ValueError:
            raise HTTPException(status_code=400, detail="Tipo de movimiento inválido")

    if categoria:
        try:
            cat_filter = CuentaSanalle.categoria == CategoriaMovimiento(categoria)
            filters.append(cat_filter)
            categoria_filters.append(cat_filter)
        except ValueError:
            raise HTTPException(status_code=400, detail="Categoría de movimiento inválida")

    if filters:
        base_query = base_query.where(and_(*filters))

    # Count total
    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Balance queries: tipo is already constrained per query, only apply categoria filter
    balance_ingresos_q = select(func.sum(CuentaSanalle.importe)).where(CuentaSanalle.tipo == TipoMovimiento.ingreso)
    balance_egresos_q = select(func.sum(CuentaSanalle.importe)).where(CuentaSanalle.tipo == TipoMovimiento.egreso)

    if categoria_filters:
        balance_ingresos_q = balance_ingresos_q.where(and_(*categoria_filters))
        balance_egresos_q = balance_egresos_q.where(and_(*categoria_filters))
        
    ingresos_total = (await db.execute(balance_ingresos_q)).scalar() or 0
    egresos_total = (await db.execute(balance_egresos_q)).scalar() or 0

    # Desglose por método de pago
    metodo_q = (
        select(
            CuentaSanalle.metodo_pago,
            CuentaSanalle.tipo,
            func.sum(CuentaSanalle.importe).label("total"),
        )
        .group_by(CuentaSanalle.metodo_pago, CuentaSanalle.tipo)
    )
    if categoria_filters:
        metodo_q = metodo_q.where(and_(*categoria_filters))
    metodo_rows = (await db.execute(metodo_q)).all()

    por_metodo: dict = {}
    for row in metodo_rows:
        key = row.metodo_pago.value
        if key not in por_metodo:
            por_metodo[key] = {"ingresos": 0.0, "egresos": 0.0, "balance": 0.0}
        if row.tipo == TipoMovimiento.ingreso:
            por_metodo[key]["ingresos"] = float(row.total)
        else:
            por_metodo[key]["egresos"] = float(row.total)
        por_metodo[key]["balance"] = por_metodo[key]["ingresos"] - por_metodo[key]["egresos"]

    # Paged query
    query = base_query.order_by(CuentaSanalle.fecha.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    movimientos = result.scalars().all()
    
    # Convert to schema-compatible dicts
    items = [CuentaSanalleResponse.model_validate(m).model_dump() for m in movimientos]
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "resumen": {
            "ingresos": float(ingresos_total),
            "egresos": float(egresos_total),
            "balance": float(ingresos_total - egresos_total),
            "por_metodo": por_metodo,
        }
    }


@router.post("", response_model=CuentaSanalleResponse, status_code=status.HTTP_201_CREATED)
async def create_movimiento_manual(
    body: CuentaSanalleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """
    Permite registrar un movimiento manual en el Libro Mayor (solo admin).
    """
    try:
        tipo_enum = TipoMovimiento(body.tipo)
        cat_enum = CategoriaMovimiento(body.categoria)
        metodo_enum = TipoPago(body.metodo_pago)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    movimiento = await registrar_movimiento(
        db=db,
        tipo=tipo_enum,
        categoria=cat_enum,
        importe=body.importe,
        metodo_pago=metodo_enum,
        usuario_id=current_user.id,
        descripcion=body.descripcion,
        referencia_id=body.referencia_id,
        fecha=body.fecha
    )
    
    await db.commit()
    await db.refresh(movimiento)
    return movimiento


@router.get("/balance_neto")
async def obtener_balance_neto(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """
    Obtiene el balance neto del usuario actual.
    """
    # Get balance total (ingresos - egresos)
    
    balance_ingresos_q = select(func.sum(CuentaSanalle.importe)).where(CuentaSanalle.tipo == TipoMovimiento.ingreso)
    balance_egresos_q = select(func.sum(CuentaSanalle.importe)).where(CuentaSanalle.tipo == TipoMovimiento.egreso)
    
        
    ingresos_total = (await db.execute(balance_ingresos_q)).scalar() or 0
    egresos_total = (await db.execute(balance_egresos_q)).scalar() or 0
    
    total_neto = float(ingresos_total - egresos_total)
    
    return {
        "total": total_neto
    }
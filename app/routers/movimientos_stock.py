from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.movimiento_stock import MovimientoStock
from app.models.producto import Producto
from app.models.user import User
from app.models.toma_inventario import TomaInventario
from app.schemas.movimiento_stock import MovimientoStockResponse
from app.schemas.stock import MOTIVOS_LABEL, MOTIVOS_MERMA
from app.utils.deps import get_current_user

router = APIRouter()

@router.get("")
async def list_movimientos_stock(
    search: str = Query(""),
    producto_id: int | None = Query(None),
    deposito_id: int | None = Query(None),
    tipo_operacion: str | None = Query(None),
    motivo: str | None = Query(None, description="recuento_fisico, rotura, vencido, ..."),
    solo_mermas: bool = Query(False, description="Solo los motivos que son pérdida de mercadería"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = select(MovimientoStock).join(Producto).options(
        selectinload(MovimientoStock.producto),
        selectinload(MovimientoStock.usuario)
    ).order_by(desc(MovimientoStock.created_at))

    if search:
        query = query.where(Producto.nombre.ilike(f"%{search}%"))
    if producto_id:
        query = query.where(MovimientoStock.producto_id == producto_id)
    if deposito_id:
        # Cuenta tanto lo que entró como lo que salió de ese depósito.
        query = query.where(
            or_(
                MovimientoStock.deposito_origen_id == deposito_id,
                MovimientoStock.deposito_destino_id == deposito_id,
            )
        )
    if tipo_operacion:
        query = query.where(MovimientoStock.tipo_operacion == tipo_operacion)
    if motivo:
        query = query.where(MovimientoStock.motivo == motivo)
    if solo_mermas:
        query = query.where(MovimientoStock.motivo.in_(MOTIVOS_MERMA))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    movimientos = result.scalars().all()

    # Número de la toma de inventario que generó cada movimiento, de una sola vez.
    toma_ids = {m.toma_inventario_id for m in movimientos if m.toma_inventario_id}
    numeros_toma: dict[int, str] = {}
    if toma_ids:
        filas = await db.execute(
            select(TomaInventario.id, TomaInventario.numero).where(TomaInventario.id.in_(toma_ids))
        )
        numeros_toma = {tid: numero for tid, numero in filas.all()}

    items = []
    for m in movimientos:
        res = MovimientoStockResponse.model_validate(m)
        res.producto_nombre = m.producto.nombre if m.producto else "Producto Eliminado"
        res.usuario_nombre = m.usuario.username if m.usuario else "Sistema"
        res.deposito_origen_nombre = m.deposito_origen.nombre if m.deposito_origen else None
        res.deposito_destino_nombre = m.deposito_destino.nombre if m.deposito_destino else None
        res.motivo_label = MOTIVOS_LABEL.get(m.motivo or "")
        res.toma_numero = numeros_toma.get(m.toma_inventario_id)
        items.append(res)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }

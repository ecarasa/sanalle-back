from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.user import User
from app.models.zona import Zona
from app.schemas.zona import ZonaCreate, ZonaUpdate, ZonaResponse
from app.utils.deps import get_current_user, require_role

router = APIRouter()

@router.get("")
async def list_zonas(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base_query = select(Zona).where(Zona.activo == True)
    if search:
        base_query = base_query.where(Zona.nombre.ilike(f"%{search}%"))

    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = base_query.order_by(Zona.nombre).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    zonas = result.scalars().all()

    items = [ZonaResponse.model_validate(z) for z in zonas]
    return {"items": items, "total": total, "page": page, "page_size": page_size}

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_zona(
    data: ZonaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    zona = Zona(**data.model_dump())
    db.add(zona)
    await db.commit()
    await db.refresh(zona)
    return ZonaResponse.model_validate(zona)

@router.put("/{id}")
async def update_zona(
    id: int,
    data: ZonaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Zona).where(Zona.id == id))
    zona = result.scalar_one_or_none()
    if not zona:
        raise HTTPException(status_code=404, detail="Zona no encontrada")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(zona, key, value)

    await db.commit()
    await db.refresh(zona)
    return ZonaResponse.model_validate(zona)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zona(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Zona).where(Zona.id == id))
    zona = result.scalar_one_or_none()
    if not zona:
        raise HTTPException(status_code=404, detail="Zona no encontrada")

    try:
        await db.delete(zona)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="No se puede eliminar, tiene registros asociados")

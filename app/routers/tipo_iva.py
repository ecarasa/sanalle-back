from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.user import User
from app.models.tipo_iva import TipoIva
from app.schemas.tipo_iva import TipoIvaCreate, TipoIvaUpdate, TipoIvaResponse
from app.utils.deps import get_current_user, require_role

router = APIRouter()


@router.get("")
async def list_tipo_iva(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base_query = select(TipoIva)
    if search:
        base_query = base_query.where(TipoIva.nombre.ilike(f"%{search}%"))

    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = base_query.order_by(TipoIva.id).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    tipo_ivas = result.scalars().all()

    items = [TipoIvaResponse.model_validate(t).model_dump() for t in tipo_ivas]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{id}")
async def get_tipo_iva(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(TipoIva).where(TipoIva.id == id))
    tipo_iva = result.scalar_one_or_none()
    if not tipo_iva:
        raise HTTPException(status_code=404, detail="Tipo de IVA no encontrado")
    return TipoIvaResponse.model_validate(tipo_iva).model_dump()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tipo_iva(
    data: TipoIvaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    existing = await db.execute(select(TipoIva).where(TipoIva.nombre == data.nombre))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Ya existe un tipo de IVA con ese nombre")

    tipo_iva = TipoIva(**data.model_dump())
    db.add(tipo_iva)
    await db.commit()
    await db.refresh(tipo_iva)
    return TipoIvaResponse.model_validate(tipo_iva).model_dump()


@router.put("/{id}")
async def update_tipo_iva(
    id: int,
    data: TipoIvaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(TipoIva).where(TipoIva.id == id))
    tipo_iva = result.scalar_one_or_none()
    if not tipo_iva:
        raise HTTPException(status_code=404, detail="Tipo de IVA no encontrado")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(tipo_iva, key, value)

    await db.commit()
    await db.refresh(tipo_iva)
    return TipoIvaResponse.model_validate(tipo_iva).model_dump()


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tipo_iva(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(TipoIva).where(TipoIva.id == id))
    tipo_iva = result.scalar_one_or_none()
    if not tipo_iva:
        raise HTTPException(status_code=404, detail="Tipo de IVA no encontrado")

    try:
        await db.delete(tipo_iva)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="No se puede eliminar, tiene registros asociados")

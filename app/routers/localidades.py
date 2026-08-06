from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.user import User
from app.models.localidad import Localidad
from app.schemas.localidad import LocalidadCreate, LocalidadUpdate, LocalidadResponse
from app.utils.deps import get_current_user, require_role

router = APIRouter()


@router.get("")
async def list_localidades(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base_query = select(Localidad).where(Localidad.activo == True)  # noqa: E712
    if search:
        base_query = base_query.where(Localidad.nombre.ilike(f"%{search}%"))

    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = base_query.order_by(Localidad.nombre).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    localidades = result.scalars().all()

    items = [LocalidadResponse.model_validate(l) for l in localidades]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_localidad(
    data: LocalidadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Evitar duplicados por nombre + provincia (normalizados)
    nombre_norm = func.lower(func.btrim(Localidad.nombre))
    provincia_norm = func.coalesce(func.btrim(Localidad.provincia), "")
    existente = (
        await db.execute(
            select(Localidad).where(
                nombre_norm == (data.nombre or "").strip().lower(),
                provincia_norm == (data.provincia or "").strip(),
            )
        )
    ).scalar_one_or_none()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una localidad con ese nombre y provincia",
        )

    localidad = Localidad(**data.model_dump())
    db.add(localidad)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una localidad con ese nombre y provincia",
        )
    await db.refresh(localidad)
    return LocalidadResponse.model_validate(localidad)


@router.put("/{id}")
async def update_localidad(
    id: int,
    data: LocalidadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Localidad).where(Localidad.id == id))
    localidad = result.scalar_one_or_none()
    if not localidad:
        raise HTTPException(status_code=404, detail="Localidad no encontrada")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(localidad, key, value)

    await db.commit()
    await db.refresh(localidad)
    return LocalidadResponse.model_validate(localidad)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_localidad(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Localidad).where(Localidad.id == id))
    localidad = result.scalar_one_or_none()
    if not localidad:
        raise HTTPException(status_code=404, detail="Localidad no encontrada")

    try:
        await db.delete(localidad)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="No se puede eliminar, tiene registros asociados")

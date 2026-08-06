from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List

from app.core.database import get_db
from app.models.laboratorios import Laboratorio
from app.models.user import User
from app.schemas.laboratorio import LaboratorioCreate, LaboratorioUpdate, LaboratorioResponse
from app.utils.deps import get_current_user, require_role

router = APIRouter()

@router.get("", response_model=dict)
async def list_laboratorios(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = select(Laboratorio)
    if search:
        query = query.where(Laboratorio.nombre.ilike(f"%{search}%"))

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Get page
    query = query.order_by(Laboratorio.nombre).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    laboratorios = result.scalars().all()

    return {
        "items": [LaboratorioResponse.model_validate(lab) for lab in laboratorios],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@router.post("", response_model=LaboratorioResponse, status_code=status.HTTP_201_CREATED)
async def create_laboratorio(
    data: LaboratorioCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    # Check if exists
    existing = await db.execute(select(Laboratorio).where(Laboratorio.nombre == data.nombre))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Ya existe un laboratorio con ese nombre")

    laboratorio = Laboratorio(**data.model_dump())
    db.add(laboratorio)
    await db.commit()
    await db.refresh(laboratorio)
    return LaboratorioResponse.model_validate(laboratorio)

@router.get("/{id}", response_model=LaboratorioResponse)
async def get_laboratorio(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Laboratorio).where(Laboratorio.id == id))
    laboratorio = result.scalar_one_or_none()
    if not laboratorio:
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado")
    return LaboratorioResponse.model_validate(laboratorio)

@router.put("/{id}", response_model=LaboratorioResponse)
async def update_laboratorio(
    id: int,
    data: LaboratorioUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Laboratorio).where(Laboratorio.id == id))
    laboratorio = result.scalar_one_or_none()
    if not laboratorio:
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(laboratorio, key, value)

    await db.commit()
    await db.refresh(laboratorio)
    return LaboratorioResponse.model_validate(laboratorio)

@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_laboratorio(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Laboratorio).where(Laboratorio.id == id))
    laboratorio = result.scalar_one_or_none()
    if not laboratorio:
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado")

    await db.delete(laboratorio)
    await db.commit()
    return {"message": "Laboratorio eliminado correctamente"}

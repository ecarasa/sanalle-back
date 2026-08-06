from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.user import User
from app.models.banco import Banco
from app.schemas.banco import BancoCreate, BancoUpdate, BancoResponse
from app.utils.deps import get_current_user, require_role

router = APIRouter()


@router.get("")
async def list_bancos(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base_query = select(Banco).where(Banco.activo == True)  # noqa: E712
    if search:
        base_query = base_query.where(Banco.nombre.ilike(f"%{search}%"))

    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = base_query.order_by(Banco.nombre).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    bancos = result.scalars().all()

    items = [BancoResponse.model_validate(b) for b in bancos]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{id}")
async def get_banco(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Banco).where(Banco.id == id))
    banco = result.scalar_one_or_none()
    if not banco:
        raise HTTPException(status_code=404, detail="Banco no encontrado")
    return BancoResponse.model_validate(banco)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_banco(
    data: BancoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    existing = await db.execute(select(Banco).where(Banco.nombre == data.nombre))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Ya existe un banco con ese nombre")

    banco = Banco(**data.model_dump())
    db.add(banco)
    await db.commit()
    await db.refresh(banco)
    return BancoResponse.model_validate(banco)


@router.put("/{id}")
async def update_banco(
    id: int,
    data: BancoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Banco).where(Banco.id == id))
    banco = result.scalar_one_or_none()
    if not banco:
        raise HTTPException(status_code=404, detail="Banco no encontrado")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(banco, key, value)

    await db.commit()
    await db.refresh(banco)
    return BancoResponse.model_validate(banco)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_banco(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Banco).where(Banco.id == id))
    banco = result.scalar_one_or_none()
    if not banco:
        raise HTTPException(status_code=404, detail="Banco no encontrado")

    try:
        await db.delete(banco)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="No se puede eliminar, tiene registros asociados")

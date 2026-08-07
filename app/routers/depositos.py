from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.deposito import Deposito
from app.models.stock_producto_deposito import StockProductoDeposito
from app.models.user import User
from app.utils.deps import get_current_user, require_role

router = APIRouter()


class DepositoCreate(BaseModel):
    nombre: str
    orden: int | None = None


class DepositoUpdate(BaseModel):
    nombre: str | None = None
    activo: bool | None = None
    orden: int | None = None


def _to_dict(d: Deposito) -> dict:
    return {"id": d.id, "nombre": d.nombre, "activo": d.activo, "orden": d.orden}


@router.get("")
async def list_depositos(
    incluir_inactivos: bool = False,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    q = select(Deposito)
    if not incluir_inactivos:
        q = q.where(Deposito.activo == True)  # noqa: E712
    q = q.order_by(Deposito.orden, Deposito.id)
    rows = (await db.execute(q)).scalars().all()
    return [_to_dict(d) for d in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_deposito(
    body: DepositoCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    nombre = body.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    existing = (await db.execute(select(Deposito).where(func.lower(Deposito.nombre) == nombre.lower()))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe un depósito con ese nombre")

    if body.orden is None:
        max_orden = (await db.execute(select(func.coalesce(func.max(Deposito.orden), 0)))).scalar_one()
        orden = int(max_orden) + 1
    else:
        orden = body.orden

    dep = Deposito(nombre=nombre, orden=orden, activo=True)
    db.add(dep)
    await db.commit()
    await db.refresh(dep)
    return _to_dict(dep)


@router.put("/{id}")
async def update_deposito(
    id: int,
    body: DepositoUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    dep = (await db.execute(select(Deposito).where(Deposito.id == id))).scalar_one_or_none()
    if dep is None:
        raise HTTPException(status_code=404, detail="Depósito no encontrado")

    if body.nombre is not None:
        nombre = body.nombre.strip()
        if not nombre:
            raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
        dup = (await db.execute(
            select(Deposito).where(func.lower(Deposito.nombre) == nombre.lower(), Deposito.id != id)
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=400, detail="Ya existe un depósito con ese nombre")
        dep.nombre = nombre
    if body.activo is not None:
        dep.activo = body.activo
    if body.orden is not None:
        dep.orden = body.orden

    await db.commit()
    await db.refresh(dep)
    return _to_dict(dep)


@router.delete("/{id}")
async def delete_deposito(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    dep = (await db.execute(select(Deposito).where(Deposito.id == id))).scalar_one_or_none()
    if dep is None:
        raise HTTPException(status_code=404, detail="Depósito no encontrado")

    # Si tiene stock con existencias, no se elimina: se desactiva.
    con_stock = (await db.execute(
        select(func.coalesce(func.sum(StockProductoDeposito.cajas + StockProductoDeposito.blisters), 0))
        .where(StockProductoDeposito.deposito_id == id)
    )).scalar_one()
    if con_stock and con_stock > 0:
        dep.activo = False
        await db.commit()
        return {"message": f"Depósito '{dep.nombre}' tiene existencias: se desactivó (no se eliminó)."}

    await db.delete(dep)
    await db.commit()
    return {"message": f"Depósito '{dep.nombre}' eliminado."}

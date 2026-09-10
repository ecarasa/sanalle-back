import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List

from app.core.database import get_db
from app.models.laboratorios import Laboratorio
from app.models.user import User
from app.schemas.laboratorio import (
    LaboratorioCreate,
    LaboratorioOrdenRequest,
    LaboratorioOrdenResponse,
    LaboratorioResponse,
    LaboratorioUpdate,
)
from app.utils.deps import get_current_user, require_role

router = APIRouter()


def _clave(nombre: str) -> str:
    """Normaliza un nombre para matchearlo contra lo que pegó el usuario.

    El orden llega copiado de un PDF: viene con acentos inconsistentes, espacios
    dobles y mayúsculas al azar. Sin normalizar, "Bagó" y "BAGO" serían dos
    laboratorios distintos y media lista quedaría sin aplicar.
    """
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", nombre) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()

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

    # Get page — por `orden` primero: la lista de precios respeta el orden que fija
    # la droguería, y el nombre sólo desempata entre los que comparten posición.
    query = (
        query.order_by(Laboratorio.orden, Laboratorio.nombre)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
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

    campos = data.model_dump()
    # Sin orden explícito, va al final. Mismo criterio que en depósitos.
    if campos.get("orden") is None:
        max_orden = (await db.execute(select(func.coalesce(func.max(Laboratorio.orden), 0)))).scalar_one()
        campos["orden"] = int(max_orden) + 1

    laboratorio = Laboratorio(**campos)
    db.add(laboratorio)
    await db.commit()
    await db.refresh(laboratorio)
    return LaboratorioResponse.model_validate(laboratorio)


# OJO: va declarado ANTES de `PUT /{id}` o FastAPI matchea "orden" como si fuera
# un id y devuelve 422. Misma trampa que documenta el router de stock.
@router.put("/orden", response_model=LaboratorioOrdenResponse)
async def reordenar_laboratorios(
    body: LaboratorioOrdenRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Fija el orden de la lista de precios de una sola vez.

    Se puede mandar `ids` (los botones ↑/↓ de la pantalla) o `nombres` (pegar el
    orden desde el PDF del cliente). Los que no figuran quedan detrás, en orden
    alfabético, para que agregar un laboratorio nuevo no obligue a rehacer la lista.
    """
    if not body.ids and not body.nombres:
        raise HTTPException(status_code=400, detail="Mandá `ids` o `nombres` con el orden deseado.")
    if body.ids and body.nombres:
        raise HTTPException(status_code=400, detail="Mandá `ids` o `nombres`, no los dos.")

    todos = (await db.execute(select(Laboratorio))).scalars().all()

    secuencia: list[Laboratorio] = []
    no_encontrados: list[str] = []
    vistos: set[int] = set()

    if body.ids:
        por_id = {lab.id: lab for lab in todos}
        for lab_id in body.ids:
            lab = por_id.get(lab_id)
            if lab is None:
                no_encontrados.append(str(lab_id))
            elif lab.id not in vistos:
                vistos.add(lab.id)
                secuencia.append(lab)
    else:
        por_clave: dict[str, Laboratorio] = {}
        for lab in todos:
            por_clave.setdefault(_clave(lab.nombre), lab)
        for nombre in body.nombres or []:
            if not nombre.strip():
                continue
            lab = por_clave.get(_clave(nombre))
            if lab is None:
                no_encontrados.append(nombre.strip())
            elif lab.id not in vistos:
                vistos.add(lab.id)
                secuencia.append(lab)

    for posicion, lab in enumerate(secuencia, start=1):
        lab.orden = posicion

    # El resto va detrás, alfabético. Se recalcula siempre (y no sólo para los que
    # tenían orden 0) para que no queden huecos ni posiciones repetidas.
    resto = sorted((lab for lab in todos if lab.id not in vistos), key=lambda l: l.nombre.lower())
    for offset, lab in enumerate(resto, start=1):
        lab.orden = len(secuencia) + offset

    await db.commit()
    return LaboratorioOrdenResponse(aplicados=len(secuencia), no_encontrados=no_encontrados)

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

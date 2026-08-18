"""ABM genérico de entidades paramétricas (combos de la app).

Una sola tabla `entidades` agrupada por `categoria`. Sirve todos los combos
"sueltos" (condición de pago, transporte, sociedad, tipo de precio, y los nuevos
que se quieran agregar). Los combos con tabla propia (zona, localidad, etc.)
siguen en sus routers.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entidad import Entidad
from app.models.user import User
from app.utils.deps import get_current_user, require_role

router = APIRouter()

# Categorías "conocidas" con etiqueta amigable. Se pueden crear otras libremente:
# el ABM permite categorías nuevas y la lista de abajo solo aporta el label lindo.
CATEGORIAS_CONOCIDAS: list[dict] = [
    {"categoria": "condicion_pago", "label": "Condición de pago"},
    {"categoria": "transporte", "label": "Transporte"},
    {"categoria": "sociedad", "label": "Sociedad"},
    {"categoria": "tipo_precio", "label": "Tipo de precio"},
]
_LABELS = {c["categoria"]: c["label"] for c in CATEGORIAS_CONOCIDAS}


class EntidadBase(BaseModel):
    categoria: str = Field(..., min_length=1, max_length=40)
    nombre: str = Field(..., min_length=1, max_length=120)
    codigo: Optional[str] = None
    orden: int = 0
    activo: bool = True
    extra: Optional[dict] = None


class EntidadCreate(EntidadBase):
    pass


class EntidadUpdate(BaseModel):
    nombre: Optional[str] = None
    codigo: Optional[str] = None
    orden: Optional[int] = None
    activo: Optional[bool] = None
    extra: Optional[dict] = None


class EntidadResponse(EntidadBase):
    id: int
    model_config = {"from_attributes": True}


def _label(categoria: str) -> str:
    return _LABELS.get(categoria) or categoria.replace("_", " ").capitalize()


@router.get("/categorias")
async def listar_categorias(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Categorías conocidas + cualquier otra presente en la tabla, con conteo."""
    rows = (await db.execute(
        select(Entidad.categoria, func.count()).group_by(Entidad.categoria)
    )).all()
    counts = {c: n for c, n in rows}
    categorias = {c["categoria"] for c in CATEGORIAS_CONOCIDAS} | set(counts.keys())
    salida = [
        {"categoria": c, "label": _label(c), "total": counts.get(c, 0)}
        for c in sorted(categorias, key=_label)
    ]
    return salida


@router.get("", response_model=dict)
async def listar_entidades(
    categoria: str = Query(..., description="Categoría del combo"),
    search: str = Query("", max_length=100),
    solo_activos: bool = Query(False, description="Solo valores activos (para alimentar combos)"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = select(Entidad).where(Entidad.categoria == categoria)
    if solo_activos:
        query = query.where(Entidad.activo == True)  # noqa: E712
    if search:
        query = query.where(Entidad.nombre.ilike(f"%{search}%"))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    query = query.order_by(Entidad.orden, Entidad.nombre)
    items = (await db.execute(query)).scalars().all()
    return {
        "items": [EntidadResponse.model_validate(e) for e in items],
        "total": total,
        "page": 1,
        "page_size": total,
    }


@router.post("", response_model=EntidadResponse, status_code=status.HTTP_201_CREATED)
async def crear_entidad(
    data: EntidadCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    dup = (await db.execute(
        select(Entidad).where(Entidad.categoria == data.categoria, Entidad.nombre == data.nombre)
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=400, detail=f"Ya existe '{data.nombre}' en {_label(data.categoria)}")
    entidad = Entidad(**data.model_dump())
    db.add(entidad)
    await db.commit()
    await db.refresh(entidad)
    return EntidadResponse.model_validate(entidad)


@router.put("/{id}", response_model=EntidadResponse)
async def actualizar_entidad(
    id: int,
    data: EntidadUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    entidad = (await db.execute(select(Entidad).where(Entidad.id == id))).scalar_one_or_none()
    if not entidad:
        raise HTTPException(status_code=404, detail="Entidad no encontrada")
    cambios = data.model_dump(exclude_unset=True)
    nuevo_nombre = cambios.get("nombre")
    if nuevo_nombre and nuevo_nombre != entidad.nombre:
        dup = (await db.execute(
            select(Entidad).where(
                Entidad.categoria == entidad.categoria, Entidad.nombre == nuevo_nombre, Entidad.id != id
            )
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=400, detail=f"Ya existe '{nuevo_nombre}' en {_label(entidad.categoria)}")
    for k, v in cambios.items():
        setattr(entidad, k, v)
    await db.commit()
    await db.refresh(entidad)
    return EntidadResponse.model_validate(entidad)


@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def eliminar_entidad(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    entidad = (await db.execute(select(Entidad).where(Entidad.id == id))).scalar_one_or_none()
    if not entidad:
        raise HTTPException(status_code=404, detail="Entidad no encontrada")
    await db.delete(entidad)
    await db.commit()
    return {"message": "Valor eliminado"}

from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.configuracion import Configuracion
from app.models.user import User
from app.utils.deps import get_current_user, require_role

router = APIRouter()

# Configuración general con sus valores por defecto (como texto).
# Agregar una clave nueva acá la hace disponible en la pantalla de Configuración.
CONFIG_DEFAULTS: dict[str, str] = {
    # Días para considerar un producto "nuevo" (badge y filtro).
    "producto_nuevo_dias": "30",
}


async def _leer_config(db: AsyncSession) -> dict[str, str]:
    rows = (await db.execute(select(Configuracion))).scalars().all()
    valores = dict(CONFIG_DEFAULTS)
    for r in rows:
        valores[r.clave] = r.valor
    return valores


@router.get("")
async def get_configuracion(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Devuelve la configuración general (defaults + overrides guardados)."""
    return await _leer_config(db)


@router.put("")
async def update_configuracion(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Actualiza claves de configuración (solo las conocidas). Upsert por clave."""
    for clave, valor in body.items():
        if clave not in CONFIG_DEFAULTS:
            continue
        existente = (
            await db.execute(select(Configuracion).where(Configuracion.clave == clave))
        ).scalar_one_or_none()
        if existente:
            existente.valor = str(valor)
        else:
            db.add(Configuracion(clave=clave, valor=str(valor)))
    await db.commit()
    return await _leer_config(db)

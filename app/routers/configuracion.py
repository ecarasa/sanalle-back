from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, HTTPException, status
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
    # Importe a partir del cual un pedido minorista pasa a precio mayorista.
    # "0" desactiva el escalón. Comercio nunca escala: es una lista propia, no un
    # tramo por volumen.
    "umbral_mayorista": "800000",
}


def _entero_no_negativo(valor: str) -> str:
    n = int(valor)  # ValueError si no es un entero
    if n < 0:
        raise ValueError("no puede ser negativo")
    return str(n)


def _entero_positivo(valor: str) -> str:
    n = int(valor)
    if n <= 0:
        raise ValueError("tiene que ser mayor que cero")
    return str(n)


# Validadores por clave. Sin esto el PUT acepta cualquier texto, y un valor no
# numérico desactiva en silencio una regla comercial: nadie se entera hasta que
# un pedido de $2.000.000 se factura a precio minorista.
CONFIG_VALIDADORES: dict[str, Callable[[str], str]] = {
    "producto_nuevo_dias": _entero_positivo,
    "umbral_mayorista": _entero_no_negativo,
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
    """Actualiza claves de configuración (solo las conocidas). Upsert por clave.

    Valida antes de escribir nada: si una clave del lote es inválida se rechaza el
    lote entero, para no dejar la configuración a medio aplicar.
    """
    a_guardar: dict[str, str] = {}
    for clave, valor in body.items():
        if clave not in CONFIG_DEFAULTS:
            continue
        texto = str(valor).strip()
        validador = CONFIG_VALIDADORES.get(clave)
        if validador is None:
            a_guardar[clave] = texto
            continue
        try:
            a_guardar[clave] = validador(texto)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{clave}': valor inválido {valor!r} ({exc}).",
            )

    for clave, texto in a_guardar.items():
        existente = (
            await db.execute(select(Configuracion).where(Configuracion.clave == clave))
        ).scalar_one_or_none()
        if existente:
            existente.valor = texto
        else:
            db.add(Configuracion(clave=clave, valor=texto))
    await db.commit()
    return await _leer_config(db)

"""Listas de precios públicas por token revocable.

Cada grupo (minorista / mayorista / comercio) tiene un token opaco guardado en la
tabla `configuracion` (clave `lista_publica_token_<grupo>`). El link público
`/lista/<token>` resuelve el token a su grupo y sirve el catálogo con SÓLO los
precios de ese grupo. Regenerar el token invalida el link anterior (revocación).
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.configuracion import Configuracion
from app.models.user import User
from app.routers.productos import build_public_catalogo
from app.utils.deps import require_role

router = APIRouter()

# Grupos válidos (mismos strings que pricing_service.GRUPOS).
GRUPOS: tuple[str, ...] = ("minorista", "mayorista", "comercio")
GRUPO_LABEL = {"minorista": "Minorista", "mayorista": "Mayorista", "comercio": "Comercio"}


def _clave(grupo: str) -> str:
    return f"lista_publica_token_{grupo}"


def _nuevo_token() -> str:
    return secrets.token_urlsafe(16)


async def _get_token_row(db: AsyncSession, grupo: str) -> Configuracion | None:
    return (await db.execute(
        select(Configuracion).where(Configuracion.clave == _clave(grupo))
    )).scalar_one_or_none()


async def _asegurar_token(db: AsyncSession, grupo: str) -> str:
    """Devuelve el token del grupo, creándolo si no existe."""
    row = await _get_token_row(db, grupo)
    if row and row.valor:
        return row.valor
    token = _nuevo_token()
    if row:
        row.valor = token
    else:
        db.add(Configuracion(clave=_clave(grupo), valor=token))
    await db.commit()
    return token


async def _grupo_de_token(db: AsyncSession, token: str) -> str | None:
    """Resuelve un token a su grupo, o None si no corresponde a ninguno."""
    if not token:
        return None
    rows = (await db.execute(
        select(Configuracion).where(
            Configuracion.clave.in_([_clave(g) for g in GRUPOS])
        )
    )).scalars().all()
    for r in rows:
        if r.valor == token:
            # clave = "lista_publica_token_<grupo>"
            return r.clave.rsplit("_", 1)[-1]
    return None


# ---------------------------------------------------------------------------
# Público (sin auth): catálogo por token
# ---------------------------------------------------------------------------
@router.get("/lista/{token}")
async def lista_publica(
    token: str,
    search: str = Query("", description="Buscar por nombre o código"),
    laboratorio_id: int | None = Query(None),
    all: bool = Query(True, description="Devolver todos los productos sin paginar"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Catálogo público de precios de un grupo, accedido por token revocable."""
    grupo = await _grupo_de_token(db, token)
    if grupo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lista no disponible. El link puede haber sido revocado.",
        )
    catalogo = await build_public_catalogo(
        db, search=search, lista=grupo, laboratorio_id=laboratorio_id,
        page=page, page_size=page_size, all=all,
    )
    return {"grupo": grupo, "grupo_label": GRUPO_LABEL[grupo], **catalogo}


# ---------------------------------------------------------------------------
# Admin (auth): ver y regenerar los links
# ---------------------------------------------------------------------------
class LinkPublico(BaseModel):
    grupo: str
    label: str
    token: str


class LinksPublicosResponse(BaseModel):
    links: list[LinkPublico]


@router.get("/admin/links", response_model=LinksPublicosResponse)
async def listar_links(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Devuelve los 3 tokens (creándolos si faltan). El front arma la URL completa."""
    links = []
    for g in GRUPOS:
        token = await _asegurar_token(db, g)
        links.append(LinkPublico(grupo=g, label=GRUPO_LABEL[g], token=token))
    return LinksPublicosResponse(links=links)


@router.post("/admin/links/{grupo}/regenerar", response_model=LinkPublico)
async def regenerar_link(
    grupo: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Genera un token nuevo para el grupo; el link anterior deja de funcionar."""
    if grupo not in GRUPOS:
        raise HTTPException(status_code=400, detail=f"Grupo inválido: {grupo}")
    token = _nuevo_token()
    row = await _get_token_row(db, grupo)
    if row:
        row.valor = token
    else:
        db.add(Configuracion(clave=_clave(grupo), valor=token))
    await db.commit()
    return LinkPublico(grupo=grupo, label=GRUPO_LABEL[grupo], token=token)

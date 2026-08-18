from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.chat import ChatConversacion, ChatParticipante, ChatMensaje
from app.models.user import User
from app.utils.deps import get_current_user

router = APIRouter()


# ---------- Schemas ----------

class CrearConversacion(BaseModel):
    tipo: str = "individual"            # 'individual' | 'grupo'
    user_id: int | None = None         # para individual: el otro usuario
    nombre: str | None = None          # para grupo
    participante_ids: list[int] = []   # para grupo


class EnviarMensaje(BaseModel):
    contenido: str


class UsuarioMini(BaseModel):
    id: int
    nombre: str


# ---------- Helpers ----------

def _nombre_usuario(u: User | None) -> str:
    if not u:
        return "Usuario"
    return u.nombre_completo or u.username


async def _es_participante(db: AsyncSession, conversacion_id: int, user_id: int) -> ChatParticipante | None:
    res = await db.execute(
        select(ChatParticipante).where(
            and_(
                ChatParticipante.conversacion_id == conversacion_id,
                ChatParticipante.user_id == user_id,
            )
        )
    )
    return res.scalar_one_or_none()


# ---------- Endpoints ----------

@router.get("/usuarios")
async def listar_usuarios(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Usuarios activos con los que se puede chatear (excluye al propio)."""
    res = await db.execute(
        select(User).where(and_(User.activo == True, User.id != current_user.id)).order_by(User.nombre_completo)  # noqa: E712
    )
    users = res.scalars().all()
    return [{"id": u.id, "nombre": _nombre_usuario(u), "rol": u.rol.value} for u in users]


@router.get("/conversaciones")
async def listar_conversaciones(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Conversaciones del usuario, con último mensaje y cantidad de no leídos."""
    # IDs de conversaciones donde participa
    part_res = await db.execute(
        select(ChatParticipante).where(ChatParticipante.user_id == current_user.id)
    )
    mis_participaciones = part_res.scalars().all()
    conv_ids = [p.conversacion_id for p in mis_participaciones]
    last_read_by_conv = {p.conversacion_id: p.last_read_at for p in mis_participaciones}
    if not conv_ids:
        return []

    conv_res = await db.execute(
        select(ChatConversacion)
        .options(
            selectinload(ChatConversacion.participantes).selectinload(ChatParticipante.usuario),
        )
        .where(ChatConversacion.id.in_(conv_ids))
    )
    conversaciones = conv_res.scalars().all()

    salida = []
    for c in conversaciones:
        # Último mensaje
        ult_res = await db.execute(
            select(ChatMensaje)
            .where(ChatMensaje.conversacion_id == c.id)
            .order_by(ChatMensaje.created_at.desc())
            .limit(1)
        )
        ultimo = ult_res.scalar_one_or_none()

        # No leídos: mensajes de otros posteriores a last_read_at
        last_read = last_read_by_conv.get(c.id)
        no_leidos_q = select(func.count()).where(
            and_(
                ChatMensaje.conversacion_id == c.id,
                ChatMensaje.autor_id != current_user.id,
            )
        )
        if last_read is not None:
            no_leidos_q = no_leidos_q.where(ChatMensaje.created_at > last_read)
        no_leidos = (await db.execute(no_leidos_q)).scalar_one()

        # Nombre a mostrar: grupo -> nombre; individual -> el otro participante
        if c.tipo == "grupo":
            titulo = c.nombre or "Grupo"
        else:
            otro = next((p.usuario for p in c.participantes if p.user_id != current_user.id), None)
            titulo = _nombre_usuario(otro)

        salida.append({
            "id": c.id,
            "tipo": c.tipo,
            "titulo": titulo,
            "participantes": [
                {"id": p.user_id, "nombre": _nombre_usuario(p.usuario)} for p in c.participantes
            ],
            "ultimo_mensaje": ultimo.contenido if ultimo else None,
            "ultimo_mensaje_fecha": ultimo.created_at.isoformat() if ultimo else None,
            "no_leidos": no_leidos,
        })

    # Ordenar por actividad (último mensaje más reciente primero)
    salida.sort(key=lambda s: s["ultimo_mensaje_fecha"] or "", reverse=True)
    return salida


@router.post("/conversaciones", status_code=status.HTTP_201_CREATED)
async def crear_conversacion(
    body: CrearConversacion,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.tipo == "individual":
        if not body.user_id or body.user_id == current_user.id:
            raise HTTPException(status_code=400, detail="Elegí un usuario válido para el chat individual")

        # Reusar la conversación individual existente si ya la hay
        existentes = await db.execute(
            select(ChatConversacion)
            .options(selectinload(ChatConversacion.participantes))
            .where(ChatConversacion.tipo == "individual")
        )
        for c in existentes.scalars().all():
            ids = {p.user_id for p in c.participantes}
            if ids == {current_user.id, body.user_id}:
                return {"id": c.id, "reused": True}

        conv = ChatConversacion(tipo="individual", creador_id=current_user.id)
        db.add(conv)
        await db.flush()
        db.add(ChatParticipante(conversacion_id=conv.id, user_id=current_user.id))
        db.add(ChatParticipante(conversacion_id=conv.id, user_id=body.user_id))
        await db.commit()
        return {"id": conv.id, "reused": False}

    # Grupo
    if not body.nombre or not body.nombre.strip():
        raise HTTPException(status_code=400, detail="El grupo necesita un nombre")
    ids = set(body.participante_ids) | {current_user.id}
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="Agregá al menos un participante")

    conv = ChatConversacion(tipo="grupo", nombre=body.nombre.strip(), creador_id=current_user.id)
    db.add(conv)
    await db.flush()
    for uid in ids:
        db.add(ChatParticipante(conversacion_id=conv.id, user_id=uid))
    await db.commit()
    return {"id": conv.id, "reused": False}


@router.get("/conversaciones/{conversacion_id}/mensajes")
async def listar_mensajes(
    conversacion_id: int,
    after_id: int = Query(0, description="Traer solo mensajes con id mayor a este (polling incremental)"),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    part = await _es_participante(db, conversacion_id, current_user.id)
    if not part:
        raise HTTPException(status_code=403, detail="No participás de esta conversación")

    q = (
        select(ChatMensaje)
        .options(selectinload(ChatMensaje.autor))
        .where(ChatMensaje.conversacion_id == conversacion_id)
    )
    if after_id:
        q = q.where(ChatMensaje.id > after_id)
    q = q.order_by(ChatMensaje.created_at.asc()).limit(limit)
    res = await db.execute(q)
    mensajes = res.scalars().all()

    return [
        {
            "id": m.id,
            "autor_id": m.autor_id,
            "autor_nombre": _nombre_usuario(m.autor),
            "contenido": m.contenido,
            "created_at": m.created_at.isoformat(),
            "propio": m.autor_id == current_user.id,
        }
        for m in mensajes
    ]


@router.post("/conversaciones/{conversacion_id}/mensajes", status_code=status.HTTP_201_CREATED)
async def enviar_mensaje(
    conversacion_id: int,
    body: EnviarMensaje,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    part = await _es_participante(db, conversacion_id, current_user.id)
    if not part:
        raise HTTPException(status_code=403, detail="No participás de esta conversación")
    contenido = (body.contenido or "").strip()
    if not contenido:
        raise HTTPException(status_code=400, detail="El mensaje está vacío")

    mensaje = ChatMensaje(conversacion_id=conversacion_id, autor_id=current_user.id, contenido=contenido)
    db.add(mensaje)
    # El autor marca como leído al enviar
    part.last_read_at = datetime.now()
    await db.commit()
    await db.refresh(mensaje)
    return {
        "id": mensaje.id,
        "autor_id": current_user.id,
        "autor_nombre": _nombre_usuario(current_user),
        "contenido": mensaje.contenido,
        "created_at": mensaje.created_at.isoformat(),
        "propio": True,
    }


@router.post("/conversaciones/{conversacion_id}/leer")
async def marcar_leido(
    conversacion_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    part = await _es_participante(db, conversacion_id, current_user.id)
    if not part:
        raise HTTPException(status_code=403, detail="No participás de esta conversación")
    part.last_read_at = datetime.now()
    await db.commit()
    return {"ok": True}


@router.get("/no-leidos")
async def total_no_leidos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Total de mensajes no leídos del usuario (para el badge del menú)."""
    part_res = await db.execute(
        select(ChatParticipante).where(ChatParticipante.user_id == current_user.id)
    )
    total = 0
    for p in part_res.scalars().all():
        q = select(func.count()).where(
            and_(
                ChatMensaje.conversacion_id == p.conversacion_id,
                ChatMensaje.autor_id != current_user.id,
            )
        )
        if p.last_read_at is not None:
            q = q.where(ChatMensaje.created_at > p.last_read_at)
        total += (await db.execute(q)).scalar_one()
    return {"total": total}

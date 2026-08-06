from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.cliente import Cliente
from app.models.solicitud_cambio_cliente import SolicitudCambioCliente, EstadoSolicitud
from app.schemas.solicitud_cambio_cliente import SolicitudCambioClienteCreate, SolicitudCambioClienteResponse
from app.utils.deps import get_current_user, require_role

router = APIRouter()


def _build_response(s: SolicitudCambioCliente) -> SolicitudCambioClienteResponse:
    return SolicitudCambioClienteResponse(
        id=s.id,
        cliente_id=s.cliente_id,
        cliente_nombre=s.cliente.nombre if s.cliente else None,
        solicitante_id=s.solicitante_id,
        solicitante_nombre=s.solicitante.nombre_completo if s.solicitante else None,
        campo=s.campo,
        valor_anterior=s.valor_anterior,
        valor_nuevo=s.valor_nuevo,
        motivo=s.motivo,
        estado=s.estado.value,
        revisado_por_id=s.revisado_por_id,
        revisado_por_nombre=s.revisado_por.nombre_completo if s.revisado_por else None,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get("")
async def list_solicitudes(
    estado: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy.orm import selectinload

    base_query = select(SolicitudCambioCliente)
    if estado:
        base_query = base_query.where(SolicitudCambioCliente.estado == EstadoSolicitud(estado))

    if current_user.rol.value == "ventas":
        base_query = base_query.where(SolicitudCambioCliente.solicitante_id == current_user.id)

    count_q = select(func.count()).select_from(base_query.with_only_columns(SolicitudCambioCliente.id).subquery())
    total = (await db.execute(count_q)).scalar_one()

    data_query = (
        base_query.options(
            selectinload(SolicitudCambioCliente.cliente),
            selectinload(SolicitudCambioCliente.solicitante),
            selectinload(SolicitudCambioCliente.revisado_por),
        )
        .order_by(SolicitudCambioCliente.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(data_query)
    solicitudes = result.scalars().unique().all()

    return {
        "items": [_build_response(s) for s in solicitudes],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_solicitud(
    body: SolicitudCambioClienteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy.orm import selectinload

    # Validate cliente
    cliente_result = await db.execute(select(Cliente).where(Cliente.id == body.cliente_id))
    if not cliente_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    solicitud = SolicitudCambioCliente(
        cliente_id=body.cliente_id,
        solicitante_id=current_user.id,
        campo=body.campo,
        valor_anterior=body.valor_anterior,
        valor_nuevo=body.valor_nuevo,
        motivo=body.motivo,
    )
    db.add(solicitud)
    await db.commit()

    reload_query = (
        select(SolicitudCambioCliente)
        .where(SolicitudCambioCliente.id == solicitud.id)
        .options(
            selectinload(SolicitudCambioCliente.cliente),
            selectinload(SolicitudCambioCliente.solicitante),
        )
    )
    result = await db.execute(reload_query)
    solicitud = result.scalar_one()
    return _build_response(solicitud)


@router.patch("/{id}/aprobar")
async def aprobar_solicitud(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(SolicitudCambioCliente)
        .where(SolicitudCambioCliente.id == id)
        .options(
            selectinload(SolicitudCambioCliente.cliente),
            selectinload(SolicitudCambioCliente.solicitante),
            selectinload(SolicitudCambioCliente.revisado_por),
        )
    )
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    solicitud.estado = EstadoSolicitud.aprobada
    solicitud.revisado_por_id = current_user.id

    # Apply the change to the client if campo is specified
    if solicitud.campo and solicitud.valor_nuevo:
        cliente_result = await db.execute(select(Cliente).where(Cliente.id == solicitud.cliente_id))
        cliente = cliente_result.scalar_one_or_none()
        if cliente and hasattr(cliente, solicitud.campo):
            setattr(cliente, solicitud.campo, solicitud.valor_nuevo)

    await db.commit()
    await db.refresh(solicitud)
    return _build_response(solicitud)


@router.patch("/{id}/rechazar")
async def rechazar_solicitud(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(SolicitudCambioCliente)
        .where(SolicitudCambioCliente.id == id)
        .options(
            selectinload(SolicitudCambioCliente.cliente),
            selectinload(SolicitudCambioCliente.solicitante),
            selectinload(SolicitudCambioCliente.revisado_por),
        )
    )
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    solicitud.estado = EstadoSolicitud.rechazada
    solicitud.revisado_por_id = current_user.id
    await db.commit()
    await db.refresh(solicitud)
    return _build_response(solicitud)

from typing import Any
import io

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update as sa_update
from pydantic import BaseModel
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.cliente import Cliente
from app.models.cliente_direccion import ClienteDireccion
from app.models.pedido import ESTADOS_NO_COMPUTABLES, Pedido, EstadoDespacho
from app.models.pago import Pago, EstadoPago
from app.models.nota_credito_debito import NotaCreditoDebito
from app.models.solicitud_cambio_cliente import SolicitudCambioCliente
from app.models.user import User, RolUsuario
from app.models.localidad import Localidad
from app.models.zona import Zona
from app.schemas.cliente import (
    ClienteConDeuda,
    ClienteCreate,
    ClienteDireccionCreate,
    ClienteDireccionResponse,
    ClienteDireccionUpdate,
    ClienteResponse,
    ClienteUpdate,
)
from app.utils.deps import get_current_user, require_role
from app.utils.filters import apply_column_filters
from app.services.semaforo_service import (
    calcular_semaforo,
    calcular_semaforo_actividad,
    ACTIVIDAD_VERDE_DIAS,
    ACTIVIDAD_AMARILLO_DIAS,
)
from app.services.geolocating import obtener_coordenadas_osm
from decimal import Decimal


router = APIRouter()


def _pedidos_subquery(cliente_id_col, tipo_doc=None):
    """Subquery: sum of importe_total for pedidos with active states."""
    filters = [
        Pedido.cliente_id == cliente_id_col,
        Pedido.shipping_status.notin_(ESTADOS_NO_COMPUTABLES),
    ]
    if tipo_doc:
        filters.append(Pedido.tipo_documento == tipo_doc)
    
    return (
        select(func.coalesce(func.sum(Pedido.importe_total), 0))
        .where(and_(*filters))
        .correlate(Cliente)
        .scalar_subquery()
    )


def _pagos_subquery(cliente_id_col, tipo_cuenta=None):
    """Subquery: sum of importe for pagos with active states."""
    filters = [
        Pago.cliente_id == cliente_id_col,
        Pago.estado.in_([
            EstadoPago.pendiente,
            EstadoPago.acreditado,
            EstadoPago.recibido,
            EstadoPago.imputado,
        ]),
    ]
    if tipo_cuenta:
        filters.append(Pago.tipo_cuenta == tipo_cuenta)

    return (
        select(func.coalesce(func.sum(Pago.importe), 0))
        .where(and_(*filters))
        .correlate(Cliente)
        .scalar_subquery()
    )


def _notas_subquery(cliente_id_col, tipo_cuenta=None, tipo_nota=None):
    """Subquery: sum of importe_total for notas with active states."""
    from app.models.nota_credito_debito import NotaCreditoDebito, TipoNota
    filters = [NotaCreditoDebito.cliente_id == cliente_id_col]
    if tipo_cuenta:
        filters.append(NotaCreditoDebito.tipo_cuenta == tipo_cuenta)
    if tipo_nota:
        filters.append(NotaCreditoDebito.tipo == tipo_nota)

    return (
        select(func.coalesce(func.sum(NotaCreditoDebito.importe_total), 0))
        .where(and_(*filters))
        .correlate(Cliente)
        .scalar_subquery()
    )


@router.get("")
async def list_clientes(
    search: str = Query("", description="Buscar por nombre, CUIT o razón social"),
    column_filters: str | None = Query(None, alias="filters", description="JSON column filters"),
    actividad: str | None = Query(None, pattern="^(verde|amarillo|rojo)$", description="Filtrar por semáforo de actividad (recencia de compra)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=1000),
    sin_paginar: bool = Query(False, alias="all", description="Devolver todos los clientes sin paginar (para filtrado en memoria en el front)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Deuda Remitos
    deuda_remito_expr = (
        _pedidos_subquery(Cliente.id, "remito") 
        - _pagos_subquery(Cliente.id, "remito")
        + _notas_subquery(Cliente.id, "remito", "debito")
        - _notas_subquery(Cliente.id, "remito", "credito")
        + Cliente.deuda_inicial_remito
    )
    
    # Deuda Facturas
    deuda_factura_expr = (
        _pedidos_subquery(Cliente.id, "factura")
        - _pagos_subquery(Cliente.id, "factura")
        + _notas_subquery(Cliente.id, "factura", "debito")
        - _notas_subquery(Cliente.id, "factura", "credito")
        + Cliente.deuda_inicial_factura
    )

    deuda_expr = deuda_remito_expr + deuda_factura_expr

    base_filter = Cliente.activo == True  # noqa: E712
    # ... rest of filters ...
    if current_user.rol.value == "ventas":
        base_filter = and_(base_filter, Cliente.vendedor_id == current_user.id)
    else:
        base_filter = and_(base_filter, Cliente.aprobado == True)  # noqa: E712

    if search:
        like_pattern = f"%{search}%"
        search_filter = and_(
            base_filter,
            (
                Cliente.nombre.ilike(like_pattern)
                | Cliente.cuit.ilike(like_pattern)
                | Cliente.razon_social.ilike(like_pattern)
            ),
        )
    else:
        search_filter = base_filter

    # Los outer joins a Localidad/Zona son necesarios para que apply_column_filters
    # pueda filtrar por localidad_nombre / zona_nombre (columnas de tablas unidas).
    # Sin el join, SQLAlchemy hacía un cross join sin condición -> producto cartesiano
    # y el filtro devolvía todos los clientes. Relaciones N->1: no duplican filas.
    base_query = (
        select(Cliente)
        .outerjoin(Localidad, Cliente.localidad_id == Localidad.id)
        .outerjoin(Zona, Cliente.zona_id == Zona.id)
        .where(search_filter)
    )

    base_query = apply_column_filters(
        base_query,
        Cliente,
        column_filters,
        allowed_columns={
            "nombre", "razon_social", "cuit", "localidad_nombre", "zona_nombre",
            "domicilio", "activo", "categoria", "tipo", "condicion_pago"
        },
        extra_mappings={
            "localidad_nombre": Localidad.nombre,
            "zona_nombre": Zona.nombre
        }
    )

    oldest_pedido_fecha_subquery = (
        select(func.min(Pedido.fecha))
        .where(
            and_(
                Pedido.cliente_id == Cliente.id,
                Pedido.saldo_pendiente > 0,
                Pedido.shipping_status.notin_(ESTADOS_NO_COMPUTABLES),
            )
        )
        .correlate(Cliente)
        .scalar_subquery()
    )

    # Última compra: fecha del pedido más reciente (no cancelado). Alimenta el
    # semáforo de ACTIVIDAD (recencia), distinto del de mora.
    ultima_compra_subquery = (
        select(func.max(Pedido.fecha))
        .where(
            and_(
                Pedido.cliente_id == Cliente.id,
                Pedido.shipping_status.notin_(ESTADOS_NO_COMPUTABLES),
            )
        )
        .correlate(Cliente)
        .scalar_subquery()
    )

    # Filtro por semáforo de actividad. Se aplica sobre base_query para que afecte
    # también al conteo total. Umbrales alineados con calcular_semaforo_actividad.
    if actividad:
        from datetime import timedelta
        from app.utils.tz import hoy_ar
        hoy = hoy_ar()
        verde_desde = hoy - timedelta(days=ACTIVIDAD_VERDE_DIAS)
        amarillo_desde = hoy - timedelta(days=ACTIVIDAD_AMARILLO_DIAS)
        if actividad == "verde":
            base_query = base_query.where(ultima_compra_subquery >= verde_desde)
        elif actividad == "amarillo":
            base_query = base_query.where(
                and_(
                    ultima_compra_subquery < verde_desde,
                    ultima_compra_subquery >= amarillo_desde,
                )
            )
        elif actividad == "rojo":
            base_query = base_query.where(
                or_(
                    ultima_compra_subquery.is_(None),
                    ultima_compra_subquery < amarillo_desde,
                )
            )

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    deuda_query = (
        select(
            Cliente, 
            deuda_expr.label("deuda"), 
            deuda_remito_expr.label("deuda_remitos"),
            deuda_factura_expr.label("deuda_facturas"),
            oldest_pedido_fecha_subquery.label("oldest_pedido_fecha"),
            ultima_compra_subquery.label("ultima_compra_fecha"),
            User.nombre_completo.label("vendedor_nombre"),
            Localidad.nombre.label("localidad_nombre"),
            Zona.nombre.label("zona_nombre")
        )
        .outerjoin(User, Cliente.vendedor_id == User.id)
        .outerjoin(Localidad, Cliente.localidad_id == Localidad.id)
        .outerjoin(Zona, Cliente.zona_id == Zona.id)
        .where(Cliente.id.in_(select(base_query.with_only_columns(Cliente.id).subquery().c.id)))
        .order_by(Cliente.nombre)
    )
    # Cuando el front pide `all=true` traemos todo sin offset/limit para filtrar/ordenar
    # en memoria. En ese modo la deuda se calcula para todos los clientes en una sola query.
    if not sin_paginar:
        deuda_query = deuda_query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(deuda_query)
    rows = result.all()

    items = []
    from app.utils.tz import hoy_ar
    today = hoy_ar()

    for cliente, deuda, deuda_remitos, deuda_facturas, oldest_fecha, ultima_compra_fecha, vendedor_nombre, localidad_nombre, zona_nombre in rows:
        cliente_dict = ClienteResponse.model_validate(cliente).model_dump()
        deuda_float = float(deuda) if deuda else 0.0
        cliente_dict["deuda"] = deuda_float
        cliente_dict["saldo_remitos"] = float(deuda_remitos) if deuda_remitos else 0.0
        cliente_dict["saldo_facturas"] = float(deuda_facturas) if deuda_facturas else 0.0
        cliente_dict["vendedor_nombre"] = vendedor_nombre
        cliente_dict["localidad_nombre"] = localidad_nombre
        cliente_dict["zona_nombre"] = zona_nombre

        # Determine days overdue for semaphore
        days_overdue = None
        if oldest_fecha:
            days_overdue = (today - oldest_fecha).days
        elif (cliente_dict["saldo_remitos"] > 0 or cliente_dict["saldo_facturas"] > 0):
            # If there is debt but no active pending order found, it must be from deuda_inicial
            # or legacy imputations. We treat it as old debt.
            days_overdue = None # calcular_semaforo handles None as "old debt" case

        cliente_dict["semaforo"] = calcular_semaforo(deuda_float, days_overdue)
        cliente_dict["dias_mora"] = days_overdue

        # Semáforo de ACTIVIDAD (recencia de compra)
        dias_ultima = (today - ultima_compra_fecha).days if ultima_compra_fecha else None
        cliente_dict["ultima_compra"] = ultima_compra_fecha.isoformat() if ultima_compra_fecha else None
        cliente_dict["dias_ultima_compra"] = dias_ultima
        cliente_dict["semaforo_actividad"] = calcular_semaforo_actividad(dias_ultima)

        items.append(ClienteConDeuda(**cliente_dict))


    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/pendientes")
async def list_clientes_pendientes(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """List clients pending approval."""
    base_query = select(Cliente).where(
        and_(Cliente.aprobado == False, Cliente.activo == True)  # noqa: E712
    )

    if search:
        search_filter = or_(
            Cliente.nombre.ilike(f"%{search}%"),
            Cliente.cuit.ilike(f"%{search}%"),
        )
        base_query = base_query.where(search_filter)

    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    result = await db.execute(
        select(Cliente, User.nombre_completo.label("vendedor_nombre"), Localidad.nombre.label("localidad_nombre"), Zona.nombre.label("zona_nombre"))
        .outerjoin(User, Cliente.vendedor_id == User.id)
        .outerjoin(Localidad, Cliente.localidad_id == Localidad.id)
        .outerjoin(Zona, Cliente.zona_id == Zona.id)
        .where(Cliente.id.in_(select(base_query.with_only_columns(Cliente.id).subquery().c.id)))
        .order_by(Cliente.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()

    items = []
    for cliente, vendedor_nombre, localidad_nombre, zona_nombre in rows:
        d = ClienteResponse.model_validate(cliente).model_dump()
        d["vendedor_nombre"] = vendedor_nombre
        d["localidad_nombre"] = localidad_nombre
        d["zona_nombre"] = zona_nombre
        d["deuda"] = 0
        items.append(ClienteConDeuda(**d))

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.patch("/{id}/aprobar")
async def aprobar_cliente(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Cliente).where(Cliente.id == id))
    cliente = result.scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    cliente.aprobado = True
    await db.commit()
    return {"message": f"Cliente {cliente.nombre} aprobado"}


@router.get("/{id}", response_model=ClienteResponse)
async def get_cliente(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Cliente).where(Cliente.id == id))
    cliente = result.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )
    resp = ClienteResponse.model_validate(cliente)
    # Enriquecer con los datos de la localidad (para la dirección de envío por defecto).
    if cliente.localidad_id:
        loc = (await db.execute(select(Localidad).where(Localidad.id == cliente.localidad_id))).scalar_one_or_none()
        if loc:
            resp.localidad_nombre = loc.nombre
            resp.localidad_provincia = loc.provincia
            resp.localidad_codigo_postal = loc.codigo_postal
    return resp


async def _geocodificar(
    db: AsyncSession, direccion: str | None, localidad_id: int | None
) -> tuple[float | None, float | None]:
    """Coordenadas de una dirección. Sin localidad no se intenta: el geocoder
    devuelve cualquier cosa de otra provincia."""
    if not direccion or not localidad_id:
        return None, None
    localidad = (
        await db.execute(select(Localidad).where(Localidad.id == localidad_id))
    ).scalar_one_or_none()
    if localidad is None:
        return None, None
    return await obtener_coordenadas_osm(direccion, localidad.nombre)


async def _update_cliente_coords(cliente: Cliente, db: AsyncSession):
    """Helper to update lat/lon using the geolocating service."""
    lat, lon = await _geocodificar(db, cliente.domicilio, cliente.localidad_id)
    if lat is not None and lon is not None:
        cliente.latitud = lat
        cliente.longitud = lon


# --- Libreta de direcciones de entrega -------------------------------------
#
# Van antes del `POST ""` porque FastAPI resuelve por orden y `/{id}` ya existe;
# rutas más específicas primero.

ROLES_DIRECCIONES = ["ventas", "admin", "super_admin"]


def _direccion_response(d: ClienteDireccion) -> ClienteDireccionResponse:
    resp = ClienteDireccionResponse.model_validate(d)
    resp.localidad_nombre = d.localidad.nombre if d.localidad else None
    return resp


async def _cliente_o_404(db: AsyncSession, cliente_id: int) -> Cliente:
    cliente = (
        await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    ).scalar_one_or_none()
    if cliente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    return cliente


async def _desmarcar_otros_defaults(db: AsyncSession, cliente_id: int, excepto_id: int | None) -> None:
    """Solo una dirección puede ser la propuesta por defecto."""
    q = sa_update(ClienteDireccion).where(ClienteDireccion.cliente_id == cliente_id)
    if excepto_id is not None:
        q = q.where(ClienteDireccion.id != excepto_id)
    await db.execute(q.values(es_default=False))


@router.get("/{cliente_id}/direcciones", response_model=list[ClienteDireccionResponse])
async def list_direcciones(
    cliente_id: int,
    incluir_inactivas: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    await _cliente_o_404(db, cliente_id)
    q = select(ClienteDireccion).where(ClienteDireccion.cliente_id == cliente_id)
    if not incluir_inactivas:
        q = q.where(ClienteDireccion.activo.is_(True))
    filas = (
        await db.execute(q.order_by(ClienteDireccion.es_default.desc(), ClienteDireccion.id))
    ).scalars().all()
    return [_direccion_response(d) for d in filas]


@router.post(
    "/{cliente_id}/direcciones",
    response_model=ClienteDireccionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_direccion(
    cliente_id: int,
    body: ClienteDireccionCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(ROLES_DIRECCIONES)),
):
    """Ventas también puede dar de alta: la dirección nueva suele aparecer en el
    momento de cargar el pedido, y frenar eso hasta que un admin la cargue sería
    peor que el problema."""
    await _cliente_o_404(db, cliente_id)

    lat, lon = await _geocodificar(db, body.direccion, body.localidad_id)
    direccion = ClienteDireccion(
        cliente_id=cliente_id,
        latitud=lat,
        longitud=lon,
        **body.model_dump(),
    )
    db.add(direccion)
    await db.flush()
    if direccion.es_default:
        await _desmarcar_otros_defaults(db, cliente_id, direccion.id)
    await db.commit()

    direccion = (
        await db.execute(select(ClienteDireccion).where(ClienteDireccion.id == direccion.id))
    ).scalar_one()
    return _direccion_response(direccion)


@router.put("/{cliente_id}/direcciones/{direccion_id}", response_model=ClienteDireccionResponse)
async def update_direccion(
    cliente_id: int,
    direccion_id: int,
    body: ClienteDireccionUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(ROLES_DIRECCIONES)),
):
    direccion = (
        await db.execute(
            select(ClienteDireccion).where(
                ClienteDireccion.id == direccion_id,
                ClienteDireccion.cliente_id == cliente_id,
            )
        )
    ).scalar_one_or_none()
    if direccion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dirección no encontrada")

    cambios = body.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(direccion, campo, valor)

    # Si cambió la dirección o la localidad hay que volver a geocodificar: las
    # coordenadas viejas apuntarían a la ubicación anterior en el mapa de reparto.
    if "direccion" in cambios or "localidad_id" in cambios:
        lat, lon = await _geocodificar(db, direccion.direccion, direccion.localidad_id)
        direccion.latitud, direccion.longitud = lat, lon

    if direccion.es_default:
        await _desmarcar_otros_defaults(db, cliente_id, direccion.id)

    await db.commit()
    direccion = (
        await db.execute(select(ClienteDireccion).where(ClienteDireccion.id == direccion_id))
    ).scalar_one()
    return _direccion_response(direccion)


@router.delete("/{cliente_id}/direcciones/{direccion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_direccion(
    cliente_id: int,
    direccion_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(ROLES_DIRECCIONES)),
):
    """Baja lógica. Los pedidos que salieron a esa dirección la referencian, y
    además guardan el texto: borrar la fila les rompería el vínculo sin ganar nada."""
    direccion = (
        await db.execute(
            select(ClienteDireccion).where(
                ClienteDireccion.id == direccion_id,
                ClienteDireccion.cliente_id == cliente_id,
            )
        )
    ).scalar_one_or_none()
    if direccion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dirección no encontrada")

    era_default = direccion.es_default
    direccion.activo = False
    direccion.es_default = False
    await db.flush()

    # Si se dio de baja la principal, asciende la siguiente activa. Un cliente con
    # direcciones pero ninguna marcada dejaba el selector del pedido sin proponer
    # nada, y el vendedor terminaba tipeando a mano una que ya estaba cargada.
    if era_default:
        siguiente = (
            await db.execute(
                select(ClienteDireccion)
                .where(
                    ClienteDireccion.cliente_id == cliente_id,
                    ClienteDireccion.activo.is_(True),
                )
                .order_by(ClienteDireccion.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if siguiente is not None:
            siguiente.es_default = True

    await db.commit()


@router.post("", response_model=ClienteResponse, status_code=status.HTTP_201_CREATED)

async def create_cliente(
    body: ClienteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Ventas can create clients (pending approval), admin creates approved
    is_admin = current_user.rol.value in ("admin", "super_admin")
    if not is_admin and current_user.rol.value != "ventas":
        raise HTTPException(status_code=403, detail="No tiene permisos para crear clientes")

    data = body.model_dump()
    if not is_admin:
        data["aprobado"] = False
        data["vendedor_id"] = current_user.id

    cliente = Cliente(**data)
    # Geocodificación automática para carga manual
    await _update_cliente_coords(cliente, db)
    db.add(cliente)

    await db.commit()
    await db.refresh(cliente)
    return cliente


@router.put("/{id}", response_model=ClienteResponse)
async def update_cliente(
    id: int,
    body: ClienteUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Cliente).where(Cliente.id == id))
    cliente = result.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(cliente, field, value)

    # Si cambió domicilio o localidad, actualizar coordenadas
    if "domicilio" in update_data or "localidad_id" in update_data:
        await _update_cliente_coords(cliente, db)

    await db.commit()

    await db.refresh(cliente)
    return cliente


@router.delete("/{id}")
async def delete_cliente(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(Cliente).where(Cliente.id == id))
    cliente = result.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )

    cliente.activo = False
    await db.commit()
    return {"message": f"Cliente {cliente.nombre} desactivado"}


# --- Unificación (merge) de clientes duplicados ---

_MERGE_MODELS = (
    (Pedido, "pedidos"),
    (Pago, "pagos"),
    (NotaCreditoDebito, "notas"),
    (SolicitudCambioCliente, "solicitudes"),
)


class MergeClientesRequest(BaseModel):
    origen_id: int   # se absorbe y se elimina
    destino_id: int  # se conserva
    # Valores finales elegidos campo por campo (independiente del orden de selección).
    # Solo se aplican los campos de esta lista blanca al cliente destino.
    campos_finales: dict[str, Any] | None = None


_MERGE_CAMPOS_PERMITIDOS = {
    "nombre", "razon_social", "cuit", "domicilio", "telefono", "whatsapp", "email",
    "categoria", "tipo", "condicion_pago", "plazo_dias", "comentarios",
    "localidad_id", "zona_id", "vendedor_id",
}


@router.get("/{id}/asociados")
async def contar_asociados_cliente(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Cuenta registros asociados a un cliente (para previsualizar una unificación)."""
    cliente = (await db.execute(select(Cliente).where(Cliente.id == id))).scalar_one_or_none()
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    counts = {}
    for model, label in _MERGE_MODELS:
        counts[label] = (
            await db.execute(select(func.count()).where(model.cliente_id == id))
        ).scalar_one()
    return {"cliente_id": id, "nombre": cliente.nombre, "asociados": counts}


@router.post("/merge")
async def merge_clientes(
    body: MergeClientesRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Unifica dos clientes: mueve todo lo asociado del ORIGEN al DESTINO y elimina el origen."""
    if body.origen_id == body.destino_id:
        raise HTTPException(status_code=400, detail="Origen y destino no pueden ser el mismo cliente")

    origen = (await db.execute(select(Cliente).where(Cliente.id == body.origen_id))).scalar_one_or_none()
    destino = (await db.execute(select(Cliente).where(Cliente.id == body.destino_id))).scalar_one_or_none()
    if origen is None or destino is None:
        raise HTTPException(status_code=404, detail="Cliente origen o destino no encontrado")

    # Reasignar todas las tablas asociadas del origen al destino
    movidos = {}
    for model, label in _MERGE_MODELS:
        res = await db.execute(
            sa_update(model).where(model.cliente_id == body.origen_id).values(cliente_id=body.destino_id)
        )
        movidos[label] = res.rowcount

    # Absorber la deuda inicial del origen en el destino
    destino.deuda_inicial = (destino.deuda_inicial or Decimal(0)) + (origen.deuda_inicial or Decimal(0))
    destino.deuda_inicial_remito = (destino.deuda_inicial_remito or Decimal(0)) + (origen.deuda_inicial_remito or Decimal(0))
    destino.deuda_inicial_factura = (destino.deuda_inicial_factura or Decimal(0)) + (origen.deuda_inicial_factura or Decimal(0))

    # Aplicar la elección de datos campo por campo al destino (whitelist).
    if body.campos_finales:
        for campo, valor in body.campos_finales.items():
            if campo in _MERGE_CAMPOS_PERMITIDOS:
                setattr(destino, campo, valor)

    origen_nombre = origen.nombre
    await db.delete(origen)
    await db.commit()

    return {
        "origen_id": body.origen_id,
        "origen_nombre": origen_nombre,
        "destino_id": body.destino_id,
        "destino_nombre": destino.nombre,
        "movidos": movidos,
    }


@router.get("/{id}/deuda")
async def get_cliente_deuda(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    from app.models.nota_credito_debito import NotaCreditoDebito, TipoNota

    result = await db.execute(select(Cliente).where(Cliente.id == id))
    cliente = result.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )

    # Helper function for aggregated values
    async def get_sum(subquery):
        res = await db.execute(subquery)
        return float(res.scalar_one() or 0)

    # Pedidos
    p_rem = await get_sum(select(func.coalesce(func.sum(Pedido.importe_total), 0)).where(and_(Pedido.cliente_id == id, Pedido.tipo_documento == "remito", Pedido.shipping_status.notin_(ESTADOS_NO_COMPUTABLES))))
    p_fac = await get_sum(select(func.coalesce(func.sum(Pedido.importe_total), 0)).where(and_(Pedido.cliente_id == id, Pedido.tipo_documento == "factura", Pedido.shipping_status.notin_(ESTADOS_NO_COMPUTABLES))))

    # Pagos
    pag_rem = await get_sum(select(func.coalesce(func.sum(Pago.importe), 0)).where(and_(Pago.cliente_id == id, Pago.tipo_cuenta == "remito", Pago.estado.in_([EstadoPago.pendiente, EstadoPago.acreditado, EstadoPago.recibido, EstadoPago.imputado]))))
    pag_fac = await get_sum(select(func.coalesce(func.sum(Pago.importe), 0)).where(and_(Pago.cliente_id == id, Pago.tipo_cuenta == "factura", Pago.estado.in_([EstadoPago.pendiente, EstadoPago.acreditado, EstadoPago.recibido, EstadoPago.imputado]))))

    # Notas
    nc_rem = await get_sum(select(func.coalesce(func.sum(NotaCreditoDebito.importe_total), 0)).where(and_(NotaCreditoDebito.cliente_id == id, NotaCreditoDebito.tipo_cuenta == "remito", NotaCreditoDebito.tipo == TipoNota.credito)))
    nd_rem = await get_sum(select(func.coalesce(func.sum(NotaCreditoDebito.importe_total), 0)).where(and_(NotaCreditoDebito.cliente_id == id, NotaCreditoDebito.tipo_cuenta == "remito", NotaCreditoDebito.tipo == TipoNota.debito)))
    
    nc_fac = await get_sum(select(func.coalesce(func.sum(NotaCreditoDebito.importe_total), 0)).where(and_(NotaCreditoDebito.cliente_id == id, NotaCreditoDebito.tipo_cuenta == "factura", NotaCreditoDebito.tipo == TipoNota.credito)))
    nd_fac = await get_sum(select(func.coalesce(func.sum(NotaCreditoDebito.importe_total), 0)).where(and_(NotaCreditoDebito.cliente_id == id, NotaCreditoDebito.tipo_cuenta == "factura", NotaCreditoDebito.tipo == TipoNota.debito)))

    saldo_remitos = p_rem - pag_rem + nd_rem - nc_rem + float(cliente.deuda_inicial_remito)
    saldo_facturas = p_fac - pag_fac + nd_fac - nc_fac + float(cliente.deuda_inicial_factura)

    return {
        "deuda": saldo_remitos + saldo_facturas,
        "saldo_remitos": saldo_remitos,
        "saldo_facturas": saldo_facturas,
        "total_pedidos": p_rem + p_fac,
        "total_pagos": pag_rem + pag_fac,
        "deuda_inicial": float(cliente.deuda_inicial),
    }


async def _get_or_create_localidad(db: AsyncSession, nombre: str) -> int | None:
    nombre = nombre.strip()
    if not nombre or nombre == "-":
        return None
    result = await db.execute(select(Localidad).where(func.lower(Localidad.nombre) == nombre.lower()))
    localidad = result.scalar_one_or_none()
    if localidad:
        return localidad.id
    new_loc = Localidad(nombre=nombre)
    db.add(new_loc)
    await db.flush()
    return new_loc.id


def _map_cliente_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Map a JSON row (from scrapper or direct format) to cliente fields."""
    nombre = (
        row.get("nombre")
        or row.get("c_nombre")
        or row.get("razon_social")
        or row.get("c_razonsocial")
        or ""
    ).strip()

    if not nombre:
        return None

    return {
        "nombre": nombre,
        "razon_social": (row.get("razon_social") or row.get("c_razonsocial") or "").strip() or None,
        "cuit": (row.get("cuit") or row.get("c_cuit") or "").strip() or None,
        "domicilio": (row.get("domicilio") or row.get("c_domicilio") or row.get("direccion") or "-").strip(),
        "_raw_localidad": (row.get("localidad") or row.get("c_localidad") or row.get("ciudad") or "-").strip(),
        "telefono": (row.get("telefono") or row.get("c_telefono") or "").strip() or None,
        "email": (row.get("email") or row.get("c_email") or row.get("mail") or "").strip() or None,
    }


@router.post("/import")
async def import_clientes(
    items: list[dict[str, Any]] = Body(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for i, row in enumerate(items):
        mapped = _map_cliente_row(row)
        if not mapped or not mapped.get("nombre"):
            skipped += 1
            continue

        try:
            existing_q = select(Cliente).where(Cliente.nombre == mapped["nombre"])
            if mapped.get("cuit"):
                existing_q = select(Cliente).where(
                    (Cliente.nombre == mapped["nombre"]) | (Cliente.cuit == mapped["cuit"])
                )

            result = await db.execute(existing_q)
            existing = result.scalar_one_or_none()

            raw_loc = mapped.pop("_raw_localidad", "")
            localidad_id = await _get_or_create_localidad(db, raw_loc) if raw_loc else None
            mapped["localidad_id"] = localidad_id

            if existing:
                for field, value in mapped.items():
                    if value is not None:
                        setattr(existing, field, value)
                existing.activo = True
                updated += 1
            else:
                cliente = Cliente(**mapped)
                db.add(cliente)
                created += 1
        except Exception as e:
            errors.append(f"Fila {i + 1} ({mapped.get('nombre', '?')}): {str(e)}")
            skipped += 1

    await db.commit()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total": len(items),
        "errors": errors[:20],
    }


async def _get_or_create_vendedor(db: AsyncSession, nombre: str) -> int | None:
    """Find or create a vendedor (ventas user) by first name. Returns user id."""
    nombre = nombre.strip()
    if not nombre or nombre.upper() == "NUEVO":
        return None

    result = await db.execute(
        select(User).where(
            func.lower(User.nombre_completo) == nombre.lower()
        )
    )
    user = result.scalar_one_or_none()
    if user:
        return user.id

    username = nombre.lower().replace(" ", "")
    email = f"{username}@sanalle.com"

    for suffix in ["", "2", "3", "4", "5"]:
        check_user = await db.execute(
            select(User).where(
                (User.username == f"{username}{suffix}") | (User.email == f"{email.split('@')[0]}{suffix}@sanalle.com")
            )
        )
        if not check_user.scalar_one_or_none():
            username = f"{username}{suffix}"
            email = f"{email.split('@')[0]}{suffix}@sanalle.com"
            break

    new_user = User(
        email=email,
        username=username,
        hashed_password=get_password_hash("ventas123"),
        nombre_completo=nombre,
        rol=RolUsuario.ventas,
        activo=True,
    )
    db.add(new_user)
    await db.flush()
    return new_user.id


@router.post("/import-xlsx")
async def import_clientes_xlsx(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Import clients from an XLSX file exported from the old system."""
    import openpyxl

    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe ser un XLSX",
        )

    contents = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
    ws = wb.active

    created = 0
    updated = 0
    skipped = 0
    vendedores_created: list[str] = []
    errors: list[str] = []

    vendedor_cache: dict[str, int | None] = {}
    localidad_cache: dict[str, int | None] = {}

    existing_vendedores_result = await db.execute(select(User.nombre_completo).where(User.rol == RolUsuario.ventas))
    existing_vendedor_names = {row[0].lower() for row in existing_vendedores_result.all()}

    rows = list(ws.iter_rows(min_row=1, values_only=True))
    total_client_rows = 0

    for row in rows:
        if not row or not isinstance(row[0], (int, float)):
            continue
        total_client_rows += 1

        try:
            nombre = str(row[1] or "").strip()
            if not nombre:
                skipped += 1
                continue

            razon_social = str(row[2] or "").strip() or None
            cuit = str(row[3] or "").strip() or None
            domicilio = str(row[4] or "").strip() or "-"
            localidad = str(row[5] or "").strip() or "-"
            telefono = str(row[6] or "").strip() or None
            categoria = str(row[7] or "").strip() or None
            raw_deuda = row[8]
            deuda_inicial = Decimal(str(raw_deuda)) if raw_deuda and raw_deuda != 0 else Decimal("0")
            vendedor_nombre = str(row[10] or "").strip()

            vendedor_id = None
            if vendedor_nombre:
                if vendedor_nombre not in vendedor_cache:
                    is_new = vendedor_nombre.lower() not in existing_vendedor_names
                    vendedor_cache[vendedor_nombre] = await _get_or_create_vendedor(db, vendedor_nombre)
                    if is_new and vendedor_cache[vendedor_nombre] is not None:
                        vendedores_created.append(vendedor_nombre)
                vendedor_id = vendedor_cache[vendedor_nombre]

            localidad_id = None
            if localidad and localidad != "-":
                if localidad not in localidad_cache:
                    localidad_cache[localidad] = await _get_or_create_localidad(db, localidad)
                localidad_id = localidad_cache[localidad]

            result = await db.execute(
                select(Cliente).where(Cliente.nombre == nombre)
            )
            existing = result.scalar_one_or_none()

            if existing:
                if razon_social:
                    existing.razon_social = razon_social
                if cuit:
                    existing.cuit = cuit
                existing.domicilio = domicilio
                if localidad_id:
                    existing.localidad_id = localidad_id
                if telefono:
                    existing.telefono = telefono
                if categoria:
                    existing.categoria = categoria
                if vendedor_id:
                    existing.vendedor_id = vendedor_id
                existing.deuda_inicial = deuda_inicial
                existing.activo = True
                updated += 1
            else:
                cliente = Cliente(
                    nombre=nombre,
                    razon_social=razon_social,
                    cuit=cuit,
                    domicilio=domicilio,
                    localidad_id=localidad_id,
                    telefono=telefono,
                    categoria=categoria,
                    vendedor_id=vendedor_id,
                    deuda_inicial=deuda_inicial,
                )
                db.add(cliente)
                created += 1

        except Exception as e:
            errors.append(f"Fila ({row[1]}): {str(e)}")
            skipped += 1

    await db.commit()
    wb.close()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total": total_client_rows,
        "vendedores_created": list(set(vendedores_created)),
        "errors": errors[:20],
    }

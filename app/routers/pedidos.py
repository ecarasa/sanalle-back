from app.services.geolocating import obtener_ruta_tomtom, obtener_coordenadas_osm, obtener_coordenadas_tomtom
from app.models.user import RolUsuario
import os
from collections import defaultdict

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import httpx
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select, func, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, aliased
from app.core.config import settings
from app.core.database import get_db
from app.models.cliente import Cliente
from app.models.pedido import Pedido, EstadoDespacho, EstadoPago as EstadoPagoPedido, TipoDocumento
from app.models.pedido_item import PedidoItem
from app.models.producto import Producto
from app.models.pago_imputacion import PagoImputacion
from app.models.user import User
from app.models.rutas import Ruta
from app.schemas.pedido import (
    PedidoCreate,
    PedidoUpdate,
    PedidoShippingStatusUpdate,
    PedidoPaymentStatusUpdate,
    PedidoItemComisionUpdate,
    PedidoItemResponse,
    PedidoResponse,
    AsignarRepartidorRequest,
    OptimizarRutaRequest,
    OptimizarRutaResponse,
    UbicacionUpdate,
)
from app.models.bitacora_pedido import BitacoraPedido
from app.schemas.bitacora_pedido import BitacoraPedidoResponse
from app.services import bitacora_service
from app.services.bitacora_service import (
    nuevo_grupo_id,
    registrar_cambios_pedido,
    registrar_diff_items,
    registrar_evento,
    snapshot_items,
    snapshot_pedido,
)
from app.services.pdf_service import generate_pedido_pdf
from app.services.pago_service import imputar_pagos_a_pedido
from app.services.pricing_service import LISTAS
from app.services.semaforo_service import calcular_semaforo_pedido
from app.utils.deps import get_current_user, require_role
from app.utils.filters import apply_column_filters
from collections import defaultdict

router = APIRouter()

# Valid state transitions
SHIPPING_TRANSITIONS: dict[str, list[str]] = {
    "pendiente":           ["en_preparacion", "cancelado"],
    "en_preparacion":      ["listo_para_despacho", "pendiente", "cancelado"],
    "listo_para_despacho": ["en_camino", "en_preparacion", "cancelado"],
    "en_camino":           ["entregado", "cancelado"],
    "entregado":           [],
    "cancelado":           [],
}

PAYMENT_TRANSITIONS: dict[str, list[str]] = {
    "pendiente": ["pagado", "parcial", "cancelado"],
    "parcial":   ["pagado", "cancelado"],
    "pagado":    [],
    "cancelado": [],
}


@router.get("/transiciones")
async def get_transiciones(
    _current_user: User = Depends(get_current_user),
):
    """Expose valid status transitions to the frontend."""
    return {"shipping": SHIPPING_TRANSITIONS, "payment": PAYMENT_TRANSITIONS}


def _comision_para(vendedor: User | None, producto: Producto) -> float:
    """Comisión del vendedor según la categoría del producto (GENERICO / OTC)."""
    if vendedor is None:
        return 0.0
    categoria = (producto.categoria_producto or "").strip().upper()
    if categoria == "GENERICO":
        return vendedor.comision_generico or 0.0
    if categoria == "OTC":
        return vendedor.comision_otc or 0.0
    return 0.0


def _build_item_response(item: PedidoItem) -> PedidoItemResponse:
    producto_nombre = item.producto.nombre if item.producto else None
    margen = None
    if item.producto and item.producto.costo_mas_iibb and item.producto.costo_mas_iibb > 0:
        precio_u = float(item.precio_unitario)
        costo = float(item.producto.costo_mas_iibb)
        if precio_u > 0:
            margen = round((precio_u - costo) / precio_u * 100, 2)
    producto_precios: dict[str, float | None] = {}
    if item.producto:
        for lista in LISTAS:
            valor = getattr(item.producto, lista.precio_field, None)
            producto_precios[lista.key] = float(valor) if valor is not None else None

    return PedidoItemResponse(
        id=item.id,
        producto_id=item.producto_id,
        cantidad_cajas=item.cantidad_cajas,
        cantidad_blisters=item.cantidad_blisters,
        cantidad=item.cantidad,
        precio_lista=float(item.precio_lista) if item.precio_lista is not None else None,
        descuento_porcentaje=float(item.descuento_porcentaje) if item.descuento_porcentaje is not None else None,
        precio_unitario=float(item.precio_unitario),
        precio_total=float(item.precio_total),
        producto_nombre=producto_nombre,
        margen=margen,
        producto_precios=producto_precios,
    )


def _build_pedido_response(pedido: Pedido) -> PedidoResponse:
    """Build a PedidoResponse from a Pedido ORM instance with loaded relationships."""
    items = [_build_item_response(item) for item in pedido.items]

    semaforo = calcular_semaforo_pedido(
        shipping_status=pedido.shipping_status.value,
        payment_status=pedido.payment_status.value,
        fecha_entrega=pedido.fecha_entrega,
        despachado=pedido.despachado,
        fecha_compromiso_pago=pedido.fecha_compromiso_pago,
    )

    return PedidoResponse(
        id=pedido.id,
        numero_pedido=pedido.numero_pedido,
        cliente_id=pedido.cliente_id,
        cliente_nombre=pedido.cliente.nombre if pedido.cliente else None,
        cliente_tipo=pedido.cliente.tipo if pedido.cliente else None,
        vendedor_id=pedido.vendedor_id,
        vendedor_nombre=pedido.vendedor.nombre_completo if pedido.vendedor else None,
        shipping_status=pedido.shipping_status.value,
        payment_status=pedido.payment_status.value,
        semaforo=semaforo,
        tipo_documento=pedido.tipo_documento.value if pedido.tipo_documento else None,
        fecha=pedido.fecha,
        fecha_entrega=pedido.fecha_entrega,
        transporte=pedido.transporte,
        fecha_compromiso_pago=pedido.fecha_compromiso_pago,
        despachado=pedido.despachado,
        sociedad=pedido.sociedad,
        tipo_precio=pedido.tipo_precio,
        importe_total=float(pedido.importe_total),
        saldo_pendiente=float(pedido.saldo_pendiente),
        observacion=pedido.observacion,
        cliente_domicilio=pedido.cliente.domicilio if pedido.cliente else None,
        cliente_telefono=pedido.cliente.telefono or pedido.cliente.whatsapp if pedido.cliente else None,
        cliente_localidad=pedido.cliente.localidad_rel.nombre if pedido.cliente and pedido.cliente.localidad_rel else None,
        cliente_zona=pedido.cliente.zona_rel.nombre if pedido.cliente and pedido.cliente.zona_rel else None,
        repartidor_id=pedido.repartidor_id,
        repartidor_nombre=pedido.repartidor.nombre_completo if pedido.repartidor else None,
        direccion_entrega=pedido.direccion_entrega or (pedido.cliente.domicilio if pedido.cliente else None),
        latitud=pedido.latitud if pedido.latitud is not None else (pedido.cliente.latitud if pedido.cliente else None),
        longitud=pedido.longitud if pedido.longitud is not None else (pedido.cliente.longitud if pedido.cliente else None),
        bultos=pedido.bultos,
        items=items,

        created_at=pedido.created_at,
        updated_at=pedido.updated_at,
    )


def _load_options():
    return [
        selectinload(Pedido.cliente).selectinload(Cliente.localidad_rel),
        selectinload(Pedido.cliente).selectinload(Cliente.zona_rel),
        selectinload(Pedido.vendedor),
        selectinload(Pedido.repartidor),
        selectinload(Pedido.items).selectinload(PedidoItem.producto),
    ]


@router.get("")
async def list_pedidos(
    search: str = Query("", description="Buscar por numero_pedido o nombre de cliente"),
    cliente_id: int | None = Query(None),
    shipping_status: str | None = Query(None, description="Filtrar por estado de despacho"),
    payment_status: str | None = Query(None, description="Filtrar por estado de pago"),
    tipo_documento: str | None = Query(None),
    fecha_desde: date | None = Query(None),
    fecha_hasta: date | None = Query(None),
    vendedor_id: int | None = Query(None),
    repartidor_id: int | None = Query(None),
    column_filters: str | None = Query(None, alias="filters", description="JSON column filters"),
    sort_by: str | None = Query(None, description="Columna por la que ordenar"),
    sort_dir: str = Query("desc", description="Dirección de orden: asc o desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    Vendedor = aliased(User, name="vendedor")
    Repartidor = aliased(User, name="repartidor")

    base_query = select(Pedido).join(Cliente, Pedido.cliente_id == Cliente.id).join(
        Vendedor, Pedido.vendedor_id == Vendedor.id
    ).outerjoin(
        Repartidor, Pedido.repartidor_id == Repartidor.id
    )

    filters = []

    if current_user.rol.value == "ventas":
        filters.append(Pedido.vendedor_id == current_user.id)

    # Lógica de repartidor: Si no es admin, solo ve lo asignado a él si se pide "Mis Entregas" (o por defecto si es repartidor?)
    # El usuario pidió: "el admin ve TODO... pero que si el repartidor se mete pueda ver solo las suyas"
    # Si se pasa repartidor_id, lo usamos. Si no es admin, forzamos su ID si rol != ventas (aunque no hay rol repartidor formalmente)
    if current_user.rol.value not in ("admin", "super_admin"):
        if current_user.rol.value == "ventas":
            pass # Ya filtrado por vendedor_id arriba
        else:
            if repartidor_id and repartidor_id != current_user.id:
                raise HTTPException(status_code=403, detail="No tienes permiso para ver entregas de otro repartidor")
            if not repartidor_id:
                filters.append(Pedido.repartidor_id == current_user.id)
    
    if repartidor_id is not None:
        filters.append(Pedido.repartidor_id == repartidor_id)

    if search:
        like_pattern = f"%{search}%"
        filters.append(
            or_(
                Pedido.numero_pedido.ilike(like_pattern),
                Cliente.nombre.ilike(like_pattern),
            )
        )

    if cliente_id is not None:
        filters.append(Pedido.cliente_id == cliente_id)

    if vendedor_id is not None:
        filters.append(Pedido.vendedor_id == vendedor_id)

    if shipping_status is not None:
        try:
            filters.append(Pedido.shipping_status == EstadoDespacho(shipping_status))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"shipping_status inválido: {shipping_status}. Válidos: {[e.value for e in EstadoDespacho]}",
            )

    if payment_status is not None:
        try:
            filters.append(Pedido.payment_status == EstadoPagoPedido(payment_status))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"payment_status inválido: {payment_status}. Válidos: {[e.value for e in EstadoPagoPedido]}",
            )

    if tipo_documento:
        filters.append(Pedido.tipo_documento == TipoDocumento(tipo_documento))

    if fecha_desde:
        filters.append(Pedido.fecha >= fecha_desde)
    if fecha_hasta:
        filters.append(Pedido.fecha <= fecha_hasta)

    if filters:
        base_query = base_query.where(*filters)

    base_query = apply_column_filters(
        base_query,
        Pedido,
        column_filters,
        allowed_columns={
            "numero_pedido", "shipping_status", "payment_status", "fecha", "fecha_entrega",
            "importe_total", "cliente_nombre", "vendedor_nombre", "tipo_documento",
            "transporte", "sociedad", "despachado", "tipo_precio", "saldo_pendiente",
            "repartidor_id", "repartidor_nombre",
        },
        extra_mappings={
            "cliente_nombre": Cliente.nombre,
            "vendedor_nombre": Vendedor.nombre_completo,
            "repartidor_nombre": Repartidor.nombre_completo,
        },
    )

    count_query = select(func.count()).select_from(
        base_query.with_only_columns(Pedido.id).subquery()
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    sum_query = select(func.coalesce(func.sum(Pedido.importe_total), 0)).select_from(
        base_query.with_only_columns(Pedido.id, Pedido.importe_total).subquery()
    )
    sum_result = await db.execute(sum_query)
    total_importe = float(sum_result.scalar_one())

    _sort_columns = {
        "numero_pedido": Pedido.numero_pedido,
        "cliente_nombre": Cliente.nombre,
        "fecha": Pedido.fecha,
        "fecha_entrega": Pedido.fecha_entrega,
        "vendedor_nombre": User.nombre_completo,
        "importe_total": Pedido.importe_total,
        "shipping_status": Pedido.shipping_status,
        "payment_status": Pedido.payment_status,
        "despachado": Pedido.despachado,
    }
    sort_col = _sort_columns.get(sort_by) if sort_by else None
    if sort_col is not None:
        order_expr = sort_col.asc() if sort_dir == "asc" else sort_col.desc()
    else:
        order_expr = Pedido.id.desc()

    data_query = (
        base_query.options(*_load_options())
        .order_by(order_expr)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(data_query)
    pedidos = result.scalars().unique().all()

    items = [_build_pedido_response(p) for p in pedidos]

    return {
        "items": items,
        "total": total,
        "total_importe": total_importe,
        "page": page,
        "page_size": page_size,
    }

@router.get("/calendario")
async def get_pedido_calendario(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return counts of orders per delivery date with details, filtered by user role."""
    
    base_query = (
        select(Pedido)
        .options(*_load_options())
        .where(Pedido.fecha_entrega.isnot(None))
        .where(Pedido.shipping_status != EstadoDespacho.cancelado)
    )

    filters = []
    if current_user.rol.value == "ventas":
        filters.append(Pedido.vendedor_id == current_user.id)
    elif current_user.rol.value not in ("admin", "super_admin"):
        filters.append(or_(Pedido.vendedor_id == current_user.id, Pedido.repartidor_id == current_user.id))

    if filters:
        base_query = base_query.where(*filters)

    
    result = await db.execute(base_query)
    rows = result.scalars().all()

    # 3. Agrupamos los resultados en Python usando un diccionario
    entregas_dict = defaultdict(lambda: {"count": 0, "detalles": []})

    for row in rows:
        fecha_str = str(row.fecha_entrega)
        entregas_dict[fecha_str]["count"] += 1
        
        texto_detalle = f"Pedido #{row.id} - {row.cliente.nombre}"
        entregas_dict[fecha_str]["detalles"].append(texto_detalle)

   
    return [
        {
            "fecha": fecha, 
            "count": data["count"], 
            "detalles": data["detalles"]
        }
        for fecha, data in entregas_dict.items()
    ]

@router.get("/rutas_entregas")
async def get_rutas_entregas(
    fecha: date = Query(..., description="Fecha para trazar la ruta"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve los pedidos en estado 'en_camino' para la fecha dada como lista plana."""

    if current_user.rol.value not in (
        RolUsuario.ventas.value,
        RolUsuario.admin.value,
        RolUsuario.super_admin.value,
        RolUsuario.repartidor.value,
    ):
        raise HTTPException(status_code=403, detail="No tienes permisos para ver rutas de entrega.")

    query = (
        select(Pedido)
        .where(Pedido.fecha_entrega == fecha)
        .where(Pedido.shipping_status == EstadoDespacho.en_camino)
        .options(*_load_options())
    )

    result = await db.execute(query)
    pedidos = result.scalars().all()

    puntos = []
    for p in pedidos:
        lat = p.latitud if p.latitud is not None else (p.cliente.latitud if p.cliente else None)
        lon = p.longitud if p.longitud is not None else (p.cliente.longitud if p.cliente else None)
        if lat is None or lon is None:
            continue
        puntos.append({
            "pedido_id": p.id,
            "numero_pedido": p.numero_pedido,
            "cliente_id": p.cliente_id,
            "cliente": p.cliente.nombre if p.cliente else "Consumidor Final",
            "direccion_texto": p.direccion_entrega or (p.cliente.domicilio if p.cliente else ""),
            "latitud": lat,
            "longitud": lon,
            "estado": p.shipping_status.value,
            "zona": p.cliente.zona_rel.nombre if p.cliente and p.cliente.zona_rel else None,
        })

    return puntos

@router.post("/optimizar_ruta", response_model=OptimizarRutaResponse)
async def optimizar_ruta(
    request: OptimizarRutaRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    if len(request.coordenadas) < 2:
        raise HTTPException(status_code=400, detail="Se requieren al menos 2 coordenadas")
        
    if not request.pedidos_ids:
        raise HTTPException(status_code=400, detail="Se requieren IDs para la huella")

    # 1. Generar huella MD5
    hash_string = ",".join(str(i) for i in sorted(request.pedidos_ids))
    hash_id = hashlib.md5(hash_string.encode()).hexdigest()

    # 2. Buscar en caché (DB)
    query_ruta = select(Ruta).where(Ruta.hash_id == hash_id)
    result_ruta = await db.execute(query_ruta)
    ruta = result_ruta.scalar_one_or_none()

    if ruta and ruta.ruta_geojson and ruta.orden_waypoints:
        try:
            return OptimizarRutaResponse(
                hash_id=hash_id,
                coords=json.loads(ruta.ruta_geojson),
                km=ruta.distancia_km or 0.0,
                tiempo_minutos=getattr(ruta, 'tiempo_minutos', 0.0),
                waypoints=json.loads(ruta.orden_waypoints),
                tramos=json.loads(getattr(ruta, 'tramos_json', '[]'))
            )
        except json.JSONDecodeError:
            pass  # Recalcular si hay corrupción

    # 3. Llamar a OSRM para obtener el ORDEN ÓPTIMO (Trip)
    coords_str = ";".join(f"{c.longitud},{c.latitud}" for c in request.coordenadas)
    url_osrm = (
        f"https://router.project-osrm.org/trip/v1/driving/{coords_str}"
        "?source=first&roundtrip=false&overview=false" # overview=false porque no necesitamos su polyline
    )

    async with httpx.AsyncClient() as client:
        try:
            resp_osrm = await client.get(url_osrm, timeout=10.0)
            resp_osrm.raise_for_status()
            data_osrm = resp_osrm.json()
            
            if data_osrm.get("code") != "Ok" or not data_osrm.get("waypoints"):
                raise HTTPException(status_code=500, detail="No se pudo optimizar el orden en OSRM")
                
            waypoints_data = data_osrm["waypoints"]
            waypoints_indices = [wp["waypoint_index"] for wp in waypoints_data]

        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Error en comunicación con OSRM: {exc}")

    # 4. Reordenar nuestras coordenadas basándonos en la respuesta de OSRM
    coords_con_indice = [
        (request.coordenadas[i], waypoints_data[i]["waypoint_index"])
        for i in range(len(request.coordenadas))
    ]
    # Ordenamos de menor a mayor según el waypoint_index
    coords_con_indice.sort(key=lambda x: x[1])
    
    # Extraemos solo las tuplas (latitud, longitud) ya ordenadas para TomTom
    coords_ordenadas_tomtom = [
        (c.latitud, c.longitud) for c, idx in coords_con_indice
    ]

    # 5. Llamar a TomTom para obtener la ruta enriquecida y con tráfico
    try:
        tomtom_data = await obtener_ruta_tomtom(coords_ordenadas_tomtom)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error calculando ruta en TomTom: {str(e)}")

    # 6. Guardar el Snapshot en la Base de Datos
    if not ruta:
        ruta = Ruta(hash_id=hash_id)
        db.add(ruta)
    
    ruta.ruta_geojson = json.dumps(tomtom_data["coords"])
    ruta.distancia_km = tomtom_data["km"]
    ruta.tiempo_minutos = tomtom_data["tiempo_minutos"]
    ruta.tramos_json = json.dumps(tomtom_data["tramos"])
    ruta.orden_waypoints = json.dumps(waypoints_indices)
    ruta.fecha_entrega = date.today()
    
    await db.commit()

    # 7. Retornar al Frontend
    return OptimizarRutaResponse(
        hash_id=hash_id,
        coords=tomtom_data["coords"],
        km=tomtom_data["km"],
        tiempo_minutos=tomtom_data["tiempo_minutos"],
        waypoints=waypoints_indices,
        tramos=tomtom_data["tramos"]
    )

@router.patch("/rutas/{hash_id}/iniciar")
async def iniciar_recorrido(
    hash_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Ruta).where(Ruta.hash_id == hash_id))
    ruta = result.scalar_one_or_none()
    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    try:
        hora_inicio = datetime.fromisoformat(body["hora_inicio"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="hora_inicio inválido, use formato ISO")

    # Si el frontend envía ETAs pre-calculadas (con timezone correcto), usarlas directamente
    etas: list[dict] = body.get("etas") or []
    if not etas:
        tramos = json.loads(ruta.tramos_json) if isinstance(ruta.tramos_json, str) else (ruta.tramos_json or [])
        hora_inicio_aware = hora_inicio if hora_inicio.tzinfo else hora_inicio.replace(tzinfo=timezone.utc)
        acumulado_min = 0.0
        for i, tramo in enumerate(tramos):
            acumulado_min += tramo.get("tiempo_minutos", 0)
            eta_dt = hora_inicio_aware + timedelta(minutes=acumulado_min)
            etas.append({"parada_index": i, "eta_iso": eta_dt.isoformat()})

    ruta.inicio_recorrido = hora_inicio
    ruta.eta_paradas = etas
    await db.commit()

    return {
        "hash_id": hash_id,
        "inicio": hora_inicio.isoformat(),
        "etas": etas,
    }


@router.patch("/rutas/{hash_id}/terminar")
async def terminar_recorrido(
    hash_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Ruta).where(Ruta.hash_id == hash_id))
    ruta = result.scalar_one_or_none()
    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    pedidos_ids: list[int] = body.get("pedidos_ids", [])
    if not pedidos_ids:
        raise HTTPException(status_code=400, detail="pedidos_ids requerido")

    actualizados = 0
    errores: list[dict] = []

    for pedido_id in pedidos_ids:
        result_p = await db.execute(
            select(Pedido).where(Pedido.id == pedido_id).options(*_load_options())
        )
        pedido = result_p.scalar_one_or_none()
        if not pedido:
            errores.append({"pedido_id": pedido_id, "error": "no encontrado"})
            continue
        if pedido.shipping_status != EstadoDespacho.en_camino:
            errores.append({"pedido_id": pedido_id, "error": f"estado inválido: {pedido.shipping_status.value}"})
            continue
        # Apply same stock logic as PATCH /{id}/shipping-status for en_camino → entregado
        for item in pedido.items:
            prod_result = await db.execute(
                select(Producto).where(Producto.id == item.producto_id).with_for_update()
            )
            producto = prod_result.scalar_one_or_none()
            if producto:
                es_sanalle = (pedido.sociedad and pedido.sociedad.lower() == "sanalle") or (pedido.tipo_documento == TipoDocumento.factura)
                if es_sanalle:
                    producto.modify_stock_a(-item.cantidad_cajas, -item.cantidad_blisters, is_reservation=True)
                else:
                    producto.modify_stock_b(-item.cantidad_cajas, -item.cantidad_blisters, is_reservation=True)
        pedido.shipping_status = EstadoDespacho.entregado
        actualizados += 1

    ruta.fin_recorrido = datetime.now(tz=timezone.utc)
    await db.commit()

    return {"actualizados": actualizados, "errores": errores}


@router.patch("/{pedido_id}/ubicacion")
async def actualizar_ubicacion(
    pedido_id: int,
    body: UbicacionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.rol.value not in (
        RolUsuario.admin.value,
        RolUsuario.super_admin.value,
        RolUsuario.repartidor.value,
    ):
        raise HTTPException(status_code=403, detail="Sin permiso para modificar la ubicación")

    result = await db.execute(
        select(Pedido)
        .where(Pedido.id == pedido_id)
        .options(selectinload(Pedido.cliente).selectinload(Cliente.localidad_rel))
    )
    pedido = result.scalar_one_or_none()
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    ciudad = (
        pedido.cliente.localidad_rel.nombre
        if pedido.cliente and pedido.cliente.localidad_rel
        else "Buenos Aires"
    )
    lat, lon = await obtener_coordenadas_tomtom(body.direccion, ciudad)
    if lat is None or lon is None:
        raise HTTPException(status_code=422, detail="No se pudo geolocalizar la dirección ingresada")

    pedido.direccion_entrega = body.direccion
    pedido.latitud = lat
    pedido.longitud = lon

    # Invalidate any cached route for this delivery date so the map recalculates
    if pedido.fecha_entrega:
        await db.execute(delete(Ruta).where(Ruta.fecha_entrega == pedido.fecha_entrega))

    await db.commit()

    return {"latitud": lat, "longitud": lon, "direccion_entrega": body.direccion}


@router.get("/{id}")
async def get_pedido(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = select(Pedido).where(Pedido.id == id).options(*_load_options())
    result = await db.execute(query)
    pedido = result.scalar_one_or_none()
    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pedido no encontrado",
        )
    return _build_pedido_response(pedido)


@router.get("/{cliente_id}/pedidos_a_imputar")
async def get_pedidos_a_imputar_by_cliente(
    cliente_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = (
        select(Pedido)
        .where(
            Pedido.cliente_id == cliente_id,
            Pedido.saldo_pendiente > 0,
        )
        .order_by(Pedido.created_at.asc())
        .options(*_load_options())
    )
    result = await db.execute(query)
    pedidos = result.scalars().unique().all()

    return {
        "pedidos": [_build_pedido_response(p) for p in pedidos],
    }


@router.get("/{id}/bitacora")
async def get_bitacora_pedido(
    id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Historial de modificaciones del pedido, del cambio más reciente al más viejo."""
    base = select(BitacoraPedido).where(BitacoraPedido.pedido_id == id)

    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()

    result = await db.execute(
        base.order_by(BitacoraPedido.created_at.desc(), BitacoraPedido.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    entradas = result.scalars().all()

    return {
        "items": [BitacoraPedidoResponse.model_validate(e) for e in entradas],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_pedido(
    body: PedidoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate cliente exists
    cliente_result = await db.execute(select(Cliente).where(Cliente.id == body.cliente_id))
    cliente = cliente_result.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )

    # Auto-generate numero_pedido
    max_result = await db.execute(
        select(func.max(Pedido.numero_pedido)).where(Pedido.numero_pedido.like("PED-%"))
    )
    max_numero = max_result.scalar_one()
    if max_numero:
        current_num = int(max_numero.replace("PED-", ""))
        next_num = current_num + 1
    else:
        next_num = 1
    numero_pedido = f"PED-{next_num:04d}"

    # Parse tipo_documento
    tipo_doc = None
    if body.tipo_documento:
        try:
            tipo_doc = TipoDocumento(body.tipo_documento)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Tipo documento inválido: {body.tipo_documento}")

    # Create pedido — defaults (armando, pendiente) come from model
    vendedor_id = body.vendedor_id if (body.vendedor_id and current_user.rol.value in ("admin", "super_admin")) else current_user.id
    vendedor_result = await db.execute(select(User).where(User.id == vendedor_id))
    vendedor = vendedor_result.scalar_one_or_none()
    if vendedor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendedor no encontrado",
        )
    pedido = Pedido(
        numero_pedido=numero_pedido,
        cliente_id=body.cliente_id,
        vendedor_id=vendedor_id,
        tipo_documento=tipo_doc,
        fecha=date.today(),
        fecha_entrega=body.fecha_entrega,
        transporte=body.transporte,
        fecha_compromiso_pago=body.fecha_compromiso_pago,
        despachado=body.despachado,
        sociedad=body.sociedad,
        observacion=body.observacion,
        direccion_entrega=cliente.domicilio,
        latitud=cliente.latitud,
        longitud=cliente.longitud,
        bultos=body.bultos,
        tipo_precio=body.tipo_precio,
        importe_total=Decimal("0"),
        saldo_pendiente=Decimal("0"),
    )

    db.add(pedido)
    await db.flush()

    grupo_id = nuevo_grupo_id()
    await registrar_evento(
        db,
        pedido=pedido,
        usuario=current_user,
        evento="creacion",
        accion="alta",
        entidad="pedido",
        grupo_id=grupo_id,
        observacion=f"Pedido creado para {cliente.nombre}",
    )

    # Create items - check for duplicates
    seen_products: set[int] = set()
    importe_total = Decimal("0")
    for item_data in body.items:
        if item_data.producto_id in seen_products:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Producto id {item_data.producto_id} duplicado en el pedido",
            )
        seen_products.add(item_data.producto_id)

        prod_result = await db.execute(
            select(Producto).where(Producto.id == item_data.producto_id).with_for_update()
        )
        producto = prod_result.scalar_one_or_none()
        if producto is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto con id {item_data.producto_id} no encontrado",
            )
        
        # Deduct stock based on society (Sanalle -> A, Farmacare -> B)
        # We assume if sociedad is None, it defaults to Farmacare or logic fallback
        es_sanalle = (body.sociedad and body.sociedad.lower() == "sanalle") or (tipo_doc == TipoDocumento.factura)
        
        # Handle generic 'cantidad' if provided
        cajas = item_data.cantidad if item_data.cantidad is not None and item_data.cantidad_cajas == 0 else item_data.cantidad_cajas
        blisters = item_data.cantidad_blisters

        if es_sanalle:
            producto.modify_stock_a(-cajas, -blisters)
            producto.modify_stock_a(cajas, blisters, is_reservation=True)
        else:
            producto.modify_stock_b(-cajas, -blisters)
            producto.modify_stock_b(cajas, blisters, is_reservation=True)

        comision = _comision_para(vendedor, producto)

        pedido_item = PedidoItem(
            pedido_id=pedido.id,
            producto_id=item_data.producto_id,
            cantidad_cajas=cajas,
            cantidad_blisters=blisters,
            precio_lista=Decimal(str(item_data.precio_lista)) if item_data.precio_lista is not None else None,
            descuento_porcentaje=Decimal(str(item_data.descuento_porcentaje)) if item_data.descuento_porcentaje is not None else None,
            precio_unitario=Decimal(str(item_data.precio_unitario)),
            precio_total=Decimal(str(item_data.precio_total)),
            comision_vendedor=comision,
        )
        db.add(pedido_item)
        importe_total += Decimal(str(item_data.precio_total))

        await registrar_evento(
            db,
            pedido=pedido,
            usuario=current_user,
            evento="creacion",
            accion="alta",
            entidad="item",
            despues=f"{cajas} caja(s) @ ${Decimal(str(item_data.precio_unitario)):.2f}",
            producto_id=producto.id,
            producto_nombre=producto.nombre,
            grupo_id=grupo_id,
        )

    pedido.importe_total = importe_total
    pedido.saldo_pendiente = importe_total

    # Auto-imputar pagos disponibles (créditos a favor del cliente)
    await imputar_pagos_a_pedido(db, pedido)

    await db.commit()

    # Reload with relationships
    query = select(Pedido).where(Pedido.id == pedido.id).options(*_load_options())
    result = await db.execute(query)
    pedido = result.scalar_one()

    return _build_pedido_response(pedido)


@router.put("/{id}")
async def update_pedido(
    id: int,
    body: PedidoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(Pedido)
        .where(Pedido.id == id)
        .options(selectinload(Pedido.items).selectinload(PedidoItem.producto))
        .with_for_update()
    )
    result = await db.execute(query)
    pedido = result.scalar_one_or_none()
    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pedido no encontrado",
        )

    is_admin = current_user.rol.value in ("admin", "super_admin")
    if body.vendedor_id is not None and not is_admin and body.vendedor_id != pedido.vendedor_id:
        raise HTTPException(status_code=403, detail="Solo admin puede cambiar el vendedor")

    if body.items is not None and not is_admin:
        if pedido.shipping_status not in (EstadoDespacho.pendiente, EstadoDespacho.en_preparacion):
            raise HTTPException(status_code=403, detail="Solo admin puede editar items en este estado")

    # Bitácora: hay que fotografiar el estado ANTES de tocar nada. Los items se borran
    # y se recrean más abajo, así que después ya no habría con qué comparar.
    grupo_id = nuevo_grupo_id()
    estado_previo = snapshot_pedido(pedido)
    items_previos = snapshot_items(pedido.items)

    # Update scalar fields
    update_data = body.model_dump(exclude_unset=True, exclude={"items"})
    if "shipping_status" in update_data and update_data["shipping_status"] is not None:
        try:
            update_data["shipping_status"] = EstadoDespacho(update_data["shipping_status"])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"shipping_status inválido: {update_data['shipping_status']}",
            )
    if "payment_status" in update_data and update_data["payment_status"] is not None:
        try:
            update_data["payment_status"] = EstadoPagoPedido(update_data["payment_status"])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"payment_status inválido: {update_data['payment_status']}",
            )
    if "tipo_documento" in update_data and update_data["tipo_documento"] is not None:
        try:
            update_data["tipo_documento"] = TipoDocumento(update_data["tipo_documento"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Tipo documento inválido")

    for field, value in update_data.items():
        setattr(pedido, field, value)

    # Replace items if provided
    if body.items is not None:
        # Revert stock for existing items before removing them
        for existing_item in pedido.items:
            prod_result = await db.execute(
                select(Producto).where(Producto.id == existing_item.producto_id).with_for_update()
            )
            producto = prod_result.scalar_one_or_none()
            if producto:
                es_sanalle = (pedido.sociedad and pedido.sociedad.lower() == "sanalle") or (pedido.tipo_documento == TipoDocumento.factura)
                if es_sanalle:
                    producto.modify_stock_a(existing_item.cantidad_cajas, existing_item.cantidad_blisters)
                    producto.modify_stock_a(-existing_item.cantidad_cajas, -existing_item.cantidad_blisters, is_reservation=True)
                else:
                    producto.modify_stock_b(existing_item.cantidad_cajas, existing_item.cantidad_blisters)
                    producto.modify_stock_b(-existing_item.cantidad_cajas, -existing_item.cantidad_blisters, is_reservation=True)
            await db.delete(existing_item)
        await db.flush()

        # Fetch vendedor for commission calculation
        vendedor_result = await db.execute(select(User).where(User.id == pedido.vendedor_id))
        vendedor = vendedor_result.scalar_one_or_none()

        importe_total = Decimal("0")
        for item_data in body.items:
            prod_result = await db.execute(
                select(Producto).where(Producto.id == item_data.producto_id).with_for_update()
            )
            producto = prod_result.scalar_one_or_none()
            if producto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Producto con id {item_data.producto_id} no encontrado",
                )
            
            es_sanalle = (pedido.sociedad and pedido.sociedad.lower() == "sanalle") or (pedido.tipo_documento == TipoDocumento.factura)
            
            # Handle generic 'cantidad' if provided
            cajas = item_data.cantidad if item_data.cantidad is not None and item_data.cantidad_cajas == 0 else item_data.cantidad_cajas
            blisters = item_data.cantidad_blisters

            if es_sanalle:
                producto.modify_stock_a(-cajas, -blisters)
                producto.modify_stock_a(cajas, blisters, is_reservation=True)
            else:
                producto.modify_stock_b(-cajas, -blisters)
                producto.modify_stock_b(cajas, blisters, is_reservation=True)

            comision = _comision_para(vendedor, producto)

            pedido_item = PedidoItem(
                pedido_id=pedido.id,
                producto_id=item_data.producto_id,
                cantidad_cajas=cajas,
                cantidad_blisters=blisters,
                precio_lista=Decimal(str(item_data.precio_lista)) if item_data.precio_lista is not None else None,
                descuento_porcentaje=Decimal(str(item_data.descuento_porcentaje)) if item_data.descuento_porcentaje is not None else None,
                precio_unitario=Decimal(str(item_data.precio_unitario)),
                precio_total=Decimal(str(item_data.precio_total)),
                comision_vendedor=comision,
            )
            db.add(pedido_item)
            importe_total += Decimal(str(item_data.precio_total))

        pedido.importe_total = importe_total
        sum_imputations_result = await db.execute(
            select(func.coalesce(func.sum(PagoImputacion.monto), 0)).where(PagoImputacion.pedido_id == id)
        )
        total_imputado = sum_imputations_result.scalar_one()
        pedido.saldo_pendiente = pedido.importe_total - total_imputado

        # Auto-imputar pagos disponibles si hay saldo pendiente tras la actualización
        await imputar_pagos_a_pedido(db, pedido)

    # Bitácora: se compara contra las fotos tomadas al principio. Hace falta el flush
    # para que los items recién creados existan en la sesión antes de releerlos.
    await db.flush()
    await registrar_cambios_pedido(
        db,
        pedido=pedido,
        antes=estado_previo,
        usuario=current_user,
        grupo_id=grupo_id,
    )
    if body.items is not None:
        items_result = await db.execute(
            select(PedidoItem)
            .where(PedidoItem.pedido_id == pedido.id)
            .options(selectinload(PedidoItem.producto))
        )
        await registrar_diff_items(
            db,
            pedido=pedido,
            antes=items_previos,
            despues=snapshot_items(items_result.scalars().all()),
            usuario=current_user,
            grupo_id=grupo_id,
        )

    await db.commit()

    reload_query = select(Pedido).where(Pedido.id == pedido.id).options(*_load_options())
    result = await db.execute(reload_query)
    pedido = result.scalar_one()

    return _build_pedido_response(pedido)


@router.patch("/{id}/shipping-status")
async def update_shipping_status(
    id: int,
    body: PedidoShippingStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(Pedido)
        .where(Pedido.id == id)
        .options(selectinload(Pedido.items).selectinload(PedidoItem.producto))
        .with_for_update()
    )
    result = await db.execute(query)
    pedido = result.scalar_one_or_none()
    if pedido is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")

    try:
        nuevo_shipping = EstadoDespacho(body.shipping_status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"shipping_status inválido: {body.shipping_status}. Válidos: {[e.value for e in EstadoDespacho]}",
        )

    valid = SHIPPING_TRANSITIONS.get(pedido.shipping_status.value, [])
    if nuevo_shipping.value not in valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transición no permitida de '{pedido.shipping_status.value}' a '{nuevo_shipping.value}'. Válidos: {valid}",
        )

    # Stock adjustments on shipping change
    if nuevo_shipping == EstadoDespacho.entregado:
        for item in pedido.items:
            prod_result = await db.execute(
                select(Producto).where(Producto.id == item.producto_id).with_for_update()
            )
            producto = prod_result.scalar_one_or_none()
            if producto:
                es_sanalle = (pedido.sociedad and pedido.sociedad.lower() == "sanalle") or (pedido.tipo_documento == TipoDocumento.factura)
                if es_sanalle:
                    producto.modify_stock_a(-item.cantidad_cajas, -item.cantidad_blisters, is_reservation=True)
                else:
                    producto.modify_stock_b(-item.cantidad_cajas, -item.cantidad_blisters, is_reservation=True)

    elif nuevo_shipping == EstadoDespacho.cancelado:
        for item in pedido.items:
            prod_result = await db.execute(
                select(Producto).where(Producto.id == item.producto_id).with_for_update()
            )
            producto = prod_result.scalar_one_or_none()
            if producto:
                es_sanalle = (pedido.sociedad and pedido.sociedad.lower() == "sanalle") or (pedido.tipo_documento == TipoDocumento.factura)
                if es_sanalle:
                    producto.modify_stock_a(item.cantidad_cajas, item.cantidad_blisters)
                    producto.modify_stock_a(-item.cantidad_cajas, -item.cantidad_blisters, is_reservation=True)
                else:
                    producto.modify_stock_b(item.cantidad_cajas, item.cantidad_blisters)
                    producto.modify_stock_b(-item.cantidad_cajas, -item.cantidad_blisters, is_reservation=True)

    estado_anterior = pedido.shipping_status
    pedido.shipping_status = nuevo_shipping

    await registrar_evento(
        db,
        pedido=pedido,
        usuario=current_user,
        evento="cambio_estado_despacho",
        accion="modificacion",
        entidad="pedido",
        campo="shipping_status",
        antes=estado_anterior,
        despues=nuevo_shipping,
        grupo_id=nuevo_grupo_id(),
    )

    await db.commit()

    reload_query = select(Pedido).where(Pedido.id == pedido.id).options(*_load_options())
    result = await db.execute(reload_query)
    pedido = result.scalar_one()

    return _build_pedido_response(pedido)


@router.patch("/{id}/payment-status")
async def update_payment_status(
    id: int,
    body: PedidoPaymentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Pedido).where(Pedido.id == id).with_for_update()
    result = await db.execute(query)
    pedido = result.scalar_one_or_none()
    if pedido is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")

    try:
        nuevo_payment = EstadoPagoPedido(body.payment_status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"payment_status inválido: {body.payment_status}. Válidos: {[e.value for e in EstadoPagoPedido]}",
        )

    valid = PAYMENT_TRANSITIONS.get(pedido.payment_status.value, [])
    if nuevo_payment.value not in valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transición no permitida de '{pedido.payment_status.value}' a '{nuevo_payment.value}'. Válidos: {valid}",
        )

    estado_anterior = pedido.payment_status
    pedido.payment_status = nuevo_payment

    await registrar_evento(
        db,
        pedido=pedido,
        usuario=current_user,
        evento="cambio_estado_pago",
        accion="modificacion",
        entidad="pedido",
        campo="payment_status",
        antes=estado_anterior,
        despues=nuevo_payment,
        grupo_id=nuevo_grupo_id(),
    )

    await db.commit()

    reload_query = select(Pedido).where(Pedido.id == pedido.id).options(*_load_options())
    result = await db.execute(reload_query)
    pedido = result.scalar_one()

    return _build_pedido_response(pedido)


@router.patch("/{id}/items/{producto_id}/comision")
async def update_item_comision(
    id: int,
    producto_id: int,
    body: PedidoItemComisionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["super_admin", "admin"])),
):
    """
    Updates the specific commission percentage applied to a PedidoItem.
    """
    # Fetch the pedido first to ensure it exists
    pedido_result = await db.execute(select(Pedido).where(Pedido.id == id))
    pedido = pedido_result.scalar_one_or_none()
    if pedido is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")

    # Fetch and update the item
    query = (
        select(PedidoItem)
        .where(
            PedidoItem.pedido_id == id,
            PedidoItem.producto_id == producto_id,
        )
        .options(selectinload(PedidoItem.producto))
        .with_for_update()
    )

    result = await db.execute(query)
    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item del pedido no encontrado")

    comision_anterior = item.comision_vendedor
    item.comision_vendedor = Decimal(str(body.comision_porcentaje))

    await registrar_evento(
        db,
        pedido=pedido,
        usuario=current_user,
        evento="comision_item",
        accion="modificacion",
        entidad="item",
        campo="comision_vendedor",
        antes=comision_anterior,
        despues=item.comision_vendedor,
        producto_id=producto_id,
        producto_nombre=item.producto.nombre if item.producto else None,
        grupo_id=nuevo_grupo_id(),
    )

    await db.commit()

    return {"message": "Comisión actualizada correctamente", "comision_porcentaje": float(item.comision_vendedor)}


@router.post("/asignar-repartidor")
async def asignar_repartidor(
    body: AsignarRepartidorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Bulk assign repartidor to multiple pedidos."""
    rep_result = await db.execute(select(User).where(User.id == body.repartidor_id))
    repartidor = rep_result.scalar_one_or_none()
    if not repartidor:
        raise HTTPException(status_code=404, detail="Repartidor no encontrado")

    grupo_id = nuevo_grupo_id()
    updated = 0
    for pid in body.pedido_ids:
        result = await db.execute(select(Pedido).where(Pedido.id == pid))
        pedido = result.scalar_one_or_none()
        if pedido:
            anterior = pedido.repartidor_id
            pedido.repartidor_id = body.repartidor_id
            if anterior != body.repartidor_id:
                await registrar_evento(
                    db,
                    pedido=pedido,
                    usuario=current_user,
                    evento="asignacion_repartidor",
                    accion="modificacion",
                    entidad="pedido",
                    campo="repartidor_id",
                    antes=anterior,
                    despues=body.repartidor_id,
                    grupo_id=grupo_id,
                    observacion=f"Repartidor: {repartidor.nombre_completo}",
                )
            updated += 1

    await db.commit()
    return {"message": f"{updated} pedidos actualizados", "updated": updated}


@router.get("/{id}/pdf")
async def get_pedido_pdf(
    id: int,
    sin_valores: bool = Query(False, description="Generar PDF con todos los valores en 0"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = (
        select(Pedido)
        .where(Pedido.id == id)
        .options(
            selectinload(Pedido.cliente).selectinload(Cliente.localidad_rel),
            selectinload(Pedido.vendedor),
            selectinload(Pedido.items).selectinload(PedidoItem.producto),
        )
    )
    result = await db.execute(query)
    pedido = result.scalar_one_or_none()
    if pedido is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")

    pedido_data = {
        "numero_pedido": pedido.numero_pedido,
        "fecha": str(pedido.fecha),
        "fecha_entrega": str(pedido.fecha_entrega) if pedido.fecha_entrega else None,
        "shipping_status": pedido.shipping_status.value,
        "payment_status": pedido.payment_status.value,
        "transporte": pedido.transporte,
        "sociedad": pedido.sociedad,
        "importe_total": 0.0 if sin_valores else float(pedido.importe_total),
        "observacion": pedido.observacion,
        "tipo_documento": pedido.tipo_documento.value if pedido.tipo_documento else "remito",
    }
    cliente_data = {
        "nombre": pedido.cliente.nombre if pedido.cliente else "",
        "cuit": pedido.cliente.cuit if pedido.cliente else "-",
        "domicilio": pedido.cliente.domicilio if pedido.cliente else "",
        "localidad": pedido.cliente.localidad_rel.nombre if pedido.cliente and pedido.cliente.localidad_rel else "",
    }
    vendedor_nombre = pedido.vendedor.nombre_completo if pedido.vendedor else ""
    items = [
        {
            "producto_nombre": item.producto.nombre if item.producto else f"Producto #{item.producto_id}",
            "cantidad": item.cantidad,
            "precio_unitario": 0.0 if sin_valores else float(item.precio_unitario),
            "precio_total": 0.0 if sin_valores else float(item.precio_total),
            "descuento_porcentaje": float(item.descuento_porcentaje) if item.descuento_porcentaje else None,
        }
        for item in pedido.items
    ]

    filename = generate_pedido_pdf(pedido_data, cliente_data, vendedor_nombre, items)
    full_path = os.path.join(settings.PDF_STORAGE_PATH, filename)

    return FileResponse(
        path=full_path,
        media_type="application/pdf",
        filename=filename,
    )


@router.delete("/{id}")
async def delete_pedido(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Pedido)
        .where(Pedido.id == id)
        .options(selectinload(Pedido.items).selectinload(PedidoItem.producto))
        .with_for_update()
    )
    pedido = result.scalar_one_or_none()
    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pedido no encontrado",
        )

    if pedido.shipping_status not in (EstadoDespacho.pendiente, EstadoDespacho.en_preparacion):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden eliminar pedidos en estado Pendiente o En Preparación",
        )

    # El borrador que se creó y se canceló sin tocar nada no deja rastro. Cualquier
    # pedido con historia real deja el registro de su eliminación, que sobrevive al
    # borrado porque bitacora_pedidos no tiene FK a pedidos.
    if not await bitacora_service.limpiar_borrador(db, pedido.id):
        await registrar_evento(
            db,
            pedido=pedido,
            usuario=current_user,
            evento="eliminacion",
            accion="baja",
            entidad="pedido",
            antes=f"{len(pedido.items)} item(s) · total ${pedido.importe_total:.2f}",
            grupo_id=nuevo_grupo_id(),
            observacion="Pedido eliminado. Se restauró el stock.",
        )
    await db.flush()

    for item in pedido.items:
        prod_result = await db.execute(
            select(Producto).where(Producto.id == item.producto_id).with_for_update()
        )
        producto = prod_result.scalar_one_or_none()
        if producto:
            es_sanalle = (pedido.sociedad and pedido.sociedad.lower() == "sanalle") or (pedido.tipo_documento == TipoDocumento.factura)
            if es_sanalle:
                producto.modify_stock_a(item.cantidad_cajas, item.cantidad_blisters)
                producto.modify_stock_a(-item.cantidad_cajas, -item.cantidad_blisters, is_reservation=True)
            else:
                producto.modify_stock_b(item.cantidad_cajas, item.cantidad_blisters)
                producto.modify_stock_b(-item.cantidad_cajas, -item.cantidad_blisters, is_reservation=True)

    await db.delete(pedido)
    await db.commit()
    return {"message": f"Pedido {pedido.numero_pedido} eliminado correctamente"}
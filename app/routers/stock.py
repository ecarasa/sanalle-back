"""Operaciones de stock: ajustes con motivo, mínimos y toma de inventario.

Router propio y no dentro de `productos.py` por dos razones: ese archivo ya pasa
las mil líneas, y sus rutas `/{id}` se comen cualquier path nuevo que se agregue
después.
"""

import io
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.deposito import Deposito
from app.models.producto import Producto
from app.models.user import User
from app.schemas.producto import ProductoResponse
from app.models.toma_inventario import TomaInventario
from app.schemas.stock import (
    MOTIVOS_AJUSTE,
    MOTIVOS_LABEL,
    AjusteStockRequest,
    MinimosBulkRequest,
    MinimosMasivoRequest,
    MotivoAjusteResponse,
    TomaAplicarRequest,
    TomaConteoRequest,
    TomaInventarioCreate,
)
from app.services import ajuste_stock_service, stock_service, toma_inventario_service
from app.utils.deps import (
    ROLES_MAESTRO_PRODUCTOS,
    ROLES_STOCK,
    get_current_user,
    require_role,
)

router = APIRouter()


@router.get("/motivos-ajuste", response_model=list[MotivoAjusteResponse])
async def list_motivos_ajuste(_current_user: User = Depends(get_current_user)):
    """Catálogo de motivos, para que el front no hardcodee las etiquetas."""
    return MOTIVOS_AJUSTE


@router.post("/ajustes")
async def crear_ajuste(
    body: AjusteStockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(ROLES_STOCK)),
):
    """Corrige el stock de un producto en un depósito, con motivo obligatorio."""
    producto = (
        await db.execute(select(Producto).where(Producto.id == body.producto_id).with_for_update())
    ).scalar_one_or_none()
    if producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    deposito = await stock_service.validar_deposito(db, body.deposito_id)

    _, movimiento = await ajuste_stock_service.registrar_ajuste(
        db,
        producto=producto,
        deposito_id=deposito.id,
        cajas=body.cantidad_cajas,
        blisters=body.cantidad_blisters,
        modo=body.modo,
        motivo=body.motivo,
        usuario_id=current_user.id,
        observacion=body.observacion,
    )
    await db.commit()
    await db.refresh(producto)

    from app.routers.productos import _producto_to_response

    return {
        "producto": _producto_to_response(producto),
        "movimiento_id": movimiento.id if movimiento else None,
        "sin_cambio": movimiento is None,
    }


# --- Mínimos de reposición ----------------------------------------------------
# Son dato de maestro y no de depósito: van con rol más estricto que los ajustes.


@router.post("/minimos-bulk")
async def actualizar_minimos_bulk(
    body: MinimosBulkRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(ROLES_MAESTRO_PRODUCTOS)),
):
    """Fija el mínimo de una lista de productos (edición inline de la grilla)."""
    actualizados = 0
    for item in body.items:
        res = await db.execute(
            update(Producto)
            .where(Producto.id == item.producto_id)
            .values(
                stock_minimo_cajas=item.stock_minimo_cajas,
                stock_minimo_blisters=item.stock_minimo_blisters,
            )
        )
        actualizados += res.rowcount or 0
    await db.commit()
    return {"updated": actualizados}


@router.post("/minimos-masivo")
async def actualizar_minimos_masivo(
    body: MinimosMasivoRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(ROLES_MAESTRO_PRODUCTOS)),
):
    """Pone el mismo mínimo a todo un laboratorio, proveedor o categoría."""
    filtros = [Producto.activo.is_(True)]
    if body.laboratorio_id:
        filtros.append(Producto.laboratorio_id == body.laboratorio_id)
    if body.proveedor_id:
        filtros.append(Producto.proveedor_id == body.proveedor_id)
    if body.categoria:
        filtros.append(Producto.categoria_producto.ilike(body.categoria))
    if body.producto_ids:
        filtros.append(Producto.id.in_(body.producto_ids))
    if body.solo_si_cero:
        filtros.append(
            and_(
                func.coalesce(Producto.stock_minimo_cajas, 0) == 0,
                func.coalesce(Producto.stock_minimo_blisters, 0) == 0,
            )
        )

    res = await db.execute(
        update(Producto)
        .where(and_(*filtros))
        .values(
            stock_minimo_cajas=body.valor_cajas,
            stock_minimo_blisters=body.valor_blisters,
        )
    )
    await db.commit()
    return {"updated": res.rowcount or 0}


# --- Toma de inventario -------------------------------------------------------


def _toma_response(toma: TomaInventario, resumen: dict | None = None) -> dict:
    return {
        "id": toma.id,
        "numero": toma.numero,
        "deposito_id": toma.deposito_id,
        "deposito_nombre": toma.deposito.nombre if toma.deposito else None,
        "estado": toma.estado,
        "origen": toma.origen,
        "fecha": toma.fecha,
        "observacion": toma.observacion,
        "creado_por_nombre": toma.creado_por.username if toma.creado_por else None,
        "aplicado_por_nombre": toma.aplicado_por.username if toma.aplicado_por else None,
        "aplicada_at": toma.aplicada_at,
        "created_at": toma.created_at,
        "resumen": resumen,
    }


async def _toma_o_404(db: AsyncSession, toma_id: int) -> TomaInventario:
    toma = (
        await db.execute(select(TomaInventario).where(TomaInventario.id == toma_id))
    ).scalar_one_or_none()
    if toma is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toma no encontrada")
    return toma


@router.post("/inventarios", status_code=status.HTTP_201_CREATED)
async def abrir_inventario(
    body: TomaInventarioCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(ROLES_STOCK)),
):
    """Abre un recuento físico de un depósito y congela lo que el sistema cree tener."""
    filtro = body.filtro
    toma, total = await toma_inventario_service.abrir(
        db,
        deposito_id=body.deposito_id,
        usuario_id=current_user.id,
        fecha=body.fecha,
        observacion=body.observacion,
        laboratorio_id=filtro.laboratorio_id if filtro else None,
        categoria=filtro.categoria if filtro else None,
        solo_con_stock=filtro.solo_con_stock if filtro else False,
    )
    await db.commit()
    await db.refresh(toma)
    return {**_toma_response(toma), "total_lineas": total}


@router.get("/inventarios")
async def list_inventarios(
    estado: str | None = Query(None),
    deposito_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = select(TomaInventario).order_by(TomaInventario.id.desc())
    if estado:
        query = query.where(TomaInventario.estado == estado)
    if deposito_id:
        query = query.where(TomaInventario.deposito_id == deposito_id)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    filas = (
        await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return {
        "items": [_toma_response(t) for t in filas],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/inventarios/{toma_id}")
async def get_inventario(
    toma_id: int,
    search: str = Query(""),
    solo_con_diferencia: bool = Query(False),
    solo_sin_contar: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    toma = await _toma_o_404(db, toma_id)
    lineas = await toma_inventario_service._lineas_con_actual(db, toma)

    items = []
    for item, producto, fila in lineas:
        por_caja = producto.get_blisters_por_caja
        contado_bl, actual_bl, movido = toma_inventario_service._diferencia(item, producto, fila)
        if search and search.lower() not in f"{producto.nombre} {producto.codigo}".lower():
            continue
        if solo_sin_contar and contado_bl is not None:
            continue
        if solo_con_diferencia and (contado_bl is None or contado_bl == actual_bl):
            continue
        # En una toma ya aplicada la diferencia es la que se aplicó, congelada.
        # Recalcularla contra el stock de hoy mostraría un número que no fue.
        aplicada = toma.estado == "aplicada"
        diferencia = (
            item.aplicado_delta_blisters
            if aplicada
            else (None if contado_bl is None else contado_bl - actual_bl)
        )
        items.append({
            "producto_id": producto.id,
            "producto_codigo": producto.codigo,
            "producto_nombre": producto.nombre,
            "blisters_por_caja": por_caja,
            "esperado_cajas": item.esperado_cajas,
            "esperado_blisters": item.esperado_blisters,
            "contado_cajas": item.contado_cajas,
            "contado_blisters": item.contado_blisters,
            "actual_cajas": fila.cajas if fila else 0,
            "actual_blisters": fila.blisters if fila else 0,
            "reservado_cajas": fila.reservado_cajas if fila else 0,
            "diferencia_blisters": diferencia,
            "movido_durante_conteo": movido and not aplicada,
        })

    total = len(items)
    desde = (page - 1) * page_size
    return {
        **_toma_response(toma, await toma_inventario_service.resumen(db, toma, lineas)),
        "items": items[desde:desde + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.put("/inventarios/{toma_id}/lineas")
async def guardar_conteo(
    toma_id: int,
    body: TomaConteoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(ROLES_STOCK)),
):
    """Autosave de la planilla de conteo."""
    toma = await _toma_o_404(db, toma_id)
    guardadas = await toma_inventario_service.guardar_conteo(
        db, toma=toma, items=body.items, usuario_id=current_user.id
    )
    await db.commit()
    return {"guardadas": guardadas}


@router.post("/inventarios/{toma_id}/aplicar")
async def aplicar_inventario(
    toma_id: int,
    body: TomaAplicarRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(ROLES_STOCK)),
):
    """Aplica todas las diferencias juntas. Todo o nada."""
    toma = (
        await db.execute(
            select(TomaInventario).where(TomaInventario.id == toma_id).with_for_update()
        )
    ).scalar_one_or_none()
    if toma is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toma no encontrada")

    resultado = await toma_inventario_service.aplicar(
        db,
        toma=toma,
        usuario_id=current_user.id,
        observacion=body.observacion,
        confirmar_movidas=body.confirmar_movidas,
    )
    await db.commit()
    return resultado


@router.delete("/inventarios/{toma_id}")
async def anular_inventario(
    toma_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(ROLES_STOCK)),
):
    toma = await _toma_o_404(db, toma_id)
    if toma.estado != "borrador":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La toma {toma.numero} ya está {toma.estado}: no se puede anular.",
        )
    toma.estado = "anulada"
    await db.commit()
    return {"estado": toma.estado}


# --- Carga masiva por planilla ------------------------------------------------
# Endpoint propio y no el import de productos: ese crea y actualiza el maestro
# (precios y márgenes incluidos), y cargar inventario no debería poder pisar
# datos comerciales. Además el formato es distinto: acá una fila es
# producto + depósito + cantidad, que es lo que sale de una planilla de conteo.


def _hoja_de(contents: bytes):
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
    ws = wb.active
    encabezado = [
        str(c.value).strip().lower() if c.value else ""
        for c in next(ws.iter_rows(min_row=1, max_row=1))
    ]
    return ws, {nombre: idx for idx, nombre in enumerate(encabezado)}


def _planilla(nombre_hoja: str, encabezados: list[str], filas: list[list]) -> StreamingResponse:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = nombre_hoja
    ws.append(encabezados)
    azul = PatternFill(start_color="003087", end_color="003087", fill_type="solid")
    for celda in ws[1]:
        celda.fill = azul
        celda.font = Font(color="FFFFFF", bold=True)
        celda.alignment = Alignment(horizontal="center")
    for fila in filas:
        ws.append(fila)
    for i, encabezado in enumerate(encabezados, 1):
        ws.column_dimensions[chr(64 + i) if i <= 26 else "A"].width = max(14, len(encabezado) + 4)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_hoja}.xlsx"'},
    )


@router.get("/import-template")
async def stock_import_template(
    deposito_id: int | None = Query(None, description="Precarga el catálogo de ese depósito"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(ROLES_STOCK)),
):
    """Planilla de carga de stock: Código | Depósito | Cajas | Blísters."""
    filas: list[list] = []
    if deposito_id:
        deposito = await stock_service.validar_deposito(db, deposito_id)
        productos = (
            await db.execute(
                select(Producto.codigo, Producto.nombre)
                .where(Producto.activo.is_(True))
                .order_by(Producto.codigo)
            )
        ).all()
        filas = [[codigo, deposito.nombre, nombre, 0, 0] for codigo, nombre in productos]
    return _planilla(
        "Stock",
        ["Código", "Depósito", "Producto (referencia)", "Cajas", "Blísters"],
        filas,
    )


@router.post("/import-excel")
async def stock_import_excel(
    file: UploadFile = File(...),
    motivo: str = Form("carga_inicial"),
    modo: str = Form("absoluto"),
    observacion: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(ROLES_STOCK)),
):
    """Carga stock desde una planilla, dejando un movimiento por fila.

    Valida todas las filas antes de tocar nada: con una sola fila mala no se
    aplica ninguna, así el operario corrige la planilla y la vuelve a subir sin
    quedar con media carga hecha.
    """
    if motivo not in MOTIVOS_LABEL:
        raise HTTPException(status_code=400, detail=f"Motivo inválido: {motivo!r}")
    if modo not in ("absoluto", "delta"):
        raise HTTPException(status_code=400, detail="El modo tiene que ser 'absoluto' o 'delta'")
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="El archivo debe ser XLSX")

    ws, col = _hoja_de(await file.read())
    requeridas = ["código", "depósito", "cajas"]
    faltan = [c for c in requeridas if c not in col]
    if faltan:
        raise HTTPException(
            status_code=400, detail=f"Columnas requeridas faltantes: {', '.join(faltan)}"
        )

    productos = {
        (codigo or "").strip().lower(): pid
        for pid, codigo in (await db.execute(select(Producto.id, Producto.codigo))).all()
    }
    depositos = {
        (nombre or "").strip().lower(): did
        for did, nombre in (await db.execute(select(Deposito.id, Deposito.nombre))).all()
    }

    def _celda(fila: tuple, nombre: str):
        idx = col.get(nombre)
        if idx is None or idx >= len(fila):
            return None
        valor = fila[idx]
        return valor if valor != "" else None

    # Primera pasada: validar. Nada se escribe hasta que la planilla esté limpia.
    pendientes: list[tuple[int, int, int, int]] = []
    errores: list[str] = []
    for nro, fila in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        if not fila or all(v is None or v == "" for v in fila):
            continue
        codigo = str(_celda(fila, "código") or "").strip()
        deposito_nombre = str(_celda(fila, "depósito") or "").strip()
        producto_id = productos.get(codigo.lower())
        deposito_id = depositos.get(deposito_nombre.lower())
        if not producto_id:
            errores.append(f"Fila {nro}: no existe el producto con código {codigo!r}")
            continue
        if not deposito_id:
            errores.append(f"Fila {nro}: no existe el depósito {deposito_nombre!r}")
            continue
        try:
            cajas = int(_celda(fila, "cajas") or 0)
            blisters = int(_celda(fila, "blísters") or _celda(fila, "blisters") or 0)
        except (ValueError, TypeError):
            errores.append(f"Fila {nro}: las cantidades tienen que ser números enteros")
            continue
        if modo == "absoluto" and (cajas < 0 or blisters < 0):
            errores.append(f"Fila {nro}: en modo absoluto las cantidades no pueden ser negativas")
            continue
        pendientes.append((nro, producto_id, deposito_id, cajas, blisters))

    if errores:
        return {"aplicados": 0, "sin_cambio": 0, "errors": errores[:20], "total_errores": len(errores)}

    aplicados = 0
    sin_cambio = 0
    detalle = (observacion or f"Carga por planilla: {file.filename}")[:200]
    # Orden determinístico de bloqueo, para no trabarse contra una venta que esté
    # tocando los mismos productos en otro orden.
    for _, producto_id, deposito_id, cajas, blisters in sorted(pendientes, key=lambda x: x[1]):
        producto = (
            await db.execute(select(Producto).where(Producto.id == producto_id).with_for_update())
        ).scalar_one()
        _, movimiento = await ajuste_stock_service.registrar_ajuste(
            db,
            producto=producto,
            deposito_id=deposito_id,
            cajas=cajas,
            blisters=blisters,
            modo=modo,
            motivo=motivo,
            usuario_id=current_user.id,
            observacion=detalle,
        )
        if movimiento is None:
            sin_cambio += 1
        else:
            aplicados += 1

    await db.commit()
    return {"aplicados": aplicados, "sin_cambio": sin_cambio, "errors": [], "total_errores": 0}


@router.get("/minimos-excel")
async def minimos_excel(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(ROLES_MAESTRO_PRODUCTOS)),
):
    """Baja el mínimo actual de cada producto para editarlo y volver a subirlo."""
    filas = (
        await db.execute(
            select(
                Producto.id,
                Producto.codigo,
                Producto.nombre,
                Producto.stock_minimo_cajas,
                Producto.stock_minimo_blisters,
            )
            .where(Producto.activo.is_(True))
            .order_by(Producto.codigo)
        )
    ).all()
    return _planilla(
        "Minimos",
        ["ID", "Código", "Nombre", "Mínimo cajas", "Mínimo blísters"],
        [[pid, cod, nom, mc or 0, mb or 0] for pid, cod, nom, mc, mb in filas],
    )


@router.post("/minimos-excel")
async def importar_minimos_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(ROLES_MAESTRO_PRODUCTOS)),
):
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="El archivo debe ser XLSX")

    ws, col = _hoja_de(await file.read())
    if "código" not in col:
        raise HTTPException(status_code=400, detail="Falta la columna 'Código'")

    productos = {
        (codigo or "").strip().lower(): pid
        for pid, codigo in (await db.execute(select(Producto.id, Producto.codigo))).all()
    }

    def _celda(fila: tuple, nombre: str):
        idx = col.get(nombre)
        if idx is None or idx >= len(fila):
            return None
        return fila[idx]

    actualizados = 0
    errores: list[str] = []
    for nro, fila in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        if not fila or all(v is None or v == "" for v in fila):
            continue
        codigo = str(_celda(fila, "código") or "").strip()
        producto_id = productos.get(codigo.lower())
        if not producto_id:
            errores.append(f"Fila {nro}: no existe el producto con código {codigo!r}")
            continue
        try:
            cajas = int(_celda(fila, "mínimo cajas") or 0)
            blisters = int(_celda(fila, "mínimo blísters") or 0)
            if cajas < 0 or blisters < 0:
                raise ValueError
        except (ValueError, TypeError):
            errores.append(f"Fila {nro}: los mínimos tienen que ser enteros >= 0")
            continue
        res = await db.execute(
            update(Producto)
            .where(Producto.id == producto_id)
            .values(stock_minimo_cajas=cajas, stock_minimo_blisters=blisters)
        )
        actualizados += res.rowcount or 0

    await db.commit()
    return {"updated": actualizados, "errors": errores[:20], "total_errores": len(errores)}

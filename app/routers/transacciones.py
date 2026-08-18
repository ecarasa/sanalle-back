"""Vista unificada de TRANSACCIONES de dinero (solo lectura).

Agrega en una sola lista los movimientos de plata que hoy viven en tablas
separadas (cobros de cliente, pagos a proveedor, notas de crédito/débito de
cliente y de proveedor), cada uno con su contraparte (cliente/proveedor) y sus
LINKS a los documentos asociados (pedido / compra), para navegar entre sí.

No crea tablas nuevas: computa sobre lo existente, siguiendo el patrón de
cuenta_corriente.py. Reusa las imputaciones existentes:
- pago_imputaciones (cobro ↔ pedido)
- pago_proveedor_imputaciones (pago a proveedor ↔ compra)
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete as sa_delete, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.cliente import Cliente
from app.models.proveedor import Proveedor
from app.models.pedido import Pedido
from app.models.ingreso_mercaderia import IngresoMercaderia
from app.models.pago import Pago
from app.models.pago_imputacion import PagoImputacion
from app.models.pago_proveedor import PagoProveedor, PagoProveedorImputacion
from app.models.nota_credito_debito import NotaCreditoDebito, NotaCreditoItem, TipoNota
from app.models.notas_proveedor import NotaProveedor
from app.models.user import User
from app.utils.deps import require_role

router = APIRouter()

TIPOS_VALIDOS = {"cobro", "pago_proveedor", "nota_credito", "nota_debito", "nota_proveedor"}


async def _nombres(db: AsyncSession, modelo, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    campo = "nombre"
    rows = (await db.execute(select(modelo.id, getattr(modelo, campo)).where(modelo.id.in_(ids)))).all()
    return {r[0]: r[1] for r in rows}


@router.get("")
async def listar_transacciones(
    fecha_desde: date | None = Query(None),
    fecha_hasta: date | None = Query(None),
    tipo: str | None = Query(None, description="cobro|pago_proveedor|nota_credito|nota_debito|nota_proveedor"),
    search: str = Query("", description="Filtra por nombre de cliente/proveedor"),
    cuenta_id: int | None = Query(None, description="Filtra por cuenta de dinero (caja/banco)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    tipos = {tipo} if tipo in TIPOS_VALIDOS else TIPOS_VALIDOS
    # Las notas de crédito/débito no están ligadas a una cuenta de dinero puntual.
    if cuenta_id is not None:
        tipos = tipos & {"cobro", "pago_proveedor"}
    trans: list[dict] = []

    # ---- Cobros de cliente (Pago) ----
    if "cobro" in tipos:
        q = select(Pago)
        if fecha_desde:
            q = q.where(Pago.fecha_recepcion >= fecha_desde)
        if fecha_hasta:
            q = q.where(Pago.fecha_recepcion <= fecha_hasta)
        if cuenta_id is not None:
            q = q.where(Pago.cuenta_id == cuenta_id)
        pagos = (await db.execute(q)).scalars().all()
        pago_ids = [p.id for p in pagos]
        # imputaciones cobro -> pedido
        imps = []
        if pago_ids:
            imps = (await db.execute(
                select(PagoImputacion).where(PagoImputacion.pago_id.in_(pago_ids))
            )).scalars().all()
        pedido_ids = {i.pedido_id for i in imps}
        ped_nums = {}
        if pedido_ids:
            ped_nums = {r[0]: r[1] for r in (await db.execute(
                select(Pedido.id, Pedido.numero_pedido).where(Pedido.id.in_(pedido_ids))
            )).all()}
        imp_por_pago: dict[int, list] = {}
        for i in imps:
            imp_por_pago.setdefault(i.pago_id, []).append(i)
        cli_nombres = await _nombres(db, Cliente, {p.cliente_id for p in pagos})
        for p in pagos:
            links = [
                {"tipo": "pedido", "id": i.pedido_id, "label": ped_nums.get(i.pedido_id, f"#{i.pedido_id}")}
                for i in imp_por_pago.get(p.id, [])
            ]
            es_puente = bool(getattr(p, "es_puente", False))
            trans.append({
                "key": f"cobro-{p.id}",
                "tipo": "cobro",
                "tipo_label": "Tránsito (pasamanos)" if es_puente else "Cobro",
                "fecha": p.fecha_recepcion.isoformat(),
                "importe": float(p.importe),
                # Los cobros pasamanos no son plata propia: van como tránsito y no suman a ingresos.
                "direccion": "transito" if es_puente else "ingreso",
                "numero": p.numero_recibo,
                "metodo_pago": p.tipo_pago.value if p.tipo_pago else None,
                "cuenta": p.tipo_cuenta.value if p.tipo_cuenta else None,
                "contraparte": {"tipo": "cliente", "id": p.cliente_id, "nombre": cli_nombres.get(p.cliente_id, "-")},
                "links": links,
                "descripcion": p.observacion,
            })

    # ---- Pagos a proveedor ----
    if "pago_proveedor" in tipos:
        q = select(PagoProveedor)
        if fecha_desde:
            q = q.where(PagoProveedor.fecha_pago >= fecha_desde)
        if fecha_hasta:
            q = q.where(PagoProveedor.fecha_pago <= fecha_hasta)
        if cuenta_id is not None:
            q = q.where(PagoProveedor.cuenta_id == cuenta_id)
        pps = (await db.execute(q)).scalars().all()
        pp_ids = [pp.id for pp in pps]
        imps = []
        if pp_ids:
            imps = (await db.execute(
                select(PagoProveedorImputacion).where(PagoProveedorImputacion.pago_proveedor_id.in_(pp_ids))
            )).scalars().all()
        ingreso_ids = {i.ingreso_mercaderia_id for i in imps}
        ing_nums = {}
        if ingreso_ids:
            ing_nums = {r[0]: r[1] for r in (await db.execute(
                select(IngresoMercaderia.id, IngresoMercaderia.numero).where(IngresoMercaderia.id.in_(ingreso_ids))
            )).all()}
        imp_por_pp: dict[int, list] = {}
        for i in imps:
            imp_por_pp.setdefault(i.pago_proveedor_id, []).append(i)
        prov_nombres = await _nombres(db, Proveedor, {pp.proveedor_id for pp in pps})
        # Pagos financiados por un cobro pasamanos (cuenta puente): son tránsito, no egreso real.
        pago_ids_link = {pp.pago_id for pp in pps if pp.pago_id}
        puente_ids: set[int] = set()
        if pago_ids_link:
            puente_ids = {
                r[0] for r in (await db.execute(
                    select(Pago.id).where(and_(Pago.id.in_(pago_ids_link), Pago.es_puente == True))  # noqa: E712
                )).all()
            }
        for pp in pps:
            links = [
                {"tipo": "compra", "id": i.ingreso_mercaderia_id, "label": ing_nums.get(i.ingreso_mercaderia_id, f"#{i.ingreso_mercaderia_id}")}
                for i in imp_por_pp.get(pp.id, [])
            ]
            es_transito = pp.pago_id in puente_ids
            trans.append({
                "key": f"pagoprov-{pp.id}",
                "tipo": "pago_proveedor",
                "tipo_label": "Tránsito (pasamanos)" if es_transito else "Pago a proveedor",
                "fecha": pp.fecha_pago.isoformat(),
                "importe": float(pp.importe),
                "direccion": "transito" if es_transito else "egreso",
                "numero": pp.referencia_pago or f"PP-{pp.id}",
                "metodo_pago": pp.tipo_pago.value if pp.tipo_pago else None,
                "cuenta": pp.tipo_cuenta.value if pp.tipo_cuenta else None,
                "contraparte": {"tipo": "proveedor", "id": pp.proveedor_id, "nombre": prov_nombres.get(pp.proveedor_id, "-")},
                "links": links,
                "descripcion": pp.observacion,
            })

    # ---- Notas de crédito/débito de cliente ----
    if "nota_credito" in tipos or "nota_debito" in tipos:
        q = select(NotaCreditoDebito)
        if fecha_desde:
            q = q.where(NotaCreditoDebito.fecha >= fecha_desde)
        if fecha_hasta:
            q = q.where(NotaCreditoDebito.fecha <= fecha_hasta)
        notas = (await db.execute(q)).scalars().all()
        ped_ids = {n.pedido_id for n in notas if n.pedido_id}
        ped_nums = {}
        if ped_ids:
            ped_nums = {r[0]: r[1] for r in (await db.execute(
                select(Pedido.id, Pedido.numero_pedido).where(Pedido.id.in_(ped_ids))
            )).all()}
        cli_nombres = await _nombres(db, Cliente, {n.cliente_id for n in notas})
        for n in notas:
            es_credito = n.tipo == TipoNota.credito
            t = "nota_credito" if es_credito else "nota_debito"
            if t not in tipos:
                continue
            links = []
            if n.pedido_id:
                links.append({"tipo": "pedido", "id": n.pedido_id, "label": ped_nums.get(n.pedido_id, f"#{n.pedido_id}")})
            trans.append({
                "key": f"nota-{n.id}",
                "tipo": t,
                "tipo_label": "Nota de crédito" if es_credito else "Nota de débito",
                "fecha": n.fecha.isoformat(),
                "importe": float(n.importe_total),
                "direccion": "ajuste",
                "numero": n.numero,
                "metodo_pago": None,
                "cuenta": n.tipo_cuenta.value if n.tipo_cuenta else None,
                "contraparte": {"tipo": "cliente", "id": n.cliente_id, "nombre": cli_nombres.get(n.cliente_id, "-")},
                "links": links,
                "descripcion": n.motivo,
            })

    # ---- Notas de proveedor ----
    if "nota_proveedor" in tipos:
        q = select(NotaProveedor)
        if fecha_desde:
            q = q.where(NotaProveedor.fecha >= fecha_desde)
        if fecha_hasta:
            q = q.where(NotaProveedor.fecha <= fecha_hasta)
        notas = (await db.execute(q)).scalars().all()
        prov_nombres = await _nombres(db, Proveedor, {n.proveedor_id for n in notas})
        for n in notas:
            es_credito = n.tipo == TipoNota.credito
            trans.append({
                "key": f"notaprov-{n.id}",
                "tipo": "nota_proveedor",
                "tipo_label": "Nota de proveedor",
                "fecha": n.fecha.isoformat(),
                "importe": float(n.importe_total),
                "direccion": "ajuste",
                "numero": n.numero,
                "metodo_pago": None,
                "cuenta": None,
                "contraparte": {"tipo": "proveedor", "id": n.proveedor_id, "nombre": prov_nombres.get(n.proveedor_id, "-")},
                "links": [],
                "descripcion": ("Crédito" if es_credito else "Débito") + " de proveedor",
            })

    # ---- Filtro por nombre de contraparte ----
    if search:
        s = search.lower()
        trans = [t for t in trans if s in (t["contraparte"]["nombre"] or "").lower()]

    # ---- Orden por fecha desc + paginado en memoria ----
    trans.sort(key=lambda t: t["fecha"], reverse=True)
    total = len(trans)
    inicio = (page - 1) * page_size
    items = trans[inicio:inicio + page_size]

    # Totales del conjunto filtrado (no solo la página). El tránsito (pasamanos) se
    # contabiliza aparte y NO suma a ingresos/egresos reales.
    total_ingresos = sum(t["importe"] for t in trans if t["direccion"] == "ingreso")
    total_egresos = sum(t["importe"] for t in trans if t["direccion"] == "egreso")
    total_transito = sum(t["importe"] for t in trans if t["direccion"] == "transito")

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "resumen": {
            "ingresos": round(total_ingresos, 2),
            "egresos": round(total_egresos, 2),
            "neto": round(total_ingresos - total_egresos, 2),
            "transito": round(total_transito, 2),
        },
    }


@router.delete("")
async def eliminar_todas_transacciones(
    confirmar: str = Query(..., description="Debe ser 'ELIMINAR' para confirmar el borrado total"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    """Elimina TODAS las transacciones de dinero (cobros de cliente, pagos a proveedor,
    notas de crédito/débito de cliente y notas de proveedor) con sus imputaciones e items.

    Operación destructiva e irreversible. Además, como los cobros y notas afectan el
    `saldo_pendiente` de los pedidos, éste se resetea a `importe_total` (estado "sin pagos")
    para que la deuda derivada quede consistente.
    """
    if confirmar != "ELIMINAR":
        raise HTTPException(status_code=400, detail="Confirmación inválida")

    borrados: dict[str, int] = {}

    # Orden seguro respecto de las FKs: primero los hijos sin cascade, luego los padres.
    # pago_imputaciones -> pagos (FK sin ondelete): hay que borrarlas antes que los pagos.
    borrados["pago_imputaciones"] = (await db.execute(sa_delete(PagoImputacion))).rowcount
    # pago_proveedor_imputaciones y nota_credito_items tienen ondelete=CASCADE, pero los
    # borramos explícitamente para reportar el conteo real.
    borrados["pago_proveedor_imputaciones"] = (await db.execute(sa_delete(PagoProveedorImputacion))).rowcount
    borrados["nota_credito_items"] = (await db.execute(sa_delete(NotaCreditoItem))).rowcount

    # Padres. pagos_proveedor.pago_id -> pagos (ondelete=SET NULL): borrar pagos no rompe.
    borrados["cobros"] = (await db.execute(sa_delete(Pago))).rowcount
    borrados["pagos_proveedor"] = (await db.execute(sa_delete(PagoProveedor))).rowcount
    borrados["notas_credito_debito"] = (await db.execute(sa_delete(NotaCreditoDebito))).rowcount
    borrados["notas_proveedor"] = (await db.execute(sa_delete(NotaProveedor))).rowcount

    # Sin cobros ni notas, ningún pedido tiene pagos: saldo_pendiente = importe_total.
    await db.execute(sa_update(Pedido).values(saldo_pendiente=Pedido.importe_total))

    await db.commit()

    total = sum(borrados[k] for k in ("cobros", "pagos_proveedor", "notas_credito_debito", "notas_proveedor"))
    return {"eliminadas": total, "detalle": borrados}

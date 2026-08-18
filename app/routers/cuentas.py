from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.cliente import Cliente
from app.models.cuenta import Cuenta
from app.models.pago import EstadoPago, Pago
from app.models.pago_proveedor import PagoProveedor
from app.models.proveedor import Proveedor
from app.models.user import User
from app.utils.deps import get_current_user, require_role

router = APIRouter()


class CuentaBase(BaseModel):
    nombre: str
    tipo: str = "banco"        # efectivo | banco | billetera | otro
    banco: Optional[str] = None
    numero_cuenta: Optional[str] = None
    titular: Optional[str] = None
    cbu: Optional[str] = None
    alias: Optional[str] = None
    es_default: bool = False


class CuentaUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    banco: Optional[str] = None
    numero_cuenta: Optional[str] = None
    titular: Optional[str] = None
    cbu: Optional[str] = None
    alias: Optional[str] = None
    activo: Optional[bool] = None


class CuentaMovimiento(BaseModel):
    fecha: str
    tipo: str  # ingreso | egreso
    importe: float
    descripcion: str
    numero: Optional[str] = None


class CuentaResponse(CuentaBase):
    id: int
    activo: bool
    balance: float = 0.0
    ultimos_movimientos: list[CuentaMovimiento] = []
    model_config = {"from_attributes": True}


async def _balance_y_movimientos(db: AsyncSession, cuenta_id: int) -> tuple[Decimal, list[dict]]:
    """Balance real de una cuenta = cobros de cliente recibidos - pagos a proveedor
    salidos por esa cuenta. Las notas de crédito/débito no mueven caja de una cuenta
    puntual, así que no se incluyen acá."""
    ingresos_total = (await db.execute(
        select(func.coalesce(func.sum(Pago.importe), 0)).where(
            Pago.cuenta_id == cuenta_id, Pago.estado != EstadoPago.rechazado
        )
    )).scalar_one()
    egresos_total = (await db.execute(
        select(func.coalesce(func.sum(PagoProveedor.importe), 0)).where(
            PagoProveedor.cuenta_id == cuenta_id
        )
    )).scalar_one()
    balance = Decimal(str(ingresos_total)) - Decimal(str(egresos_total))

    ingresos_rows = (await db.execute(
        select(Pago.importe, Pago.fecha_recepcion, Pago.numero_recibo, Cliente.nombre)
        .join(Cliente, Cliente.id == Pago.cliente_id)
        .where(Pago.cuenta_id == cuenta_id, Pago.estado != EstadoPago.rechazado)
        .order_by(Pago.fecha_recepcion.desc())
        .limit(5)
    )).all()
    egresos_rows = (await db.execute(
        select(PagoProveedor.importe, PagoProveedor.fecha_pago, PagoProveedor.referencia_pago, Proveedor.nombre)
        .join(Proveedor, Proveedor.id == PagoProveedor.proveedor_id)
        .where(PagoProveedor.cuenta_id == cuenta_id)
        .order_by(PagoProveedor.fecha_pago.desc())
        .limit(5)
    )).all()

    movimientos = [
        {
            "fecha": fecha.isoformat(),
            "tipo": "ingreso",
            "importe": float(importe),
            "descripcion": f"Cobro de {nombre}",
            "numero": numero,
        }
        for importe, fecha, numero, nombre in ingresos_rows
    ] + [
        {
            "fecha": fecha.isoformat(),
            "tipo": "egreso",
            "importe": float(importe),
            "descripcion": f"Pago a {nombre}",
            "numero": numero,
        }
        for importe, fecha, numero, nombre in egresos_rows
    ]
    movimientos.sort(key=lambda m: m["fecha"], reverse=True)
    return balance, movimientos[:5]


async def asegurar_default(db: AsyncSession) -> Cuenta:
    """Garantiza que exista una cuenta y que haya exactamente una por defecto."""
    cuentas = (await db.execute(select(Cuenta).where(Cuenta.activo == True))).scalars().all()  # noqa: E712
    if not cuentas:
        c = Cuenta(nombre="Caja", tipo="efectivo", es_default=True, activo=True)
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return c
    default = next((c for c in cuentas if c.es_default), None)
    if default is None:
        cuentas[0].es_default = True
        await db.commit()
        default = cuentas[0]
    return default


@router.get("", response_model=list[CuentaResponse])
async def listar_cuentas(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    await asegurar_default(db)
    rows = (await db.execute(
        select(Cuenta).where(Cuenta.activo == True).order_by(Cuenta.es_default.desc(), Cuenta.nombre)  # noqa: E712
    )).scalars().all()
    result = []
    for c in rows:
        balance, movimientos = await _balance_y_movimientos(db, c.id)
        item = CuentaResponse.model_validate(c).model_dump()
        item["balance"] = float(balance)
        item["ultimos_movimientos"] = movimientos
        result.append(item)
    return result


@router.get("/default", response_model=CuentaResponse)
async def cuenta_default(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return await asegurar_default(db)


@router.post("", response_model=CuentaResponse, status_code=status.HTTP_201_CREATED)
async def crear_cuenta(
    body: CuentaBase,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    cuenta = Cuenta(**body.model_dump())
    if cuenta.es_default:
        await db.execute(sa_update(Cuenta).values(es_default=False))
    db.add(cuenta)
    await db.commit()
    await db.refresh(cuenta)
    return cuenta


@router.put("/{id}", response_model=CuentaResponse)
async def actualizar_cuenta(
    id: int,
    body: CuentaUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    cuenta = (await db.execute(select(Cuenta).where(Cuenta.id == id))).scalar_one_or_none()
    if not cuenta:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(cuenta, k, v)
    await db.commit()
    await db.refresh(cuenta)
    return cuenta


@router.post("/{id}/set-default", response_model=CuentaResponse)
async def marcar_default(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    cuenta = (await db.execute(select(Cuenta).where(Cuenta.id == id))).scalar_one_or_none()
    if not cuenta:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    await db.execute(sa_update(Cuenta).values(es_default=False))
    cuenta.es_default = True
    cuenta.activo = True
    await db.commit()
    await db.refresh(cuenta)
    return cuenta


@router.delete("/{id}")
async def eliminar_cuenta(
    id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    cuenta = (await db.execute(select(Cuenta).where(Cuenta.id == id))).scalar_one_or_none()
    if not cuenta:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    if cuenta.es_default:
        raise HTTPException(status_code=400, detail="No se puede eliminar la cuenta por defecto. Marcá otra como default primero.")
    cuenta.activo = False
    await db.commit()
    return {"message": f"Cuenta '{cuenta.nombre}' desactivada"}

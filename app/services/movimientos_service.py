from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from decimal import Decimal

from app.models.cuenta_sanalle import CuentaSanalle, TipoMovimiento, CategoriaMovimiento
from app.models.pago import TipoPago


async def registrar_movimiento(
    db: AsyncSession,
    tipo: TipoMovimiento,
    categoria: CategoriaMovimiento,
    importe: Decimal,
    metodo_pago: TipoPago,
    usuario_id: int,
    descripcion: str | None = None,
    referencia_id: str | None = None,
    fecha: datetime | None = None
) -> CuentaSanalle:
    """
    Registra un movimiento en la Cuenta Sanalle (Libro Mayor).
    """
    if fecha is None:
        fecha = datetime.now()
        
    movimiento = CuentaSanalle(
        fecha=fecha,
        tipo=tipo,
        categoria=categoria,
        importe=importe,
        metodo_pago=metodo_pago,
        descripcion=descripcion,
        referencia_id=referencia_id,
        usuario_id=usuario_id
    )
    db.add(movimiento)
    await db.flush()
    return movimiento

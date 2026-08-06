from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class MovimientoCC(BaseModel):
    fecha: datetime
    tipo: str  # pedido, pago, nota_credito, nota_debito
    numero: str
    descripcion: Optional[str] = None
    debe: float = 0
    haber: float = 0
    saldo: float = 0


class CuentaCorrienteResponse(BaseModel):
    cliente_id: int
    cliente_nombre: Optional[str] = None
    movimientos: list[MovimientoCC] = []
    saldo_total: float = 0
    saldo_a_favor: float = 0


class SaldoResponse(BaseModel):
    cliente_id: int
    saldo: float
    fecha: Optional[date] = None

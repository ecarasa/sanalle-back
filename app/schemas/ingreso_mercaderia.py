from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class IngresoImputacionResponse(BaseModel):
    id: int
    pago_proveedor_id: int
    importe_aplicado: Decimal
    fecha_pago: datetime
    tipo_pago: str
    referencia_pago: Optional[str] = None

    model_config = {"from_attributes": True}


class IngresoMercaderiaItemCreate(BaseModel):
    producto_id: int
    cantidad_cajas: int = 0
    cantidad_blisters: int = 0
    costo_unitario: Optional[float] = None  # costo neto por caja


class IngresoMercaderiaItemResponse(IngresoMercaderiaItemCreate):
    id: int
    producto_nombre: Optional[str] = None

    model_config = {"from_attributes": True}


class IngresoImpuestoCreate(BaseModel):
    tipo_iva_id: Optional[int] = None
    concepto: str
    base: Optional[float] = None   # si no viene, se usa el subtotal neto
    tasa: float = 0.0
    importe: Optional[float] = None  # si no viene, se calcula base * tasa / 100


class IngresoImpuestoResponse(BaseModel):
    id: int
    tipo_iva_id: Optional[int] = None
    concepto: str
    base: float
    tasa: float
    importe: float

    model_config = {"from_attributes": True}


class IngresoMercaderiaBase(BaseModel):
    fecha: date
    proveedor_id: Optional[int] = None
    numero_comprobante: str
    observacion: Optional[str] = None
    fecha_vencimiento: Optional[datetime] = None
    dias_plazo: Optional[int] = None


class IngresoMercaderiaCreate(IngresoMercaderiaBase):
    deposito_id: int  # depósito al que entra la mercadería
    items: list[IngresoMercaderiaItemCreate]
    impuestos: list[IngresoImpuestoCreate] = []


class IngresoMercaderiaResponse(IngresoMercaderiaBase):
    id: int
    numero: str
    deposito_id: int
    deposito_nombre: Optional[str] = None
    creado_por_id: int
    creado_por_nombre: Optional[str] = None
    proveedor_nombre: Optional[str] = None
    items: list[IngresoMercaderiaItemResponse] = []
    impuestos: list[IngresoImpuestoResponse] = []
    subtotal_neto: float = 0.0
    importe_total: float = 0.0
    saldo_pendiente: float = 0.0
    imputaciones: list[IngresoImputacionResponse] = []
    created_at: datetime
    updated_at: datetime
    # Antes era la URL pública del archivo. Ahora el objeto es privado:
    # sólo se informa si hay adjunto; el link se pide a GET /{id}/archivo.
    tiene_archivo: bool = False

    model_config = {"from_attributes": True}

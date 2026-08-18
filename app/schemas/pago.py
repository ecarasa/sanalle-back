from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.pago_proveedor import PagoProveedorResponse


class PagoBase(BaseModel):
    cliente_id: int
    tipo_pago: str
    importe: float = Field(..., gt=0)
    fecha_recepcion: Optional[datetime] = None
    observacion: Optional[str] = None
    referencia: Optional[str] = None
    banco_id: Optional[int] = None
    cuenta_id: Optional[int] = None  # cuenta de la empresa (si no se elige, va a la default)
    ch_numero: Optional[str] = None
    ch_banco: Optional[str] = None
    ch_fecha: Optional[date] = None
    ch_vto: Optional[date] = None
    retencion_tipo: Optional[str] = None
    retencion_numero: Optional[str] = None
    retencion_fecha: Optional[date] = None
    transferencia_numero: Optional[str] = None
    transferencia_fecha: Optional[date] = None
    transferencia_cuenta_origen: Optional[str] = None
    grupo_recibo_id: Optional[str] = None
    tipo_cuenta: str = "remito"
    saldo_restante: float = 0.0
    es_puente: bool = False  # cobro-pasamanos: la plata sale directo a un proveedor


class PagoCreate(PagoBase):
    auto_imputar: bool = False


class PagoUpdate(BaseModel):
    estado: Optional[str] = None
    observacion: Optional[str] = None


class PagoImputacionResponse(BaseModel):
    id: int
    pago_id: int
    pedido_id: int
    numero_pedido: Optional[str] = None
    monto: float
    observacion: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PagoResponse(PagoBase):
    id: int
    receptor_id: int
    receptor_nombre: Optional[str] = None
    cliente_nombre: Optional[str] = None
    estado: str
    recibo_pdf_path: Optional[str] = None
    numero_recibo: str
    saldo_restante: float
    created_at: datetime
    updated_at: datetime
    imputaciones: list[PagoImputacionResponse] = []
    pagos_proveedor: list[PagoProveedorResponse] = []

    model_config = {"from_attributes": True}


class PagoImputarRequest(BaseModel):
    pedido_id: int
    monto: float = Field(..., gt=0)
    observacion: Optional[str] = None


class PagoBulkImputarRequest(BaseModel):
    imputaciones: list[PagoImputarRequest]

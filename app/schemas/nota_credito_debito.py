from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class NotaCreditoItemCreate(BaseModel):
    producto_id: Optional[int] = None
    descripcion: str
    cantidad_cajas: int = 0
    cantidad_blisters: int = 0
    unidad_venta: str = "caja"
    precio_unitario: float
    precio_total: float


class NotaCreditoItemResponse(NotaCreditoItemCreate):
    id: int

    model_config = {"from_attributes": True}


class NotaCreditoDebitoBase(BaseModel):
    tipo: str
    cliente_id: int
    fecha: date
    motivo: Optional[str] = None
    pedido_id: Optional[int] = None
    tipo_cuenta: str = "remito"
    afecta_stock: bool = False
    stock_tipo: Optional[str] = None


class NotaCreditoDebitoCreate(NotaCreditoDebitoBase):
    items: list[NotaCreditoItemCreate]


class NotaCreditoDebitoResponse(NotaCreditoDebitoBase):
    id: int
    numero: str
    importe_total: float
    creado_por_id: int
    creado_por_nombre: Optional[str] = None
    cliente_nombre: Optional[str] = None
    items: list[NotaCreditoItemResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}

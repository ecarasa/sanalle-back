from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class PagoProveedorInlineCreate(BaseModel):
    """Used when creating a supplier payment inline inside a Pago creation."""
    proveedor_id: int
    importe: float = Field(..., gt=0)
    tipo_cuenta: str = "remito"
    referencia_pago: Optional[str] = None
    observacion: Optional[str] = None


class PagoProveedorBase(BaseModel):
    proveedor_id: int
    importe: float = Field(..., gt=0)
    fecha_pago: datetime
    tipo_pago: str
    tipo_cuenta: str = "remito"
    referencia_pago: Optional[str] = None
    observacion: Optional[str] = None


class PagoProveedorCreate(PagoProveedorBase):
    pago_id: Optional[int] = None


class PagoProveedorImputacionResponse(BaseModel):
    id: int
    pago_proveedor_id: int
    ingreso_mercaderia_id: int
    importe_aplicado: Decimal
    ingreso_numero: Optional[str] = None
    ingreso_comprobante: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PagoProveedorResponse(PagoProveedorBase):
    id: int
    usuario_id: int
    pago_id: Optional[int] = None
    proveedor_nombre: Optional[str] = None
    imputaciones: list[PagoProveedorImputacionResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

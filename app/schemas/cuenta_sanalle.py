from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CuentaSanalleBase(BaseModel):
    fecha: datetime
    tipo: str
    categoria: str
    importe: float = Field(..., gt=0)
    metodo_pago: str
    descripcion: Optional[str] = None
    referencia_id: Optional[str] = None


class CuentaSanalleCreate(CuentaSanalleBase):
    """
    Schema for manual entry in the ledger.
    """
    pass


class CuentaSanalleResponse(CuentaSanalleBase):
    id: int
    usuario_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

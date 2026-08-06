from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SolicitudCambioClienteCreate(BaseModel):
    cliente_id: int
    campo: Optional[str] = None
    valor_anterior: Optional[str] = None
    valor_nuevo: Optional[str] = None
    motivo: Optional[str] = None


class SolicitudCambioClienteResponse(SolicitudCambioClienteCreate):
    id: int
    solicitante_id: int
    solicitante_nombre: Optional[str] = None
    cliente_nombre: Optional[str] = None
    estado: str
    revisado_por_id: Optional[int] = None
    revisado_por_nombre: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BitacoraPedidoResponse(BaseModel):
    id: int
    pedido_id: int
    numero_pedido: Optional[str] = None
    usuario_id: Optional[int] = None
    usuario_nombre: Optional[str] = None
    evento: str
    entidad: str
    accion: str
    campo: Optional[str] = None
    valor_anterior: Optional[str] = None
    valor_nuevo: Optional[str] = None
    producto_id: Optional[int] = None
    producto_nombre: Optional[str] = None
    grupo_id: Optional[str] = None
    observacion: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

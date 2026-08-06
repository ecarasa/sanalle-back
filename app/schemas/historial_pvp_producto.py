from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict

class HistorialPvpProductoBase(BaseModel):
    producto_id: int
    pvp_anterior: Optional[Decimal] = None
    pvp_nuevo: Decimal
    fecha_cambio: datetime

class HistorialPvpProductoResponse(HistorialPvpProductoBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

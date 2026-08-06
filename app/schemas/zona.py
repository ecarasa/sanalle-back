from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class ZonaBase(BaseModel):
    nombre: str

class ZonaCreate(ZonaBase):
    pass

class ZonaUpdate(BaseModel):
    nombre: Optional[str] = None
    activo: Optional[bool] = None

class ZonaResponse(ZonaBase):
    id: int
    activo: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

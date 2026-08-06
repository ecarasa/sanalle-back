from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional

class LaboratorioBase(BaseModel):
    nombre: str
    activo: bool = True

class LaboratorioCreate(LaboratorioBase):
    pass

class LaboratorioUpdate(BaseModel):
    nombre: Optional[str] = None
    activo: Optional[bool] = None

class LaboratorioResponse(LaboratorioBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

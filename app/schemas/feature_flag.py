from datetime import datetime
from pydantic import BaseModel, ConfigDict


class FeatureFlagUpdate(BaseModel):
    habilitado: bool


class FeatureFlagResponse(BaseModel):
    clave: str
    habilitado: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class LocalidadBase(BaseModel):
    nombre: str
    provincia: Optional[str] = None
    codigo_postal: Optional[str] = None

    @field_validator("nombre", "provincia")
    @classmethod
    def format_nombre(cls, v: str | None) -> str | None:
        return v.strip().title() if v else v


class LocalidadCreate(LocalidadBase):
    pass


class LocalidadUpdate(BaseModel):
    nombre: Optional[str] = None
    provincia: Optional[str] = None
    codigo_postal: Optional[str] = None
    activo: Optional[bool] = None


class LocalidadResponse(LocalidadBase):
    id: int
    activo: bool
    created_at: datetime

    model_config = {"from_attributes": True}

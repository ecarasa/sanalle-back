from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class BancoBase(BaseModel):
    nombre: str
    codigo: Optional[str] = None

    @field_validator("nombre")
    @classmethod
    def format_nombre(cls, v: str) -> str:
        return v.strip().title() if v else v


class BancoCreate(BancoBase):
    pass


class BancoUpdate(BaseModel):
    nombre: Optional[str] = None
    codigo: Optional[str] = None
    activo: Optional[bool] = None


class BancoResponse(BancoBase):
    id: int
    activo: bool
    created_at: datetime

    model_config = {"from_attributes": True}

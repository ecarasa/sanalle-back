from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class UserBase(BaseModel):
    email: str
    username: str
    nombre_completo: str
    rol: str

    @field_validator("nombre_completo")
    @classmethod
    def format_nombre_completo(cls, v: str) -> str:
        return v.strip().title() if v else v


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)


class UserUpdate(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    nombre_completo: Optional[str] = None
    rol: Optional[str] = None
    activo: Optional[bool] = None
    comision_generico: Optional[float] = None
    comision_otc: Optional[float] = None


class UserResponse(UserBase):
    id: int
    activo: bool
    debe_cambiar_contrasena: bool = False
    created_at: datetime
    comision_generico: float = 0.0
    comision_otc: float = 0.0

    model_config = {"from_attributes": True}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6)


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    username: str
    password: str

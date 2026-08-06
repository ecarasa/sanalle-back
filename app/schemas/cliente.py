from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class ClienteBase(BaseModel):
    nombre: str
    razon_social: Optional[str] = None
    cuit: Optional[str] = None
    domicilio: str
    deuda_inicial: float = 0
    deuda_inicial_remito: float = 0
    deuda_inicial_factura: float = 0

    @field_validator("nombre", "domicilio")
    @classmethod
    def format_str_fields(cls, v: str) -> str:
        return v.strip().title() if v else v

    @field_validator("razon_social")
    @classmethod
    def format_razon_social(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().title() if v else v

    telefono: Optional[str] = None
    whatsapp: Optional[str] = None
    email: Optional[str] = None
    categoria: Optional[str] = None
    tipo: Optional[str] = None          # "mayorista" | "minorista"
    zona_id: Optional[int] = None
    condicion_pago: Optional[str] = None  # "contado" | "plazo"
    plazo_dias: Optional[int] = None
    vendedor_id: Optional[int] = None
    localidad_id: Optional[int] = None
    comentarios: Optional[str] = None


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    nombre: Optional[str] = None
    razon_social: Optional[str] = None
    cuit: Optional[str] = None
    domicilio: Optional[str] = None
    telefono: Optional[str] = None
    whatsapp: Optional[str] = None
    email: Optional[str] = None
    categoria: Optional[str] = None
    tipo: Optional[str] = None
    zona_id: Optional[int] = None
    condicion_pago: Optional[str] = None
    plazo_dias: Optional[int] = None
    vendedor_id: Optional[int] = None
    activo: Optional[bool] = None
    localidad_id: Optional[int] = None
    comentarios: Optional[str] = None
    aprobado: Optional[bool] = None


class ClienteResponse(ClienteBase):
    id: int
    activo: bool
    aprobado: bool = True
    avg_dias_pago: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    localidad_nombre: Optional[str] = None
    zona_nombre: Optional[str] = None

    model_config = {"from_attributes": True}


class ClienteConDeuda(ClienteResponse):
    deuda: float = 0
    saldo_remitos: float = 0
    saldo_facturas: float = 0
    vendedor_nombre: Optional[str] = None
    semaforo: Optional[str] = None
    dias_mora: Optional[int] = None

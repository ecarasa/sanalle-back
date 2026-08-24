from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class MovimientoStockBase(BaseModel):
    producto_id: int
    # ADJUST, TRANSFER, INGRESO, NC_RETURN, ND_ADJUST
    tipo_operacion: str
    deposito_origen_id: Optional[int] = None
    deposito_destino_id: Optional[int] = None
    cantidad_cajas: int = 0
    cantidad_blisters: int = 0
    observacion: Optional[str] = None


class MovimientoStockCreate(MovimientoStockBase):
    pass


class MovimientoStockResponse(MovimientoStockBase):
    id: int
    usuario_id: int
    created_at: datetime
    usuario_nombre: Optional[str] = None
    producto_nombre: Optional[str] = None
    deposito_origen_nombre: Optional[str] = None
    deposito_destino_nombre: Optional[str] = None

    class Config:
        from_attributes = True


class StockOperacionRequest(BaseModel):
    """Ajuste manual o transferencia de stock desde la ficha del producto.

    - ADJUST: suma (o resta, con cantidades negativas) en `deposito_id`.
    - TRANSFER: mueve de `deposito_id` a `deposito_destino_id`.
    """

    tipo_operacion: str
    deposito_id: Optional[int] = None
    deposito_destino_id: Optional[int] = None
    cantidad_cajas: int = 0
    cantidad_blisters: int = 0
    observacion: Optional[str] = None

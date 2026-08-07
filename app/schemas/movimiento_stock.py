from datetime import datetime
from pydantic import BaseModel
from typing import Optional

class MovimientoStockBase(BaseModel):
    producto_id: int
    tipo_operacion: str  # TRANSFER, FRACTION, ADJUST
    origen: Optional[str] = None
    destino: Optional[str] = None
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

    class Config:
        from_attributes = True

class StockOperacionRequest(BaseModel):
    tipo_operacion: str # TRANSFER, FRACTION, ADJUST
    origen: Optional[str] = None # STOCK_A, STOCK_B
    destino: Optional[str] = None # STOCK_A, STOCK_B
    deposito_id: Optional[int] = None  # ADJUST: depósito destino (soporta depósitos nuevos)
    cantidad_cajas: int = 0
    cantidad_blisters: int = 0
    observacion: Optional[str] = None

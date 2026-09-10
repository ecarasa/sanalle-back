from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.services.pricing_service import GRUPOS


def _normalizar_tipo_cliente(v: Optional[str]) -> Optional[str]:
    """Normaliza `tipo` a una de las listas de precios conocidas.

    La columna es texto libre y arrastra datos viejos con mayúsculas ("MAYORISTA")
    o abreviados. El form de pedidos siembra la lista de precios a partir de este
    valor y, si no lo reconoce, cae en silencio a minorista: un cliente mayorista
    terminaba cotizado al precio equivocado sin que nadie se enterara. Bajar a
    minúsculas y limpiar espacios arregla el caso real.

    Normaliza en vez de rechazar a propósito: `ClienteResponse` hereda de
    `ClienteBase`, así que un `raise` acá haría explotar el listado entero de
    clientes ante una sola fila con basura en la columna. Lo desconocido queda en
    None, que es la verdad —no es ninguna de las listas— y el form lo muestra
    vacío para que alguien lo corrija.
    """
    if v is None:
        return v
    normalizado = v.strip().lower()
    return normalizado if normalizado in GRUPOS else None


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

    @field_validator("tipo")
    @classmethod
    def _chk_tipo(cls, v: Optional[str]) -> Optional[str]:
        return _normalizar_tipo_cliente(v)

    telefono: Optional[str] = None
    whatsapp: Optional[str] = None
    email: Optional[str] = None
    categoria: Optional[str] = None
    tipo: Optional[str] = None          # grupo de precios: minorista | mayorista | comercio
    zona_id: Optional[int] = None
    condicion_pago: Optional[str] = None  # "contado" | "plazo"
    plazo_dias: Optional[int] = None
    dias_entrega: Optional[int] = None
    vendedor_id: Optional[int] = None
    localidad_id: Optional[int] = None
    comentarios: Optional[str] = None
    # Último transporte usado con este cliente. Se actualiza solo al guardar un
    # pedido; acá se puede fijar o corregir a mano.
    transporte_habitual: Optional[str] = None


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
    dias_entrega: Optional[int] = None
    vendedor_id: Optional[int] = None
    activo: Optional[bool] = None
    localidad_id: Optional[int] = None
    comentarios: Optional[str] = None
    transporte_habitual: Optional[str] = None
    aprobado: Optional[bool] = None

    @field_validator("tipo")
    @classmethod
    def _chk_tipo(cls, v: Optional[str]) -> Optional[str]:
        return _normalizar_tipo_cliente(v)


class ClienteResponse(ClienteBase):
    id: int
    activo: bool
    aprobado: bool = True
    avg_dias_pago: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    localidad_nombre: Optional[str] = None
    localidad_provincia: Optional[str] = None
    localidad_codigo_postal: Optional[str] = None
    zona_nombre: Optional[str] = None

    model_config = {"from_attributes": True}


class ClienteConDeuda(ClienteResponse):
    deuda: float = 0
    saldo_remitos: float = 0
    saldo_facturas: float = 0
    vendedor_nombre: Optional[str] = None
    semaforo: Optional[str] = None
    dias_mora: Optional[int] = None
    # Semáforo de ACTIVIDAD (recencia de compra), distinto del semáforo de mora.
    ultima_compra: Optional[str] = None       # fecha ISO de la última compra, o None
    dias_ultima_compra: Optional[int] = None  # días desde la última compra
    semaforo_actividad: Optional[str] = None  # "verde" | "amarillo" | "rojo"


class ClienteDireccionBase(BaseModel):
    """Una dirección de entrega de la libreta del cliente."""

    etiqueta: str
    direccion: str
    localidad_id: Optional[int] = None
    codigo_postal: Optional[str] = None
    es_default: bool = False


class ClienteDireccionCreate(ClienteDireccionBase):
    pass


class ClienteDireccionUpdate(BaseModel):
    etiqueta: Optional[str] = None
    direccion: Optional[str] = None
    localidad_id: Optional[int] = None
    codigo_postal: Optional[str] = None
    es_default: Optional[bool] = None
    activo: Optional[bool] = None


class ClienteDireccionResponse(ClienteDireccionBase):
    id: int
    cliente_id: int
    activo: bool
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    localidad_nombre: Optional[str] = None

    model_config = {"from_attributes": True}

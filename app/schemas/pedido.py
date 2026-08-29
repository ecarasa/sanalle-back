from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class PedidoItemBase(BaseModel):
    producto_id: int
    # Depósito del que sale la línea. Si viene vacío se usa el del pedido; que no
    # haya ninguno de los dos es un error, no un default silencioso.
    deposito_id: Optional[int] = None
    cantidad_cajas: int = Field(0, ge=0)
    cantidad_blisters: int = Field(0, ge=0)
    cantidad: Optional[int] = None  # Generic quantity (mapped to the sale unit)
    # Unidad de venta de la línea: 'caja' (default) | 'blister'. Define cómo se
    # interpreta `cantidad` y en qué unidad se descuenta el stock.
    unidad_venta: str = "caja"
    precio_lista: Optional[float] = None
    descuento_porcentaje: Optional[float] = None
    precio_unitario: float
    precio_total: float


class PedidoItemCreate(PedidoItemBase):
    pass


class PedidoItemResponse(PedidoItemBase):
    id: int
    deposito_nombre: Optional[str] = None
    producto_nombre: Optional[str] = None
    presentacion: Optional[str] = None
    blisters_por_caja: Optional[int] = None
    margen: Optional[float] = None  # computed: (precio_unitario - costo_mas_iibb) / precio_unitario * 100
    # Precios de venta del producto por lista, para que el form pueda recalcular al
    # cambiar de lista o de formato sin volver a pedir el producto.
    producto_precios: dict[str, Optional[float]] = {}

    model_config = {"from_attributes": True}


class PedidoPlanPagoBase(BaseModel):
    """Un tramo del plan de cobro: forma, cuenta destino e importe."""

    forma: str
    cuenta_id: Optional[int] = None
    importe: float = 0
    observacion: Optional[str] = None


class PedidoPlanPagoCreate(PedidoPlanPagoBase):
    pass


class PedidoPlanPagoResponse(PedidoPlanPagoBase):
    id: int
    cuenta_nombre: Optional[str] = None

    model_config = {"from_attributes": True}


class PedidoBase(BaseModel):
    """Lo que carga ventas.

    `bultos`, `fecha_entrega` y `despachado` NO están acá: los carga depósito /
    logística por `PATCH /pedidos/{id}/logistica`. La fecha de entrega la sugiere
    el backend al crear el pedido, a partir de los días de entrega del cliente.
    """

    cliente_id: int
    observacion: Optional[str] = None
    tipo_documento: Optional[str] = None
    saldo_pendiente: Optional[float] = None
    transporte: Optional[str] = None
    # Dirección de entrega elegida de la libreta del cliente. `direccion_entrega`
    # es el texto que queda guardado en el pedido (la foto del momento).
    direccion_entrega_id: Optional[int] = None
    direccion_entrega: Optional[str] = None  # envío: por defecto el domicilio del cliente, editable
    fecha_compromiso_pago: Optional[date] = None
    sociedad: Optional[str] = None  # "sanalle" | "farmacare" — solo facturación
    # Depósito por defecto del pedido: se aplica a las líneas que no traen uno propio.
    deposito_id: Optional[int] = None
    tipo_precio: Optional[str] = "minorista"
    # False = el pedido no compromete mercadería. Para operaciones de volumen que
    # se facturan antes de que entre el ingreso del proveedor.
    reserva_stock: bool = True


class PedidoCreate(PedidoBase):
    items: list[PedidoItemCreate] = []
    plan_pago: list[PedidoPlanPagoCreate] = []
    vendedor_id: Optional[int] = None


class PedidoUpdate(BaseModel):
    shipping_status: Optional[str] = None
    payment_status: Optional[str] = None
    fecha: Optional[date] = None  # fecha de creación (editable)
    observacion: Optional[str] = None
    tipo_documento: Optional[str] = None
    transporte: Optional[str] = None
    direccion_entrega_id: Optional[int] = None
    direccion_entrega: Optional[str] = None
    fecha_compromiso_pago: Optional[date] = None
    sociedad: Optional[str] = None
    deposito_id: Optional[int] = None
    tipo_precio: Optional[str] = None
    vendedor_id: Optional[int] = None
    reserva_stock: Optional[bool] = None
    items: Optional[list[PedidoItemCreate]] = None
    # None = no tocar. Una lista (aunque sea vacía) reemplaza el plan entero.
    plan_pago: Optional[list[PedidoPlanPagoCreate]] = None


class PedidoLogisticaUpdate(BaseModel):
    """Lo que carga depósito/logística sobre un pedido ya tomado.

    Va por su propio endpoint porque el `PUT` general está bloqueado en cuanto el
    pedido sale de ventas, y justamente estos datos aparecen después: los bultos
    se cuentan al armar, la fecha de entrega se confirma al planificar el reparto.
    """

    bultos: Optional[int] = Field(None, ge=0)
    fecha_entrega: Optional[date] = None
    despachado: Optional[bool] = None


class PedidoShippingStatusUpdate(BaseModel):
    shipping_status: str


class PedidoPaymentStatusUpdate(BaseModel):
    payment_status: str


class PedidoItemComisionUpdate(BaseModel):
    comision_porcentaje: float


class AsignarRepartidorRequest(BaseModel):
    pedido_ids: list[int]
    repartidor_id: int


class PedidoResponse(BaseModel):
    id: int
    numero_pedido: str
    cliente_id: int
    cliente_nombre: Optional[str] = None
    cliente_tipo: Optional[str] = None
    vendedor_id: int
    vendedor_nombre: Optional[str] = None
    shipping_status: str
    payment_status: str
    semaforo: Optional[str] = None  # computed: rojo/azul/verde/amarillo/gris
    tipo_documento: Optional[str] = None
    fecha: date
    fecha_entrega: Optional[date] = None
    transporte: Optional[str] = None
    fecha_compromiso_pago: Optional[date] = None
    despachado: bool = False
    sociedad: Optional[str] = None
    # Depósitos involucrados, ya resueltos a nombre. Normalmente uno solo; son
    # varios cuando una línea se tomó de otro depósito por falta de stock.
    depositos: list[str] = []
    tipo_precio: Optional[str] = None
    importe_total: float
    saldo_pendiente: float
    observacion: Optional[str] = None
    cliente_domicilio: Optional[str] = None
    cliente_telefono: Optional[str] = None
    cliente_localidad: Optional[str] = None
    cliente_codigo_postal: Optional[str] = None
    cliente_provincia: Optional[str] = None
    cliente_zona: Optional[str] = None
    repartidor_id: Optional[int] = None
    repartidor_nombre: Optional[str] = None
    direccion_entrega_id: Optional[int] = None
    direccion_entrega: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    bultos: Optional[int] = 0
    reserva_stock: bool = True
    items: list[PedidoItemResponse] = []
    plan_pago: list[PedidoPlanPagoResponse] = []

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UbicacionUpdate(BaseModel):
    direccion: str


class Coordenada(BaseModel):
    latitud: float
    longitud: float


class OptimizarRutaRequest(BaseModel):
    coordenadas: list[Coordenada]
    pedidos_ids: list[int]
    fecha: Optional[date] = None  # fecha de entrega real de la ruta (para la caché)


class DespacharRutaRequest(BaseModel):
    pedido_ids: list[int]


class HojaRutaRequest(BaseModel):
    pedido_ids: list[int]  # en el orden óptimo de paradas
    fecha: Optional[date] = None

class TramoRuta(BaseModel):
    distancia_km: float
    tiempo_minutos: float

class OptimizarRutaResponse(BaseModel):
    hash_id: str
    coords: list[tuple[float, float]]  # [(lat, lon), ...]
    km: float
    tiempo_minutos: float
    waypoints: list[int]  # Indice original ordenado
    tramos: list[TramoRuta]

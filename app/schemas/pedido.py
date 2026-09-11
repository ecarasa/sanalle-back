from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.services.pricing_service import GRUPOS

# Espeja `ModalidadEntrega` de app/models/pedido.py. La columna es texto, así que
# esta validación es la que evita que entre un valor que el remito no sabe armar.
MODALIDADES_ENTREGA = ("envio", "retira")


def _validar_modalidad(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if v not in MODALIDADES_ENTREGA:
        raise ValueError(f"modalidad_entrega inválida: {v!r}. Válidas: {', '.join(MODALIDADES_ENTREGA)}")
    return v


def _validar_grupo(v: Optional[str]) -> Optional[str]:
    """Normaliza y valida un grupo contra `pricing_service.GRUPOS`.

    Se reusa la constante en vez de repetir la lista acá: agregar una lista de
    precios tiene que ser una sola línea en `pricing_service`.
    """
    if v is None:
        return v
    normalizado = v.strip().lower()
    if not normalizado:
        return None
    if normalizado not in GRUPOS:
        raise ValueError(f"tipo inválido: {v!r}. Válidos: {', '.join(GRUPOS)}")
    return normalizado


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
    # 'envio' | 'retira'. None = que el backend lo resuelva a partir del cliente.
    modalidad_entrega: Optional[str] = None
    # Dirección de entrega elegida de la libreta del cliente. `direccion_entrega`
    # es el texto que queda guardado en el pedido (la foto del momento).
    direccion_entrega_id: Optional[int] = None
    direccion_entrega: Optional[str] = None  # envío: por defecto el domicilio del cliente, editable
    fecha_compromiso_pago: Optional[date] = None
    sociedad: Optional[str] = None  # "sanalle" | "farmacare" — solo facturación
    # Depósito por defecto del pedido: se aplica a las líneas que no traen uno propio.
    deposito_id: Optional[int] = None
    tipo_precio: Optional[str] = "minorista"
    # Qué clase de venta es, independiente de la lista con la que se cotizó.
    # None = que lo herede del `tipo` del cliente.
    tipo_cliente: Optional[str] = None
    # False = este pedido no escala solo a mayorista aunque supere el umbral.
    aplica_umbral_mayorista: bool = True
    # False = el pedido no compromete mercadería. Para operaciones de volumen que
    # se facturan antes de que entre el ingreso del proveedor.
    reserva_stock: bool = True

    @field_validator("modalidad_entrega")
    @classmethod
    def _chk_modalidad(cls, v: Optional[str]) -> Optional[str]:
        return _validar_modalidad(v)

    @field_validator("tipo_precio", "tipo_cliente")
    @classmethod
    def _chk_grupo(cls, v: Optional[str]) -> Optional[str]:
        return _validar_grupo(v)


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
    modalidad_entrega: Optional[str] = None
    direccion_entrega_id: Optional[int] = None
    direccion_entrega: Optional[str] = None
    fecha_compromiso_pago: Optional[date] = None
    sociedad: Optional[str] = None
    deposito_id: Optional[int] = None
    tipo_precio: Optional[str] = None
    tipo_cliente: Optional[str] = None
    aplica_umbral_mayorista: Optional[bool] = None
    vendedor_id: Optional[int] = None
    reserva_stock: Optional[bool] = None
    items: Optional[list[PedidoItemCreate]] = None
    # None = no tocar. Una lista (aunque sea vacía) reemplaza el plan entero.
    plan_pago: Optional[list[PedidoPlanPagoCreate]] = None

    @field_validator("modalidad_entrega")
    @classmethod
    def _chk_modalidad(cls, v: Optional[str]) -> Optional[str]:
        return _validar_modalidad(v)

    @field_validator("tipo_precio", "tipo_cliente")
    @classmethod
    def _chk_grupo(cls, v: Optional[str]) -> Optional[str]:
        return _validar_grupo(v)


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


class AvisoStock(BaseModel):
    """Una línea de la cotización que pide más de lo que hay disponible.

    Es un aviso, no un error: la cotización se guarda igual. Recién al
    confirmarla (borrador -> pendiente) el faltante frena la operación.
    """

    producto_id: int
    producto_nombre: str
    deposito_id: int
    deposito_nombre: Optional[str] = None
    pedido: str  # "5 caja(s)" — ya formateado con la unidad del producto
    disponible: str


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
    modalidad_entrega: str = "envio"
    fecha_compromiso_pago: Optional[date] = None
    despachado: bool = False
    sociedad: Optional[str] = None
    # Depósitos involucrados, ya resueltos a nombre. Normalmente uno solo; son
    # varios cuando una línea se tomó de otro depósito por falta de stock.
    depositos: list[str] = []
    tipo_precio: Optional[str] = None
    tipo_cliente: Optional[str] = None
    aplica_umbral_mayorista: bool = True
    # Alguna línea salió a un precio distinto del de lista. Informativo: no frena
    # el pedido, pero al confirmarlo se le exige una observación al vendedor.
    tiene_excepcion_precio: bool = False
    excepcion_precio_detalle: Optional[str] = None
    importe_total: float
    saldo_pendiente: float
    observacion: Optional[str] = None
    cliente_domicilio: Optional[str] = None
    cliente_telefono: Optional[str] = None
    cliente_localidad: Optional[str] = None
    # El id, además del nombre: al guardar una dirección nueva en la libreta desde
    # el pedido hace falta para geocodificarla (sin localidad el geocoder no ubica
    # nada y la entrega no aparece en el mapa de reparto).
    cliente_localidad_id: Optional[int] = None
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
    # `reserva_stock` es la intención ("este pedido descuenta stock"); esto es el
    # hecho ("hoy tiene mercadería comprometida"). Difieren mientras el pedido es
    # un borrador: el front lo necesita para no contar dos veces lo reservado.
    reserva_vigente: bool = True
    # Sólo se calcula en el detalle y al guardar (GET /{id}, POST, PUT). En el
    # listado va vacío a propósito: son cientos de pedidos y costaría una query
    # de stock por cada uno.
    avisos_stock: list[AvisoStock] = []
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

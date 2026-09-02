"""Schemas de las operaciones de stock: ajustes, motivos y toma de inventario."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Catálogo de motivos. `es_merma` separa lo que es pérdida de mercadería de lo
# que es una corrección administrativa: de ahí sale el reporte de mermas sin
# tener que interpretar texto libre.
MOTIVOS_AJUSTE: list[dict] = [
    {"codigo": "recuento_fisico", "label": "Recuento físico", "es_merma": False},
    {"codigo": "rotura", "label": "Rotura", "es_merma": True},
    {"codigo": "vencido", "label": "Vencido", "es_merma": True},
    {"codigo": "faltante", "label": "Faltante", "es_merma": True},
    {"codigo": "error_carga", "label": "Error de carga", "es_merma": False},
    {"codigo": "carga_inicial", "label": "Carga inicial", "es_merma": False},
]

MotivoAjuste = Literal[
    "recuento_fisico", "rotura", "vencido", "faltante", "error_carga", "carga_inicial"
]

MOTIVOS_LABEL = {m["codigo"]: m["label"] for m in MOTIVOS_AJUSTE}
MOTIVOS_MERMA = [m["codigo"] for m in MOTIVOS_AJUSTE if m["es_merma"]]


class AjusteStockRequest(BaseModel):
    """Ajuste de stock de un producto en un depósito.

    - `delta`: suma o resta lo indicado (las cantidades pueden ser negativas).
    - `absoluto`: deja el stock en el valor indicado. Es lo que se usa cuando se
      contó físicamente: el papel manda, no importa de cuánto era la diferencia.
    """

    producto_id: int
    deposito_id: int
    modo: Literal["delta", "absoluto"] = "delta"
    cantidad_cajas: int = 0
    cantidad_blisters: int = 0
    motivo: MotivoAjuste
    # 255 en la columna, pero los movimientos de inventario le anteponen
    # "Toma TOM-00001 · ", así que el texto del usuario se acota antes.
    observacion: Optional[str] = Field(None, max_length=200)

    @model_validator(mode="after")
    def _validar(self):
        if self.modo == "absoluto" and (self.cantidad_cajas < 0 or self.cantidad_blisters < 0):
            raise ValueError("En modo absoluto las cantidades no pueden ser negativas")
        if self.modo == "delta" and self.cantidad_cajas == 0 and self.cantidad_blisters == 0:
            raise ValueError("El ajuste no cambia nada: cargá cajas o blísters")
        return self


class MotivoAjusteResponse(BaseModel):
    codigo: str
    label: str
    es_merma: bool


class TomaInventarioFiltro(BaseModel):
    """Acota qué productos entran en el conteo. Vacío = todo el catálogo activo."""

    laboratorio_id: Optional[int] = None
    categoria: Optional[str] = None
    solo_con_stock: bool = False


class TomaInventarioCreate(BaseModel):
    deposito_id: int
    fecha: Optional[date] = None
    observacion: Optional[str] = None
    filtro: Optional[TomaInventarioFiltro] = None


class TomaConteoItem(BaseModel):
    producto_id: int
    contado_cajas: int = Field(0, ge=0)
    contado_blisters: int = Field(0, ge=0)


class TomaConteoRequest(BaseModel):
    items: list[TomaConteoItem]


class TomaAplicarRequest(BaseModel):
    observacion: Optional[str] = Field(None, max_length=200)
    # Si un producto se movió entre el conteo y la aplicación, el endpoint corta
    # con 409 salvo que alguien confirme explícitamente que igual se pisa.
    confirmar_movidas: bool = False


class TomaInventarioItemResponse(BaseModel):
    producto_id: int
    producto_codigo: Optional[str] = None
    producto_nombre: Optional[str] = None
    blisters_por_caja: Optional[int] = None
    esperado_cajas: int = 0
    esperado_blisters: int = 0
    contado_cajas: Optional[int] = None
    contado_blisters: Optional[int] = None
    # Stock de ahora: si difiere del esperado, el producto se movió durante el conteo.
    actual_cajas: int = 0
    actual_blisters: int = 0
    reservado_cajas: int = 0
    diferencia_blisters: Optional[int] = None
    movido_durante_conteo: bool = False


class TomaInventarioResumen(BaseModel):
    lineas: int = 0
    contadas: int = 0
    con_diferencia: int = 0
    delta_positivo_blisters: int = 0
    delta_negativo_blisters: int = 0
    movidas_durante_conteo: int = 0


class TomaInventarioResponse(BaseModel):
    id: int
    numero: str
    deposito_id: int
    deposito_nombre: Optional[str] = None
    estado: str
    origen: str
    fecha: date
    observacion: Optional[str] = None
    creado_por_nombre: Optional[str] = None
    aplicado_por_nombre: Optional[str] = None
    aplicada_at: Optional[datetime] = None
    created_at: datetime
    resumen: Optional[TomaInventarioResumen] = None


class MinimoItem(BaseModel):
    producto_id: int
    stock_minimo_cajas: int = Field(0, ge=0)
    stock_minimo_blisters: int = Field(0, ge=0)


class MinimosBulkRequest(BaseModel):
    items: list[MinimoItem]


class MinimosMasivoRequest(BaseModel):
    """Pone el mismo mínimo a todo un conjunto de productos.

    Es la salida rápida al arranque: hoy el mínimo está en cero en todos y
    cargarlo de a uno para 231 productos no es viable.
    """

    laboratorio_id: Optional[int] = None
    proveedor_id: Optional[int] = None
    categoria: Optional[str] = None
    producto_ids: Optional[list[int]] = None
    valor_cajas: int = Field(0, ge=0)
    valor_blisters: int = Field(0, ge=0)
    # Por defecto no pisa lo ya configurado a mano.
    solo_si_cero: bool = True

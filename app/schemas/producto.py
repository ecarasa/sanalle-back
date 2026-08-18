from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator


class ProductoBase(BaseModel):
    codigo: str
    nombre: str

    @field_validator("nombre")
    @classmethod
    def format_nombre(cls, v: str) -> str:
        return v.strip().title() if v else v

    foto_url: Optional[str] = None
    stock_a_cajas: int = 0
    stock_a_blisters: int = 0
    stock_b_cajas: int = 0
    stock_b_blisters: int = 0
    stock_minimo_cajas: int = 0
    stock_minimo_blisters: int = 0
    categoria_producto: Optional[str] = None
    presentacion: Optional[str] = None
    comprimidos_por_blister: Optional[int] = None
    blisters_por_caja: Optional[int] = None
    status: Optional[str] = None
    # Formato de venta habilitado por producto
    vende_caja: bool = True
    vende_blister: bool = False
    vende_comprimido: bool = False
    pvp: Optional[Decimal] = None
    fecha_act_pvp: Optional[datetime] = None
    margen_minorista: Optional[Decimal] = None
    margen_mayorista: Optional[Decimal] = None
    costo_porcentaje: Optional[Decimal] = None
    costo_neto: Optional[Decimal] = None
    costo_mas_iibb: Optional[Decimal] = None
    precio_venta_minorista: Optional[Decimal] = None
    precio_venta_mayorista: Optional[Decimal] = None
    # Lista comercio: margen None = el producto no tiene lista comercio
    margen_comercio: Optional[Decimal] = None
    precio_venta_comercio: Optional[Decimal] = None
    proveedor_id: Optional[int] = None
    laboratorio_id: Optional[int] = None
    url_pvp: Optional[str] = None
    pvp_descripcion: Optional[str] = None


class ProductoCreate(ProductoBase):
    pass


class ProductoUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    foto_url: Optional[str] = None
    stock_a_cajas: Optional[int] = None
    stock_a_blisters: Optional[int] = None
    stock_b_cajas: Optional[int] = None
    stock_b_blisters: Optional[int] = None
    stock_minimo_cajas: Optional[int] = None
    stock_minimo_blisters: Optional[int] = None
    categoria_producto: Optional[str] = None
    presentacion: Optional[str] = None
    comprimidos_por_blister: Optional[int] = None
    blisters_por_caja: Optional[int] = None
    status: Optional[str] = None
    vende_caja: Optional[bool] = None
    vende_blister: Optional[bool] = None
    vende_comprimido: Optional[bool] = None
    pvp: Optional[Decimal] = None
    fecha_act_pvp: Optional[datetime] = None
    margen_minorista: Optional[Decimal] = None
    margen_mayorista: Optional[Decimal] = None
    costo_porcentaje: Optional[Decimal] = None
    costo_neto: Optional[Decimal] = None
    costo_mas_iibb: Optional[Decimal] = None
    precio_venta_minorista: Optional[Decimal] = None
    precio_venta_mayorista: Optional[Decimal] = None
    margen_comercio: Optional[Decimal] = None
    precio_venta_comercio: Optional[Decimal] = None
    proveedor_id: Optional[int] = None
    laboratorio_id: Optional[int] = None
    url_pvp: Optional[str] = None
    pvp_descripcion: Optional[str] = None


class ProductoResponse(ProductoBase):
    id: int
    stock_reservado_a_cajas: int = 0
    stock_reservado_a_blisters: int = 0
    stock_reservado_b_cajas: int = 0
    stock_reservado_b_blisters: int = 0
    total_blisters_a: Optional[int] = None
    total_blisters_b: Optional[int] = None
    proveedor_nombre: Optional[str] = None
    laboratorio_nombre: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductoPublicResponse(BaseModel):
    """Respuesta del catálogo público.

    No expone columnas de precio: sólo el dict `precios`, que el router arma con las
    listas del grupo pedido. Antes se mandaban todas las listas a cualquiera que
    abriera el catálogo, así que un cliente minorista veía los precios mayoristas en
    la respuesta de red.
    """

    id: int
    codigo: str
    nombre: str
    foto_url: Optional[str] = None
    stock_a_cajas: int = 0
    stock_b_cajas: int = 0
    categoria_producto: Optional[str] = None
    presentacion: Optional[str] = None
    comprimidos_por_blister: Optional[int] = None
    blisters_por_caja: Optional[int] = None
    vende_caja: bool = True
    vende_blister: bool = False
    vende_comprimido: bool = False
    laboratorio_id: Optional[int] = None
    laboratorio_nombre: Optional[str] = None
    precios: dict[str, Optional[Decimal]] = {}

    model_config = {"from_attributes": True}


class PreciosBulkUpdateItem(BaseModel):
    producto_id: int
    pvp: Optional[Decimal] = None
    precio_venta_minorista: Optional[Decimal] = None
    precio_venta_mayorista: Optional[Decimal] = None
    precio_venta_comercio: Optional[Decimal] = None
    costo_mas_iibb: Optional[Decimal] = None


class PreciosBulkUpdate(BaseModel):
    items: list[PreciosBulkUpdateItem]


class PreciosPorcentajeUpdate(BaseModel):
    porcentaje: float
    campo: str = "pvp"  # "pvp" | "costo_porcentaje" | cualquier margen_* de LISTAS
    filtro: str = "todos"  # "todos" | "proveedor" | "categoria" | "laboratorio"
    filtro_id: Optional[int] = None

    @field_validator("campo")
    @classmethod
    def campo_valido(cls, v: str) -> str:
        from app.services.pricing_service import MARGEN_FIELDS

        permitidos = {"pvp", "costo_porcentaje", *MARGEN_FIELDS}
        if v not in permitidos:
            raise ValueError(f"campo inválido: {v}. Válidos: {sorted(permitidos)}")
        return v

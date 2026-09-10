"""Fuente única de verdad del cálculo de precios.

La fórmula estaba duplicada en el router de productos (PUT y bulk %), en el
scraper de PVP y en el formulario del frontend. Acá vive una sola vez:

    costo_neto     = pvp * (1 - costo_porcentaje/100)
    costo_mas_iibb = costo_neto * IIBB_FACTOR
    precio_venta_X = costo_mas_iibb * (1 + margen_X/100)

Regla que gobierna todo: un margen en None significa que el producto NO se
vende en esa lista, y su precio queda en None. Nunca `margen or 0` — eso le
inventaría un precio a productos que no tienen esa lista configurada.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Iterable, Mapping

if TYPE_CHECKING:
    from app.models.producto import Producto

IIBB_FACTOR = Decimal("1.03")  # 3% de IIBB sobre el costo neto
CENT = Decimal("0.01")


@dataclass(frozen=True)
class ListaPrecio:
    key: str  # "minorista" | "mayorista" | "comercio"
    label: str  # para la UI
    grupo: str  # "minorista" | "mayorista" | "comercio" == cliente.tipo / pedido.tipo_precio
    formato: str | None  # None | "blisteado" | "estuchado" | "hospitalario"
    margen_field: str
    precio_field: str
    excel_label: str  # encabezado en el Excel de precios (no cambiar: rompe imports viejos)


LISTAS: tuple[ListaPrecio, ...] = (
    ListaPrecio(
        key="minorista",
        label="Minorista",
        grupo="minorista",
        formato=None,
        margen_field="margen_minorista",
        precio_field="precio_venta_minorista",
        excel_label="P. Venta Minorista",
    ),
    ListaPrecio(
        key="mayorista",
        label="Mayorista",
        grupo="mayorista",
        formato=None,
        margen_field="margen_mayorista",
        precio_field="precio_venta_mayorista",
        excel_label="P. Venta Mayorista",
    ),
    ListaPrecio(
        key="comercio",
        label="Comercio",
        grupo="comercio",
        formato=None,
        margen_field="margen_comercio",
        precio_field="precio_venta_comercio",
        excel_label="P. Comercio",
    ),
)

LISTAS_BY_KEY: dict[str, ListaPrecio] = {lista.key: lista for lista in LISTAS}
GRUPOS: tuple[str, ...] = ("minorista", "mayorista", "comercio")

MARGEN_FIELDS: tuple[str, ...] = tuple(lista.margen_field for lista in LISTAS)
PRECIO_FIELDS: tuple[str, ...] = tuple(lista.precio_field for lista in LISTAS)

# Campos que, al tocarse, obligan a recalcular los precios de venta.
PRICE_TRIGGER_FIELDS: frozenset[str] = frozenset({"pvp", "costo_porcentaje", *MARGEN_FIELDS})


def listas_de(grupo: str) -> tuple[ListaPrecio, ...]:
    """Listas que aplican a un grupo: 1 para minorista/mayorista, 3 para comercio."""
    return tuple(lista for lista in LISTAS if lista.grupo == grupo)


def lista_de(grupo: str, formato: str | None = None) -> ListaPrecio | None:
    """Resuelve la lista concreta de un pedido/ítem: (grupo, formato) -> lista."""
    candidatas = listas_de(grupo)
    if not candidatas:
        return None
    if len(candidatas) == 1:
        return candidatas[0]
    for lista in candidatas:
        if lista.formato == formato:
            return lista
    return None


def precio_esperado(producto: "Producto", grupo: str, unidad_venta: str = "caja") -> Decimal | None:
    """Precio de lista que le corresponde a una línea de pedido.

    Es el precio contra el que se detecta una excepción. Tiene que vivir acá y no
    en el router porque el cliente manda `precio_lista` por su cuenta y, cuando el
    vendedor pisa el precio a mano, el form conserva el viejo "de referencia":
    comparar contra ese valor no detectaría nada.

    Espeja `precioBasePorUnidad` de frontend/src/lib/ventas.ts — el blíster sale
    de dividir el precio de caja, y si el producto no fracciona cae al de caja.
    None = el producto no se vende en esa lista.
    """
    lista = lista_de(grupo)
    if lista is None:
        return None
    base = _dec(getattr(producto, lista.precio_field, None))
    if base is None:
        return None
    if unidad_venta == "blister":
        por_caja = producto.get_blisters_por_caja
        if por_caja and por_caja > 1:
            return _q(base / Decimal(por_caja))
    return _q(base)


def _dec(value) -> Decimal | None:
    """Convierte a Decimal preservando None. Un string vacío también es None."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calcular_costos(pvp, costo_porcentaje) -> dict[str, Decimal]:
    """Devuelve {} si falta pvp o costo_porcentaje; si no, costo_neto y costo_mas_iibb."""
    pvp_d = _dec(pvp)
    costo_d = _dec(costo_porcentaje)
    if pvp_d is None or costo_d is None:
        return {}
    costo_neto = pvp_d * (Decimal("1") - costo_d / Decimal("100"))
    return {
        "costo_neto": _q(costo_neto),
        "costo_mas_iibb": _q(costo_neto * IIBB_FACTOR),
    }


def calcular_precio(costo_mas_iibb, margen) -> Decimal | None:
    """None si no hay costo o el margen no está seteado (la lista no existe para ese producto)."""
    costo_d = _dec(costo_mas_iibb)
    margen_d = _dec(margen)
    if costo_d is None or margen_d is None:
        return None
    return _q(costo_d * (Decimal("1") + margen_d / Decimal("100")))


def calcular_todo(pvp, costo_porcentaje, margenes: Mapping[str, object]) -> dict[str, Decimal]:
    """Función pura. `margenes` viene keyed por margen_field.

    Devuelve costo_neto, costo_mas_iibb y sólo los precio_field cuyo margen esté seteado.
    """
    resultado = calcular_costos(pvp, costo_porcentaje)
    if not resultado:
        return resultado

    costo_mas_iibb = resultado["costo_mas_iibb"]
    for lista in LISTAS:
        precio = calcular_precio(costo_mas_iibb, margenes.get(lista.margen_field))
        if precio is not None:
            resultado[lista.precio_field] = precio
    return resultado


def computar_para_update(producto: "Producto", update_data: Mapping[str, object]) -> dict[str, Decimal]:
    """Campos a mergear en update_data tras un PUT/POST de producto.

    Mergea el estado actual del producto con lo que llega en el body y recalcula.
    Si el body no toca ningún campo que influya en el precio, no recalcula nada.
    """
    if not PRICE_TRIGGER_FIELDS & set(update_data.keys()):
        return {}

    def _valor(campo: str):
        if campo in update_data:
            return update_data[campo]
        return getattr(producto, campo, None)

    margenes = {campo: _valor(campo) for campo in MARGEN_FIELDS}
    return calcular_todo(_valor("pvp"), _valor("costo_porcentaje"), margenes)


def aplicar_a_producto(producto: "Producto") -> None:
    """Recalcula in-place desde el estado actual del ORM (bulk %, scraper, import Excel).

    Los precios de las listas sin margen se ponen explícitamente en None, para que
    borrar un margen borre también su precio.
    """
    margenes = {campo: getattr(producto, campo, None) for campo in MARGEN_FIELDS}
    calculado = calcular_todo(producto.pvp, producto.costo_porcentaje, margenes)
    if not calculado:
        return

    producto.costo_neto = calculado["costo_neto"]
    producto.costo_mas_iibb = calculado["costo_mas_iibb"]
    for lista in LISTAS:
        setattr(producto, lista.precio_field, calculado.get(lista.precio_field))


def precios_de(producto: "Producto", grupo: str) -> dict[str, Decimal | None]:
    """{lista_key: precio} para las listas de un grupo. Usado por el catálogo público."""
    return {
        lista.key: getattr(producto, lista.precio_field, None)
        for lista in listas_de(grupo)
    }

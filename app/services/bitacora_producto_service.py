"""Registro de quién cambió qué en la ficha de un producto.

Se escribe desde el router y no con listeners de SQLAlchemy por la misma razón
que la bitácora de pedidos: los listeners no tienen acceso al usuario
autenticado, y varias de las escrituras interesantes (aumentos masivos,
importaciones) son UPDATEs en bloque que a nivel ORM no se ven.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bitacora_producto import BitacoraProducto
from app.models.producto import Producto
from app.models.user import User

# Qué se audita. Deliberadamente NO están los precios de venta derivados
# (`precio_venta_*`): se recalculan solos a partir de pvp/costo/márgenes, así que
# registrarlos llenaría la bitácora de ruido que nadie cambió a mano.
CAMPOS_AUDITADOS: tuple[str, ...] = (
    "codigo",
    "nombre",
    "categoria_producto",
    "presentacion",
    "laboratorio_id",
    "proveedor_id",
    "pvp",
    "costo_neto",
    "costo_porcentaje",
    "costo_mas_iibb",
    "margen_minorista",
    "margen_mayorista",
    "margen_comercio",
    "stock_minimo_cajas",
    "stock_minimo_blisters",
    "blisters_por_caja",
    "comprimidos_por_blister",
    "vende_caja",
    "vende_blister",
    "vende_comprimido",
    "status",
    "activo",
)

ETIQUETAS = {
    "codigo": "Código",
    "nombre": "Nombre",
    "categoria_producto": "Categoría",
    "presentacion": "Presentación",
    "laboratorio_id": "Laboratorio",
    "proveedor_id": "Proveedor",
    "pvp": "PVP",
    "costo_neto": "Costo neto",
    "costo_porcentaje": "Costo %",
    "costo_mas_iibb": "Costo + IIBB",
    "margen_minorista": "Margen minorista",
    "margen_mayorista": "Margen mayorista",
    "margen_comercio": "Margen comercio",
    "stock_minimo_cajas": "Mínimo (cajas)",
    "stock_minimo_blisters": "Mínimo (blísters)",
    "blisters_por_caja": "Blísters por caja",
    "comprimidos_por_blister": "Comprimidos por blíster",
    "vende_caja": "Vende por caja",
    "vende_blister": "Vende por blíster",
    "vende_comprimido": "Vende por comprimido",
    "status": "Estado",
    "activo": "Activo",
}


def nuevo_grupo_id() -> str:
    """Agrupa en una sola edición todos los campos tocados por un request."""
    return str(uuid.uuid4())


def _fmt(valor) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, Decimal):
        # Sin ceros de más: 0.25 y no 0.250000.
        return format(valor.normalize(), "f")
    return str(valor)


def snapshot(producto: Producto) -> dict[str, str | None]:
    """Foto de los campos auditados, para comparar después de escribir."""
    return {campo: _fmt(getattr(producto, campo, None)) for campo in CAMPOS_AUDITADOS}


def _nombre_de(usuario: User | None) -> str | None:
    if usuario is None:
        return None
    return usuario.nombre_completo or usuario.username


def registrar_cambios(
    db: AsyncSession,
    *,
    producto: Producto,
    antes: dict[str, str | None],
    usuario: User | None,
    origen: str = "ficha",
    observacion: str | None = None,
    grupo_id: str | None = None,
) -> int:
    """Escribe una fila por campo que efectivamente cambió. Devuelve cuántas.

    No hace commit: se suma a la transacción del router, así un cambio que
    después falla no deja una bitácora que miente.
    """
    despues = snapshot(producto)
    grupo = grupo_id or nuevo_grupo_id()
    filas = 0
    for campo, anterior in antes.items():
        nuevo = despues.get(campo)
        if anterior == nuevo:
            continue
        db.add(
            BitacoraProducto(
                producto_id=producto.id,
                producto_codigo=producto.codigo,
                producto_nombre=producto.nombre,
                usuario_id=usuario.id if usuario else None,
                usuario_nombre=_nombre_de(usuario),
                accion="modificacion",
                origen=origen,
                campo=campo,
                valor_anterior=anterior,
                valor_nuevo=nuevo,
                grupo_id=grupo,
                observacion=observacion,
            )
        )
        filas += 1
    return filas


def registrar_alta(
    db: AsyncSession,
    *,
    producto: Producto,
    usuario: User | None,
    origen: str = "ficha",
    observacion: str | None = None,
) -> None:
    db.add(
        BitacoraProducto(
            producto_id=producto.id,
            producto_codigo=producto.codigo,
            producto_nombre=producto.nombre,
            usuario_id=usuario.id if usuario else None,
            usuario_nombre=_nombre_de(usuario),
            accion="alta",
            origen=origen,
            grupo_id=nuevo_grupo_id(),
            observacion=observacion,
        )
    )


def registrar_baja(
    db: AsyncSession,
    *,
    producto: Producto,
    usuario: User | None,
    origen: str = "ficha",
    observacion: str | None = None,
) -> None:
    db.add(
        BitacoraProducto(
            producto_id=producto.id,
            producto_codigo=producto.codigo,
            producto_nombre=producto.nombre,
            usuario_id=usuario.id if usuario else None,
            usuario_nombre=_nombre_de(usuario),
            accion="baja",
            origen=origen,
            grupo_id=nuevo_grupo_id(),
            observacion=observacion,
        )
    )


def registrar_campo(
    db: AsyncSession,
    *,
    producto_id: int,
    producto_codigo: str | None,
    producto_nombre: str | None,
    campo: str,
    anterior,
    nuevo,
    usuario: User | None,
    origen: str,
    observacion: str | None = None,
    grupo_id: str | None = None,
) -> bool:
    """Registra un campo suelto. Para las escrituras en bloque, donde no se
    carga el producto entero sino sólo el valor que se está por pisar."""
    ant, nue = _fmt(anterior), _fmt(nuevo)
    if ant == nue:
        return False
    db.add(
        BitacoraProducto(
            producto_id=producto_id,
            producto_codigo=producto_codigo,
            producto_nombre=producto_nombre,
            usuario_id=usuario.id if usuario else None,
            usuario_nombre=_nombre_de(usuario),
            accion="modificacion",
            origen=origen,
            campo=campo,
            valor_anterior=ant,
            valor_nuevo=nue,
            grupo_id=grupo_id or nuevo_grupo_id(),
            observacion=observacion,
        )
    )
    return True

from __future__ import annotations
from pydantic import BaseModel


class PagosPorPedidoRow(BaseModel):
    c_nombre: str
    a_idpedido: int
    pe_fecha: str
    pe_fechaentrega: str | None
    pe_importetotal: float
    a_idpago: int
    pa_receptor: str | None
    tp_nombre: str
    pa_fecharecep: str
    pa_chbanco: str | None
    pa_chvto: str | None
    a_importe: float
    a_saldo: float


class PedidoItemComisionDetalle(BaseModel):
    producto_id: int
    producto_nombre: str
    cantidad: int
    precio_unitario: float
    precio_total: float
    descuento_porcentaje: float
    categoria: str
    comision_porcentaje: float
    comision_calculada: float


class PedidoComisionDetalle(BaseModel):
    pedido_id: int
    numero_pedido: str
    cliente_nombre: str
    fecha_entrega: str | None
    total_otc: float
    total_generico: float
    total_pedido: float
    comision_calculada: float
    items: list[PedidoItemComisionDetalle] = []


class VendedorComisionRow(BaseModel):
    vendedor_id: int
    vendedor_nombre: str
    comision_generico_pct: float
    comision_otc_pct: float
    total_ventas_otc: float
    total_ventas_generico: float
    comision_otc_monto: float
    comision_generico_monto: float
    total_comision: float
    num_pedidos: int
    pedidos: list[PedidoComisionDetalle]


class HistorialPvpRow(BaseModel):
    id: int
    fecha_cambio: str
    pvp_anterior: float | None
    pvp_nuevo: float
    variacion_porcentaje: float | None


class HistorialPvpResponse(BaseModel):
    producto_id: int
    producto_nombre: str
    producto_codigo: str
    historial: list[HistorialPvpRow]

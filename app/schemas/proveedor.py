import enum
from pydantic import BaseModel, field_validator
from typing import Optional
from decimal import Decimal
from datetime import datetime, date


class TipoProveedor(str, enum.Enum):
    LABORATORIO = "LABORATORIO"
    DROGUERIA = "DROGUERIA"


class PagoPendienteInfo(BaseModel):
    id: int
    numero: str
    numero_comprobante: str
    fecha: date
    importe_total: Decimal
    saldo_pendiente: Decimal
    fecha_vencimiento: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NotaProveedorInfo(BaseModel):
    id: int
    numero: str
    tipo: str  # "credito" | "debito"
    fecha: date
    importe_total: Decimal

    model_config = {"from_attributes": True}


class ProveedorBase(BaseModel):
    nombre: str
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    tipo: TipoProveedor = TipoProveedor.LABORATORIO
    plazo_pago: int = 30
    deuda_inicial: Decimal = Decimal("0")
    contacto_nombre: Optional[str] = None
    contacto_telefono: Optional[str] = None
    contacto_email: Optional[str] = None
    descuento: Decimal = Decimal("0")
    cashback: Decimal = Decimal("0")

    @field_validator("nombre")
    @classmethod
    def format_nombre(cls, v: str) -> str:
        return v.strip().title() if v else v

    @field_validator("direccion")
    @classmethod
    def format_direccion(cls, v: str | None) -> str | None:
        return v.strip().title() if v else v


class ProveedorCreate(ProveedorBase):
    pass


class ProveedorUpdate(BaseModel):
    nombre: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    tipo: Optional[TipoProveedor] = None
    plazo_pago: Optional[int] = None
    deuda_inicial: Optional[Decimal] = None
    contacto_nombre: Optional[str] = None
    contacto_telefono: Optional[str] = None
    contacto_email: Optional[str] = None
    descuento: Optional[Decimal] = None
    cashback: Optional[Decimal] = None
    activo: Optional[bool] = None


class PagoIngresoItem(BaseModel):
    id: int
    monto: Decimal  # monto a pagar (post-descuento)


class PagoDeudaProveedorRequest(BaseModel):
    ingresos: list[PagoIngresoItem]
    metodo_pago: str
    aplicar_descuento: bool = False
    aplicar_cashback: bool = False
    pago_id: Optional[int] = None
    fecha: Optional[datetime] = None


class ProveedorResponse(ProveedorBase):
    id: int
    activo: bool
    saldo_remito: Decimal
    saldo_factura: Decimal
    created_at: datetime
    updated_at: datetime

    # Computed fields populated by the router
    saldo_pendiente_total: Decimal = Decimal("0")
    pagos_pendientes: list[PagoPendienteInfo] = []
    notas: list[NotaProveedorInfo] = []
    total_notas_credito: Decimal = Decimal("0")

    model_config = {"from_attributes": True}

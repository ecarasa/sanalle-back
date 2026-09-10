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


def _normalizar_cbu(v: Optional[str]) -> Optional[str]:
    """El CBU argentino son 22 dígitos. Se guarda sólo con dígitos y se valida el
    largo, porque un CBU mal tipeado no falla acá sino en el banco, con la
    transferencia ya armada y la plata en camino a ningún lado."""
    if v is None:
        return v
    limpio = "".join(ch for ch in v if ch.isdigit())
    if not limpio:
        return None
    if len(limpio) != 22:
        raise ValueError(f"El CBU tiene que tener 22 dígitos (tiene {len(limpio)}).")
    return limpio


def _etiqueta_limpia(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    limpio = v.strip()
    if not limpio:
        raise ValueError("La etiqueta es obligatoria: es cómo se reconoce la cuenta al pagar.")
    return limpio


class ProveedorCuentaBase(BaseModel):
    """Una cuenta bancaria de la libreta del proveedor: a dónde se le paga.

    No confundir con `cuenta_id` de un pago, que es la cuenta de SANALLE de la que
    sale la plata. Esta es la de la contraparte.
    """

    etiqueta: str
    banco: Optional[str] = None
    titular: Optional[str] = None
    cuit: Optional[str] = None
    numero_cuenta: Optional[str] = None
    cbu: Optional[str] = None
    alias: Optional[str] = None
    observacion: Optional[str] = None
    es_default: bool = False

    @field_validator("etiqueta")
    @classmethod
    def _chk_etiqueta(cls, v: str) -> str:
        return _etiqueta_limpia(v)

    @field_validator("cbu")
    @classmethod
    def _chk_cbu(cls, v: Optional[str]) -> Optional[str]:
        return _normalizar_cbu(v)


class ProveedorCuentaCreate(ProveedorCuentaBase):
    pass


class ProveedorCuentaUpdate(BaseModel):
    etiqueta: Optional[str] = None
    banco: Optional[str] = None
    titular: Optional[str] = None
    cuit: Optional[str] = None
    numero_cuenta: Optional[str] = None
    cbu: Optional[str] = None
    alias: Optional[str] = None
    observacion: Optional[str] = None
    es_default: Optional[bool] = None
    activo: Optional[bool] = None

    @field_validator("etiqueta")
    @classmethod
    def _chk_etiqueta(cls, v: Optional[str]) -> Optional[str]:
        return _etiqueta_limpia(v)

    @field_validator("cbu")
    @classmethod
    def _chk_cbu(cls, v: Optional[str]) -> Optional[str]:
        return _normalizar_cbu(v)


class ProveedorCuentaResponse(ProveedorCuentaBase):
    id: int
    proveedor_id: int
    activo: bool

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
    cashback: Decimal = Decimal("0")  # deprecado
    cashback_parcial: Decimal = Decimal("0")
    cashback_total: Decimal = Decimal("0")

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
    cashback_parcial: Optional[Decimal] = None
    cashback_total: Optional[Decimal] = None
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
    cuenta_id: Optional[int] = None  # cuenta de la empresa desde donde sale la plata
    # Cuenta del PROVEEDOR a la que se transfirió. Queda registrada en el pago para
    # poder contestar después "¿a qué CBU le pagamos esta factura?".
    proveedor_cuenta_id: Optional[int] = None
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
    cashback_pendiente: Decimal = Decimal("0")
    cuentas: list[ProveedorCuentaResponse] = []

    model_config = {"from_attributes": True}

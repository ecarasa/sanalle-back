import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Float,
    func,
)

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EstadoDespacho(enum.Enum):
    # La cotización: el pedido que el vendedor todavía está cargando. NO reserva
    # stock —se puede cotizar por más de lo que hay, y el sistema avisa— y no es
    # una venta: no suma deuda, ni facturación, ni dashboard. Depósito no lo ve.
    # La mercadería se compromete recién al finalizarlo (`borrador -> pendiente`),
    # que es el único momento en que un faltante puede frenar la operación.
    borrador = "borrador"
    pendiente = "pendiente"
    en_preparacion = "en_preparacion"
    listo_para_despacho = "listo_para_despacho"
    en_camino = "en_camino"
    entregado = "entregado"
    cancelado = "cancelado"

class EstadoPago(enum.Enum):
    pendiente = "pendiente"
    pagado = "pagado"
    cancelado = "cancelado"
    parcial = "parcial"

class TipoDocumento(enum.Enum):
    remito = "remito"
    factura = "factura"


class ModalidadEntrega(str, enum.Enum):
    """Cómo llega la mercadería al cliente. Define qué remito se imprime."""
    envio = "envio"      # se despacha a la dirección de entrega del pedido
    retira = "retira"    # el cliente pasa a buscarlo por el depósito


# Estados que no representan una venta cerrable: se excluyen de la deuda del
# cliente, de la cuenta corriente, del dashboard y de la imputación de pagos.
ESTADOS_NO_COMPUTABLES = (EstadoDespacho.borrador, EstadoDespacho.cancelado)


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero_pedido: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id"), nullable=False, index=True
    )
    vendedor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    shipping_status: Mapped[EstadoDespacho] = mapped_column(
        Enum(EstadoDespacho, name="estadodespacho", native_enum=True),
        default=EstadoDespacho.borrador,
        server_default="borrador",
        nullable=False,
        index=True,
    )
    payment_status: Mapped[EstadoPago] = mapped_column(
        Enum(EstadoPago, name="estadopagopedido", native_enum=True),
        default=EstadoPago.pendiente,
        server_default="pendiente",
        nullable=False,
        index=True,
    )
    tipo_documento: Mapped[TipoDocumento | None] = mapped_column(
        Enum(TipoDocumento, name="tipodocumento", native_enum=True),
        nullable=True,
        index=True,
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fecha_entrega: Mapped[date | None] = mapped_column(Date, nullable=True)
    transporte: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Modalidad de entrega. Es columna propia y no se deduce del texto de
    # `transporte` ("Retira el cliente" es uno de los valores sugeridos): de esto
    # dependen la dirección que sale impresa y cuántas copias se emiten, y un
    # typo en un campo libre no puede decidir eso.
    modalidad_entrega: Mapped[str] = mapped_column(
        String(20),
        default=ModalidadEntrega.envio.value,
        server_default="envio",
        nullable=False,
        index=True,
    )
    fecha_compromiso_pago: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Cómo se va a cobrar: efectivo | transferencia | cheque. Es una indicación
    # para cobranza, no registra el cobro. Reemplaza al `plan_pago` multi-tramo,
    # que pedía importe y cuenta por cada parte y nadie completaba.
    # Los valores son los de `TipoPago` para que, cuando se registre el pago de
    # verdad, la forma coincida y no haya que traducir entre dos vocabularios.
    forma_pago: Mapped[str | None] = mapped_column(String(30), nullable=True)
    despachado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    sociedad: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "sanalle" | "farmacare"
    importe_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    # Con qué lista se cotizó este pedido.
    tipo_precio: Mapped[str | None] = mapped_column(
        String(20), default="minorista", server_default="minorista", nullable=True
    )
    # Qué tipo de venta es. Va aparte de `tipo_precio` a propósito: una venta
    # minorista puede facturarse con precio mayorista por volumen o por excepción,
    # y para las estadísticas comerciales lo que importa es qué clase de cliente
    # compró, no qué columna de precios se usó. Arranca del `tipo` del cliente.
    tipo_cliente: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # False = este pedido no escala solo a mayorista aunque supere el umbral.
    # En afirmativo, como `reserva_stock`, para que el tilde se lea sin negar dos veces.
    aplica_umbral_mayorista: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    # Alguna línea se facturó a un precio distinto del de lista. Se persiste en vez
    # de calcularse porque el listado tiene que poder FILTRAR por él, y en SQL sería
    # una subconsulta correlacionada sobre pedido_items ⋈ productos por cada fila.
    tiene_excepcion_precio: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False, index=True
    )
    # El "qué": resumen autogenerado de los desvíos. El "por qué" es `observacion`,
    # que se le exige al vendedor al confirmar.
    excepcion_precio_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    saldo_pendiente: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # DB-10: Repartidor assignment
    repartidor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )

    # Geolocation snapshot. `direccion_entrega` es texto a propósito: es la foto
    # de la dirección al momento del pedido, y de ahí salen el remito y la hoja
    # de ruta. `direccion_entrega_id` apunta a la fila de la libreta del cliente
    # de la que se copió, para poder mostrar cuál se eligió.
    direccion_entrega_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cliente_direcciones.id", ondelete="SET NULL"), nullable=True
    )
    direccion_entrega: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latitud: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitud: Mapped[float | None] = mapped_column(Float, nullable=True)

    bultos: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0, server_default="0")

    # Pedido que se carga sin comprometer mercadería: se usa en operaciones de
    # volumen que se facturan antes de que entre el ingreso. Con esto en False no
    # se reserva nada al crear ni se consume/devuelve al entregar o cancelar.
    # Cuando la mercadería entra, se vuelve a poner en True y ahí sí se reserva.
    reserva_stock: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )


    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    cliente: Mapped["Cliente"] = relationship(  # noqa: F821
        "Cliente", back_populates="pedidos", lazy="noload"
    )
    vendedor: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="pedidos", lazy="noload", foreign_keys=[vendedor_id]
    )
    repartidor: Mapped["User | None"] = relationship(  # noqa: F821
        "User", lazy="noload", foreign_keys=[repartidor_id]
    )
    items: Mapped[list["PedidoItem"]] = relationship(  # noqa: F821
        "PedidoItem",
        back_populates="pedido",
        lazy="noload",
        cascade="all, delete-orphan",
    )
    # Sin `delete-orphan` a propósito: con `lazy="noload"` la colección se ve
    # vacía aunque en la base haya filas, y el cascade de huérfanos las borraría
    # en cualquier flush que no la haya cargado antes. El borrado del pedido lo
    # cubre el ON DELETE CASCADE de la FK; el reemplazo del plan se hace con un
    # DELETE explícito en el router.
    plan_pago: Mapped[list["PedidoPlanPago"]] = relationship(  # noqa: F821
        "PedidoPlanPago",
        back_populates="pedido",
        lazy="noload",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Pedido(id={self.id}, numero={self.numero_pedido!r}, shipping_status={self.shipping_status.value!r}, payment_status={self.payment_status.value!r})>"

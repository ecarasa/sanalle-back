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
    # El pedido que el vendedor todavía está cargando. Reserva stock igual que
    # `pendiente` (para avisar en el momento si no alcanza), pero no es una venta:
    # no suma deuda, ni facturación, ni dashboard. Depósito no lo ve hasta que
    # ventas lo finaliza.
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
    fecha_compromiso_pago: Mapped[date | None] = mapped_column(Date, nullable=True)
    despachado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    sociedad: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "sanalle" | "farmacare"
    importe_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0", nullable=False
    )
    tipo_precio: Mapped[str | None] = mapped_column(
        String(20), default="minorista", server_default="minorista", nullable=True
    )
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

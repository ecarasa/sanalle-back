from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import event, inspect

from app.core.database import Base


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    foto_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # DB-02: Fractional Dual Stock fields
    stock_a_cajas: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    stock_a_blisters: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    stock_reservado_a_cajas: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    stock_reservado_a_blisters: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    stock_b_cajas: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    stock_b_blisters: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    stock_reservado_b_cajas: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    stock_reservado_b_blisters: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    stock_minimo_cajas: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    stock_minimo_blisters: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)


    categoria_producto: Mapped[str | None] = mapped_column(String(255), nullable=True)
    presentacion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    comprimidos_por_blister: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blisters_por_caja: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Formato de venta: en qué unidades se puede vender este producto.
    # Ej. azitromicina cargada como expendedor pero vendida SOLO por blíster:
    # vende_caja=False, vende_blister=True. Default: solo caja (comportamiento actual).
    vende_caja: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    vende_blister: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    vende_comprimido: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    pvp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    fecha_act_pvp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    
    margen_minorista: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    
    margen_mayorista: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    
    costo_porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    costo_neto: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    costo_mas_iibb: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    precio_venta_minorista: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    precio_venta_mayorista: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Lista COMERCIO: un único margen y precio (igual que minorista/mayorista).
    # Margen en NULL = el producto no tiene lista comercio (el catálogo muestra "—").
    margen_comercio: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    precio_venta_comercio: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    

    url_pvp: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Opción de Alfabeta elegida a mano (la descripción/presentación de la fila).
    # El scraper automático prioriza esta opción al re-scrapear, así no vuelve a
    # depender de adivinar por la presentación cuando la página trae varias.
    pvp_descripcion: Mapped[str | None] = mapped_column(String(500), nullable=True)

    proveedor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("proveedores.id"), nullable=True, index=True
    )
    laboratorio_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("laboratorios.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    proveedor: Mapped["Proveedor"] = relationship("Proveedor", lazy="noload")  # noqa: F821
    laboratorio: Mapped["Laboratorio"] = relationship("Laboratorio", lazy="noload")  # noqa: F821
    historial_pvp: Mapped[list["HistorialPvpProducto"]] = relationship("HistorialPvpProducto", back_populates="producto", cascade="all, delete-orphan")  # noqa: F821
    stocks_deposito: Mapped[list["StockProductoDeposito"]] = relationship("StockProductoDeposito", cascade="all, delete-orphan", lazy="selectin")  # noqa: F821


    # Helpers matematicos para stock fraccionario
    @property
    def get_blisters_por_caja(self) -> int:
        return self.blisters_por_caja if self.blisters_por_caja and self.blisters_por_caja > 0 else 1

    @property
    def total_blisters_a(self) -> int:
        return (self.stock_a_cajas * self.get_blisters_por_caja) + self.stock_a_blisters

    @property
    def total_blisters_b(self) -> int:
        return (self.stock_b_cajas * self.get_blisters_por_caja) + self.stock_b_blisters

    def modify_stock_a(self, cajas: int, blisters: int, is_reservation: bool = False):
        change = (cajas * self.get_blisters_por_caja) + blisters
        if is_reservation:
            curr = (self.stock_reservado_a_cajas * self.get_blisters_por_caja) + self.stock_reservado_a_blisters
            new_val = curr + change
            self.stock_reservado_a_cajas = new_val // self.get_blisters_por_caja
            self.stock_reservado_a_blisters = new_val % self.get_blisters_por_caja
        else:
            curr = self.total_blisters_a
            new_val = curr + change
            self.stock_a_cajas = new_val // self.get_blisters_por_caja
            self.stock_a_blisters = new_val % self.get_blisters_por_caja

    def modify_stock_b(self, cajas: int, blisters: int, is_reservation: bool = False):
        change = (cajas * self.get_blisters_por_caja) + blisters
        if is_reservation:
            curr = (self.stock_reservado_b_cajas * self.get_blisters_por_caja) + self.stock_reservado_b_blisters
            new_val = curr + change
            self.stock_reservado_b_cajas = new_val // self.get_blisters_por_caja
            self.stock_reservado_b_blisters = new_val % self.get_blisters_por_caja
        else:
            curr = self.total_blisters_b
            new_val = curr + change
            self.stock_b_cajas = new_val // self.get_blisters_por_caja
            self.stock_b_blisters = new_val % self.get_blisters_por_caja

    @property
    def rentabilidad(self) -> Decimal | None:
        if self.costo_mas_iibb and self.costo_mas_iibb > 0 and self.precio_venta_minorista:
            return ((self.precio_venta_minorista - self.costo_mas_iibb) / self.costo_mas_iibb) * 100
        return None

    def __repr__(self) -> str:
        return f"<Producto(id={self.id}, codigo={self.codigo!r}, nombre={self.nombre!r})>"


@event.listens_for(Producto, "before_update")
def pvp_history_listener(mapper, connection, target):
    state = inspect(target)
    history = state.get_history("pvp", True)

    if history.has_changes():
        old_value = history.deleted[0] if history.deleted else None
        new_value = history.added[0] if history.added else None

        # Only record if the new value is actually different (avoid redundant entries)
        if new_value != old_value:
            # We use a connection to insert directly because we are inside a flush
            from app.models.historial_pvp_producto import HistorialPvpProducto
            
            connection.execute(
                HistorialPvpProducto.__table__.insert().values(
                    producto_id=target.id,
                    pvp_anterior=old_value,
                    pvp_nuevo=new_value,
                    fecha_cambio=datetime.now()
                )
            )
            # Update fecha_act_pvp automatically
            target.fecha_act_pvp = datetime.now()


@event.listens_for(Producto, "after_insert")
def pvp_initial_history_listener(mapper, connection, target):
    if target.pvp is not None:
        from app.models.historial_pvp_producto import HistorialPvpProducto
        connection.execute(
            HistorialPvpProducto.__table__.insert().values(
                producto_id=target.id,
                pvp_anterior=None,
                pvp_nuevo=target.pvp,
                fecha_cambio=datetime.now()
            )
        )


# --- Dual-write: sincroniza el stock por depósito (tabla nueva) cuando cambia A/B ---

_STOCK_FIELDS = ("stock_a_cajas", "stock_a_blisters", "stock_b_cajas", "stock_b_blisters")


def _sync_stock_deposito(connection, target):
    """Upsert de los depósitos legacy (a/b) con el stock actual A/B del producto."""
    from sqlalchemy import text
    for legacy, cajas, blisters in (
        ("a", target.stock_a_cajas, target.stock_a_blisters),
        ("b", target.stock_b_cajas, target.stock_b_blisters),
    ):
        connection.execute(
            text(
                """
                INSERT INTO stock_producto_deposito (producto_id, deposito_id, cajas, blisters)
                SELECT :pid, d.id, :cajas, :blisters FROM depositos d WHERE d.stock_legacy = :legacy
                ON CONFLICT (producto_id, deposito_id)
                DO UPDATE SET cajas = EXCLUDED.cajas, blisters = EXCLUDED.blisters
                """
            ),
            {"pid": target.id, "cajas": cajas, "blisters": blisters, "legacy": legacy},
        )


@event.listens_for(Producto, "before_update")
def sync_stock_deposito_on_update(mapper, connection, target):
    state = inspect(target)
    if any(state.get_history(f, True).has_changes() for f in _STOCK_FIELDS):
        _sync_stock_deposito(connection, target)


@event.listens_for(Producto, "after_insert")
def sync_stock_deposito_on_insert(mapper, connection, target):
    _sync_stock_deposito(connection, target)

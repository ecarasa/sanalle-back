import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.core.database import Base

# Import all models so that Base.metadata contains all table definitions
from app.models.user import User  # noqa: F401
from app.models.cliente import Cliente  # noqa: F401
from app.models.producto import Producto  # noqa: F401
from app.models.pedido import Pedido  # noqa: F401
from app.models.pedido_item import PedidoItem  # noqa: F401
from app.models.pago import Pago  # noqa: F401
from app.models.tipo_iva import TipoIva  # noqa: F401
from app.models.proveedor import Proveedor  # noqa: F401
from app.models.banco import Banco  # noqa: F401
from app.models.localidad import Localidad  # noqa: F401
from app.models.pago_imputacion import PagoImputacion  # noqa: F401
from app.models.nota_credito_debito import NotaCreditoDebito, NotaCreditoItem  # noqa: F401
from app.models.ingreso_mercaderia import IngresoMercaderia, IngresoMercaderiaItem  # noqa: F401
from app.models.solicitud_cambio_cliente import SolicitudCambioCliente  # noqa: F401
from app.models.zona import Zona  # noqa: F401
from app.models.rutas import Ruta  # noqa: F401
from app.models.cuenta_sanalle import CuentaSanalle  # noqa: F401
from app.models.pago_proveedor import PagoProveedor  # noqa: F401
from app.models.notas_proveedor import NotaProveedor  # noqa: F401
from app.models.laboratorios import Laboratorio  # noqa: F401
from app.models.historial_pvp_producto import HistorialPvpProducto  # noqa: F401
from app.models.movimiento_stock import MovimientoStock  # noqa: F401
from app.models.bitacora_pedido import BitacoraPedido  # noqa: F401
# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the sqlalchemy.url from application settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    # For offline mode, use the sync driver URL
    url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using an async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

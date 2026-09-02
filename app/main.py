from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routers import (
    auth, users, clientes, productos, pedidos, pagos, dashboard, exports, reportes,
    tipo_iva, proveedores,
    bancos, localidades,
    notas_credito_debito, ingresos_mercaderia, cuenta_corriente, solicitudes_cambio,
    zonas, pagos_proveedor, cuenta_sanalle, movimientos_stock, laboratorios, depositos,
    feature_flags,
)
from app.routers import scraper
from app.routers import chat
from app.routers import configuracion
from app.routers import stock
from app.routers import transacciones
from app.routers import cuentas
from app.routers import publico
from app.routers import entidades
from app.scheduler import scheduler, setup_scheduler
from fastapi.openapi.utils import get_openapi


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="SANALLE - Sistema de Gestión", version="2.0.0", redirect_slashes=False, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def custom_openapi():
    if app.openapi_schema:  
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="SANALLE API",
        version="2.0.0",
        description="Documentación de la API de SANALLE",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2PasswordBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    for path in openapi_schema["paths"].values():
        for method in path.values():
            # Aplica security global a todas las rutas
            method.setdefault("security", [{"OAuth2PasswordBearer": []}])
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(clientes.router, prefix="/api/v1/clientes", tags=["Clientes"])
app.include_router(productos.router, prefix="/api/v1/productos", tags=["Productos"])
app.include_router(pedidos.router, prefix="/api/v1/pedidos", tags=["Pedidos"])
app.include_router(pagos.router, prefix="/api/v1/pagos", tags=["Pagos"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(exports.router, prefix="/api/v1/exports", tags=["Exports"])
app.include_router(reportes.router, prefix="/api/v1/reportes", tags=["Reportes"])
app.include_router(tipo_iva.router, prefix="/api/v1/tipo-iva", tags=["TipoIva"])
app.include_router(proveedores.router, prefix="/api/v1/proveedores", tags=["Proveedores"])
app.include_router(bancos.router, prefix="/api/v1/bancos", tags=["Bancos"])
app.include_router(localidades.router, prefix="/api/v1/localidades", tags=["Localidades"])
app.include_router(notas_credito_debito.router, prefix="/api/v1/notas-credito-debito", tags=["NotasCreditoDebito"])
app.include_router(ingresos_mercaderia.router, prefix="/api/v1/ingresos-mercaderia", tags=["IngresosMercaderia"])
app.include_router(cuenta_corriente.router, prefix="/api/v1/cuenta-corriente", tags=["CuentaCorriente"])
app.include_router(solicitudes_cambio.router, prefix="/api/v1/solicitudes-cambio", tags=["SolicitudesCambio"])
app.include_router(zonas.router, prefix="/api/v1/zonas", tags=["Zonas"])
app.include_router(pagos_proveedor.router, prefix="/api/v1/pagos-proveedor", tags=["PagosProveedor"])
app.include_router(cuenta_sanalle.router, prefix="/api/v1/cuenta-sanalle", tags=["CuentaSanalle"])
app.include_router(movimientos_stock.router, prefix="/api/v1/movimientos-stock", tags=["MovimientosStock"])
app.include_router(laboratorios.router, prefix="/api/v1/laboratorios", tags=["Laboratorios"])
app.include_router(depositos.router, prefix="/api/v1/depositos", tags=["Depositos"])
app.include_router(stock.router, prefix="/api/v1/stock", tags=["Stock"])
app.include_router(scraper.router, prefix="/api/v1/scraper", tags=["Scraper"])
app.include_router(feature_flags.router, prefix="/api/v1/feature-flags", tags=["FeatureFlags"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(configuracion.router, prefix="/api/v1/configuracion", tags=["Configuracion"])
app.include_router(transacciones.router, prefix="/api/v1/transacciones", tags=["Transacciones"])
app.include_router(cuentas.router, prefix="/api/v1/cuentas", tags=["Cuentas"])
app.include_router(publico.router, prefix="/api/v1/publico", tags=["Publico"])
app.include_router(entidades.router, prefix="/api/v1/entidades", tags=["Entidades"])


@app.get("/")
async def root():
    return {"message": "SANALLE API v2.0", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}


app.openapi = custom_openapi
# Vaciar el circuito de dinero (ventas + compras + caja)

> ⚠️ **DESTRUCTIVO E IRREVERSIBLE.** Borra TODOS los pedidos, pagos, compras, pagos a
> proveedor, notas y la Cuenta Sanalle. **Deja intactos** clientes, productos, stock,
> usuarios, proveedores, laboratorios, zonas, localidades y configuración.
> Corre contra la base que apunte `DATABASE_URL` (hoy: **producción / Railway**).

## Qué borra (TRUNCATE ... RESTART IDENTITY CASCADE)

Ventas: `pedidos`, `pedido_items`, `pago_imputaciones`, `pagos`, `bitacora_pedidos`, `rutas`
Compras: `ingresos_mercaderia`, `ingreso_mercaderia_items`, `pago_proveedor_imputaciones`, `pagos_proveedor`, `notas_proveedor`
Notas cliente: `notas_credito_debito`, `nota_credito_items`
Caja: `cuenta_sanalle`

## Qué NO borra
`clientes` (incluida su `deuda_inicial*`), `productos` (incluido el stock), `users`,
`proveedores`, `laboratorios`, `zonas`, `localidades`, `configuracion`, `feature_flags`,
`movimientos_stock`, chat, historial de PVP.

## Efectos colaterales a decidir (pasos OPCIONALES en 03_wipe.sql)
- **Reservas de stock fantasma:** al borrar pedidos, `productos.stock_reservado_*` queda con
  valores viejos. El paso opcional B las pone en 0. (No toca el stock disponible.)
- **Saldos de proveedor:** `proveedores.saldo_remito/saldo_factura` se acumulan desde compras/
  pagos. El paso opcional C los pone en 0.
- **`clientes.deuda_inicial*`:** NO se toca por defecto (es el saldo de apertura real). Si querés
  arrancar de cero absoluto, hay un paso opcional D comentado.

## Procedimiento seguro (en este orden)

```bash
# 0) Exportá la URL de la base (formato plano, SIN +asyncpg)
export DATABASE_URL='postgresql://USER:PASS@HOST:PORT/DBNAME'

# 1) BACKUP COMPLETO primero (imprescindible)
bash 01_backup.sh
#    -> genera backup_full_<fecha>.dump y backup_dinero_<fecha>.sql

# 2) DRY-RUN: ver cuántas filas se van a borrar (no borra nada)
psql "$DATABASE_URL" -f 02_dry_run.sql

# 3) BORRADO (recién cuando revisaste el dry-run y tenés el backup)
psql "$DATABASE_URL" -f 03_wipe.sql
```

## Restaurar (si algo sale mal)
```bash
pg_restore --clean --if-exists -d "$DATABASE_URL" backup_full_<fecha>.dump
```

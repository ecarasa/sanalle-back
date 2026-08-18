#!/usr/bin/env bash
# Backup ANTES de vaciar el circuito de dinero.
# Requiere: DATABASE_URL en formato plano (postgresql://...  SIN +asyncpg).
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: exportá DATABASE_URL primero (postgresql://user:pass@host:port/db)"
  exit 1
fi

FECHA="$(date +%Y%m%d_%H%M%S)"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo ">> 1/2 Dump COMPLETO (custom format, restaurable con pg_restore)"
pg_dump "$DATABASE_URL" -Fc -f "$DIR/backup_full_${FECHA}.dump"

echo ">> 2/2 Dump de las tablas de dinero (SQL plano, por si querés ver/insertar puntual)"
pg_dump "$DATABASE_URL" --data-only \
  -t pedidos -t pedido_items -t pago_imputaciones -t pagos \
  -t bitacora_pedidos -t rutas \
  -t ingresos_mercaderia -t ingreso_mercaderia_items \
  -t pago_proveedor_imputaciones -t pagos_proveedor -t notas_proveedor \
  -t notas_credito_debito -t nota_credito_items \
  -t cuenta_sanalle \
  -f "$DIR/backup_dinero_${FECHA}.sql"

echo ">> OK. Backups en: $DIR"
ls -lh "$DIR"/backup_*_"${FECHA}".* || true

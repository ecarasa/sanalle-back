#!/usr/bin/env sh
# Arranque para producción (Railway u otro PaaS de un solo contenedor).
# Railway inyecta la variable PORT; caemos a 8181 en local.
set -e

echo "[start] init_db (crea tablas en DB fresca, no-op si ya existe)..."
python init_db.py

echo "[start] alembic upgrade head..."
alembic upgrade head

echo "[start] uvicorn en puerto ${PORT:-8181}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8181}" --workers 2

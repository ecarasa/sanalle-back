from fastapi import APIRouter, Depends, Query

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.scraper_run import ScraperRun
from app.services.scraper_pvp_service import (
    run_pvp_scrape,
    fetch_pvp_options,
    match_option,
    match_saved,
    _extract_quantity,
)
from app.utils.deps import require_role

router = APIRouter()


@router.post("/trigger-pvp-scrape")
async def trigger_pvp_scrape(_=Depends(require_role(["admin", "super_admin"]))):
    return await run_pvp_scrape(origen="manual")


@router.get("/runs")
async def list_scraper_runs(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(["admin", "super_admin"])),
):
    """Historial de corridas del scraper de PVP, más reciente primero."""
    rows = await db.execute(
        select(ScraperRun).order_by(ScraperRun.started_at.desc()).limit(limit)
    )
    runs = rows.scalars().all()
    return [
        {
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "duration_seconds": r.duration_seconds,
            "trigger": r.trigger,
            "status": r.status,
            "total": r.total,
            "updated": r.updated,
            "skipped": r.skipped,
            "failed": r.failed,
            "error_message": r.error_message,
        }
        for r in runs
    ]


@router.get("/test-pvp-url")
async def test_pvp_url(
    url: str = Query(..., description="URL de alfabeta.net a testear"),
    presentacion: str | None = Query(None, description="Presentación del producto, ej: 'Caja x 20'"),
    nombre: str | None = Query(None, description="Nombre del producto, ej: 'Novalgina X 10 Cmp'"),
    descripcion_guardada: str | None = Query(None, description="Opción de Alfabeta ya elegida a mano"),
    _=Depends(require_role(["admin", "super_admin"])),
):
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=settings.PVP_SCRAPER_TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0 (compatible; SanalleBot/1.0)"},
    ) as client:
        options = await fetch_pvp_options(client, url)

    if options is None:
        options = []

    # La opción ya guardada manda; si no hay, se intenta el match por presentación + nombre.
    matched = match_saved(options, descripcion_guardada)
    if matched is None:
        matched = match_option(options, presentacion, nombre)
    if matched is None and len(options) == 1:
        matched = options[0]

    return {
        "url": url,
        "presentacion": presentacion,
        "cantidad_buscada": _extract_quantity(presentacion),
        "match": matched is not None,
        "pvp_extraido": str(matched["pvp"]) if matched else None,
        "presentacion_alfabeta": matched["descripcion"] if matched else None,
        "opciones": [
            {"descripcion": o["descripcion"], "pvp": str(o["pvp"])} for o in options
        ],
    }

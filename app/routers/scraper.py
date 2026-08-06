from fastapi import APIRouter, Depends, Query

import httpx

from app.core.config import settings
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
    return await run_pvp_scrape()


@router.get("/test-pvp-url")
async def test_pvp_url(
    url: str = Query(..., description="URL de alfabeta.net a testear"),
    presentacion: str | None = Query(None, description="Presentación del producto, ej: 'Caja x 20'"),
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

    # La opción ya guardada manda; si no hay, se intenta el match por presentación.
    matched = match_saved(options, descripcion_guardada)
    if matched is None:
        matched = match_option(options, presentacion)
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

import logging
import re
from decimal import Decimal, InvalidOperation

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.producto import Producto
from app.services.pricing_service import aplicar_a_producto

logger = logging.getLogger(__name__)


async def run_pvp_scrape() -> dict:
    result = {"total": 0, "updated": 0, "failed": 0, "skipped": 0}

    async with async_session_maker() as session:
        rows = await session.execute(
            select(Producto).where(Producto.url_pvp.isnot(None))
        )
        productos = rows.scalars().all()
        result["total"] = len(productos)

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.PVP_SCRAPER_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SanalleBot/1.0)"},
        ) as client:
            batch = 0
            for producto in productos:
                new_price = await _fetch_pvp(
                    client, producto.url_pvp, producto.presentacion, producto.pvp_descripcion
                )

                if new_price is None:
                    result["failed"] += 1
                    continue

                if producto.pvp is not None and new_price == producto.pvp:
                    result["skipped"] += 1
                    continue

                producto.pvp = new_price

                # Recalcula costos y TODAS las listas configuradas (incluida comercio).
                aplicar_a_producto(producto)

                result["updated"] += 1
                batch += 1

                if batch >= 50:
                    await session.commit()
                    batch = 0

            if batch > 0:
                await session.commit()

    return result


def _extract_quantity(presentacion: str | None) -> str | None:
    """Extract the numeric quantity from a presentacion string like 'Caja x 20' → '20'."""
    if not presentacion:
        return None
    match = re.search(r'x\s*(\d+)', presentacion, re.IGNORECASE)
    return match.group(1) if match else None


def _parse_price(raw: str) -> Decimal:
    """Parse Argentine price format: $24.414,59 → Decimal('24414.59')."""
    cleaned = raw.replace("$", "").replace(".", "").replace(",", ".").strip()
    return Decimal(cleaned)


async def fetch_pvp_options(
    client: httpx.AsyncClient, url: str
) -> list[dict] | None:
    """Return every (descripcion, pvp) pair on an alfabeta.net price page,
    in document order. None on network/parse failure."""
    try:
        response = await client.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except (httpx.HTTPError, Exception) as exc:
        logger.warning("Failed to scrape PVP from %s: %s", url, exc)
        return None

    options: list[dict] = []
    for desc_td in soup.select("td.tddesc"):
        row = desc_td.find_parent("tr")
        price_td = row.select_one("td.tdprecio") if row else None
        if price_td is None:
            continue
        try:
            price = _parse_price(price_td.get_text(strip=True))
        except InvalidOperation:
            continue
        descripcion = " ".join(desc_td.get_text(" ", strip=True).split())
        options.append({"descripcion": descripcion, "pvp": price})
    return options


def match_option(options: list[dict], presentacion: str | None) -> dict | None:
    """Pick the option whose descripcion contains the quantity ('x N') of the
    product's presentacion. None if there is no quantity or no match."""
    quantity = _extract_quantity(presentacion)
    if not quantity:
        return None
    pattern = re.compile(rf'x\s*{re.escape(quantity)}\b', re.IGNORECASE)
    for opt in options:
        if pattern.search(opt["descripcion"]):
            return opt
    return None


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def match_saved(options: list[dict], descripcion: str | None) -> dict | None:
    """Pick the option that the user chose by hand (guardada en producto.pvp_descripcion).
    Exact match primero, luego normalizado (minúsculas + espacios colapsados)."""
    if not descripcion:
        return None
    for opt in options:
        if opt["descripcion"] == descripcion:
            return opt
    objetivo = _norm(descripcion)
    for opt in options:
        if _norm(opt["descripcion"]) == objetivo:
            return opt
    return None


async def _fetch_pvp(
    client: httpx.AsyncClient,
    url: str,
    presentacion: str | None = None,
    descripcion_guardada: str | None = None,
) -> Decimal | None:
    options = await fetch_pvp_options(client, url)
    if options is None:
        return None
    if not options:
        logger.warning("PVP element not found at %s", url)
        return None

    # 1) La opción elegida a mano manda: si sigue en la página, se usa esa.
    matched = match_saved(options, descripcion_guardada)
    if matched is None and descripcion_guardada:
        logger.warning(
            "Opción guardada %r ya no está en %s; se cae al match por presentación",
            descripcion_guardada, url,
        )

    # 2) Fallback: match por cantidad de la presentación.
    if matched is None:
        matched = match_option(options, presentacion)

    # 3) Sin ambigüedad posible: una sola presentación en la página.
    if matched is None and len(options) == 1:
        matched = options[0]

    if matched is None:
        logger.warning(
            "No presentation match at %s (presentacion=%r, %d opciones); reported as failed",
            url, presentacion, len(options),
        )
        return None

    return matched["pvp"]

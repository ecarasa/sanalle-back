import logging
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.producto import Producto
from app.models.scraper_run import ScraperRun
from app.services.pricing_service import aplicar_a_producto

logger = logging.getLogger(__name__)


async def _scrape_productos(result: dict) -> None:
    """Corre el scrape sobre todos los productos con url_pvp, mutando `result`."""
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
            items = result.setdefault("items", [])
            batch = 0
            for producto in productos:
                old_price = producto.pvp
                new_price = await _fetch_pvp(
                    client, producto.url_pvp, producto.presentacion,
                    producto.pvp_descripcion, producto.nombre,
                )

                if new_price is None:
                    result["failed"] += 1
                    items.append({
                        "producto_id": producto.id, "resultado": "failed",
                        "pvp_anterior": old_price, "pvp_traido": None,
                        "detalle": "No se encontró/matcheó el precio en alfabeta",
                    })
                    continue

                if old_price is not None and new_price == old_price:
                    result["skipped"] += 1
                    items.append({
                        "producto_id": producto.id, "resultado": "skipped",
                        "pvp_anterior": old_price, "pvp_traido": new_price, "detalle": None,
                    })
                    continue

                producto.pvp = new_price

                # Recalcula costos y TODAS las listas configuradas (incluida comercio).
                aplicar_a_producto(producto)

                result["updated"] += 1
                items.append({
                    "producto_id": producto.id, "resultado": "updated",
                    "pvp_anterior": old_price, "pvp_traido": new_price, "detalle": None,
                })
                batch += 1

                if batch >= 50:
                    await session.commit()
                    batch = 0

            if batch > 0:
                await session.commit()


async def run_pvp_scrape(origen: str = "manual") -> dict:
    """Corre el scraper de PVP y registra la corrida en `scraper_runs`.

    origen: 'manual' (disparado desde la UI) | 'scheduled' (job semanal).
    """
    result = {"total": 0, "updated": 0, "failed": 0, "skipped": 0}
    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()
    status = "ok"
    error_message = None

    try:
        await _scrape_productos(result)
    except Exception as exc:  # noqa: BLE001 — queremos registrar cualquier fallo
        status = "error"
        error_message = str(exc)[:500]
        logger.exception("PVP scrape failed")

    # Registrar la corrida + el detalle por producto (no debe tumbar el scrape si falla).
    try:
        from app.models.scraper_run_item import ScraperRunItem
        async with async_session_maker() as log_session:
            run = ScraperRun(
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_seconds=round(time.monotonic() - t0, 2),
                trigger=origen,
                status=status,
                total=result["total"],
                updated=result["updated"],
                skipped=result["skipped"],
                failed=result["failed"],
                error_message=error_message,
            )
            log_session.add(run)
            await log_session.commit()
            await log_session.refresh(run)

            items = result.get("items", [])
            if items:
                log_session.add_all([
                    ScraperRunItem(
                        run_id=run.id,
                        producto_id=it["producto_id"],
                        resultado=it["resultado"],
                        pvp_anterior=it["pvp_anterior"],
                        pvp_traido=it["pvp_traido"],
                        detalle=it["detalle"],
                    )
                    for it in items
                ])
                await log_session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo registrar la corrida del scraper")

    return result


def _extract_quantity(presentacion: str | None) -> str | None:
    """Extract the numeric quantity from a presentacion string like 'Caja x 20' → '20'."""
    if not presentacion:
        return None
    match = re.search(r'x\s*(\d+)', presentacion, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_quantities(text: str | None) -> list[str]:
    """Todas las cantidades 'x N' de un texto, en orden. Ej: 'X 10 Comp' → ['10']."""
    if not text:
        return []
    return re.findall(r'x\s*(\d+)\b', text, re.IGNORECASE)


def _extract_dosage_mg(text: str | None) -> str | None:
    """Dosis en mg de un texto. Ej: '200 Mg X 10' → '200'."""
    if not text:
        return None
    match = re.search(r'(\d+)\s*mg\b', text, re.IGNORECASE)
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


def match_option(
    options: list[dict],
    presentacion: str | None,
    nombre: str | None = None,
) -> dict | None:
    """Elige la opción de alfabeta que corresponde al producto.

    Estrategia:
    1) Prueba cantidades 'x N' primero de la presentación y luego del nombre
       (muchos productos tienen las unidades en el nombre y el packaging en la
       presentación, ej: nombre 'Novalgina X 10 Cmp', presentación 'Blister x 1').
    2) Si una cantidad matchea varias opciones, desambigua por dosis en mg
       (ej: Acemuk 200 mg vs 600 mg).
    """
    # Orden de prioridad de cantidades: presentación, después nombre. Sin duplicar.
    candidatos: list[str] = []
    for q in _extract_quantities(presentacion) + _extract_quantities(nombre):
        if q not in candidatos:
            candidatos.append(q)

    dosage = _extract_dosage_mg(nombre) or _extract_dosage_mg(presentacion)

    for qty in candidatos:
        qpat = re.compile(rf'x\s*{re.escape(qty)}\b', re.IGNORECASE)
        matches = [o for o in options if qpat.search(o["descripcion"])]
        if not matches:
            continue
        if len(matches) == 1:
            return matches[0]
        # Varias opciones con la misma cantidad → desambiguar por dosis.
        if dosage:
            dpat = re.compile(rf'\b{re.escape(dosage)}\s*mg\b', re.IGNORECASE)
            dosed = [o for o in matches if dpat.search(o["descripcion"])]
            if len(dosed) == 1:
                return dosed[0]
            if dosed:
                matches = dosed
        # Sigue ambiguo: se toma la primera en orden de documento (mismo precio
        # en la práctica cuando son la misma dosis+cantidad).
        return matches[0]

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
    nombre: str | None = None,
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

    # 2) Fallback: match por cantidad/dosis (presentación + nombre).
    if matched is None:
        matched = match_option(options, presentacion, nombre)

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

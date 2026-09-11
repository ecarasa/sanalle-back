"""Fecha y hora en horario argentino.

El servidor corre en UTC (Railway, y el contenedor local, no fijan TZ). Un
`date.today()`/`datetime.now()` naive toma la fecha de Greenwich, que durante
la noche argentina (hasta las 21hs ART) ya es el día siguiente. Todo lo que
tenga que reflejar "qué día es para alguien en Argentina" tiene que pasar por
acá en vez de llamar a esas funciones directo.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

ZONA_AR = ZoneInfo("America/Argentina/Buenos_Aires")


def ahora_ar() -> datetime:
    return datetime.now(ZONA_AR)


def hoy_ar() -> date:
    return ahora_ar().date()

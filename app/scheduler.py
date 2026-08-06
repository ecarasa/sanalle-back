from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.scraper_pvp_service import run_pvp_scrape

scheduler = AsyncIOScheduler()


def setup_scheduler() -> None:
    scheduler.add_job(
        run_pvp_scrape,
        trigger=CronTrigger(
            day_of_week="fri",
            hour=3,
            minute=0,
            timezone="America/Argentina/Buenos_Aires",
        ),
        id="pvp_weekly_scrape",
        name="Actualización semanal de PVP (alfabeta.net)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

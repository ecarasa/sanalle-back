"""
Database initialization script for fresh deployments.

- Fresh DB (no alembic_version table): creates all tables via SQLAlchemy
  models, then stamps alembic to head so subsequent `alembic upgrade head`
  becomes a no-op.
- Existing DB: does nothing — `alembic upgrade head` runs normally.
"""
import asyncio
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def init() -> bool:
    """Returns True if this was a fresh database."""
    from app.core.config import settings
    from app.core.database import Base
    import app.models  # noqa: F401 — registers all models on Base.metadata

    engine = create_async_engine(settings.DATABASE_URL)
    is_fresh = False

    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT EXISTS("
            "  SELECT 1 FROM information_schema.tables"
            "  WHERE table_name = 'alembic_version'"
            ")"
        ))
        is_fresh = not result.scalar()

        if is_fresh:
            print("[init_db] Fresh database detected — creating all tables...", flush=True)
            await conn.run_sync(Base.metadata.create_all)
            print("[init_db] All tables created.", flush=True)

    await engine.dispose()
    return is_fresh


if __name__ == "__main__":
    fresh = asyncio.run(init())
    if fresh:
        print("[init_db] Stamping alembic to head...", flush=True)
        result = subprocess.run(["alembic", "stamp", "head"], capture_output=True, text=True)
        print(result.stdout, end="", flush=True)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr, flush=True)
            sys.exit(1)
        print("[init_db] Done. alembic upgrade head will be a no-op.", flush=True)
    else:
        print("[init_db] Existing database — skipping create_all.", flush=True)

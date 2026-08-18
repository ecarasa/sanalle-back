from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.user import User
from app.utils.deps import get_current_user, require_role
from app.services.dashboard_service import get_ventas_dashboard, get_admin_dashboard

router = APIRouter()


@router.get("/ventas")
async def dashboard_ventas(
    desde: str | None = None,
    hasta: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_ventas_dashboard(db, current_user.id, desde=desde, hasta=hasta)


@router.get("/admin")
async def dashboard_admin(
    mes: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    return await get_admin_dashboard(db, mes, desde=desde, hasta=hasta)

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.feature_flag import FeatureFlag
from app.models.user import User
from app.schemas.feature_flag import FeatureFlagResponse, FeatureFlagUpdate
from app.utils.deps import get_current_user, require_role

router = APIRouter()


@router.get("")
async def list_feature_flags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(FeatureFlag).order_by(FeatureFlag.clave))
    flags = result.scalars().all()
    return [FeatureFlagResponse.model_validate(f) for f in flags]


@router.put("/{clave}")
async def set_feature_flag(
    clave: str,
    data: FeatureFlagUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["super_admin"])),
):
    result = await db.execute(select(FeatureFlag).where(FeatureFlag.clave == clave))
    flag = result.scalar_one_or_none()
    if flag is None:
        flag = FeatureFlag(clave=clave, habilitado=data.habilitado)
        db.add(flag)
    else:
        flag.habilitado = data.habilitado
    await db.commit()
    await db.refresh(flag)
    return FeatureFlagResponse.model_validate(flag)

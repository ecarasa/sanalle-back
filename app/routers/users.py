from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import (
    PasswordChange,
    ResetPasswordRequest,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.utils.deps import get_current_user, require_role
from app.utils.filters import apply_column_filters

router = APIRouter()


@router.get("")
async def list_users(
    search: str = Query("", description="Buscar por nombre, email o username"),
    column_filters: str | None = Query(None, alias="filters", description="JSON column filters"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    base_query = select(User)

    if search:
        like_pattern = f"%{search}%"
        search_filter = (
            User.nombre_completo.ilike(like_pattern)
            | User.email.ilike(like_pattern)
            | User.username.ilike(like_pattern)
        )
        base_query = base_query.where(search_filter)

    base_query = apply_column_filters(
        base_query,
        User,
        column_filters,
        allowed_columns={"nombre_completo", "email", "username", "rol", "activo"},
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = base_query.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    users = result.scalars().all()

    return {
        "items": [UserResponse.model_validate(u) for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@router.get("/vendedores")
async def list_vendedores(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["admin", "super_admin"])),
):
    result = await db.execute(select(User).where(User.rol == "ventas"))
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["super_admin"])),
):
    result = await db.execute(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El username o email ya está registrado",
        )

    user = User(
        email=body.email,
        username=body.username,
        hashed_password=get_password_hash(body.password),
        nombre_completo=body.nombre_completo,
        rol=body.rol,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.put("/me/password")
async def change_password(
    body: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contraseña actual incorrecta",
        )

    current_user.hashed_password = get_password_hash(body.new_password)
    current_user.debe_cambiar_contrasena = False
    await db.commit()
    return {"message": "Contraseña actualizada"}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["super_admin"])),
):
    """Admin resets a user's password and sets the must-change flag."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.hashed_password = get_password_hash(body.new_password)
    user.debe_cambiar_contrasena = True
    await db.commit()
    return {"message": f"Contraseña de {user.username} reseteada"}


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["super_admin"])),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role(["super_admin"])),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    user.activo = False
    await db.commit()
    return {"message": f"Usuario {user.username} desactivado"}

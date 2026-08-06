"""
Seed module for SANALLE ERP (Users only).
Run with: python -m app.seed
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.config import settings
from app.core.security import get_password_hash
from app.core.database import Base
from app.models.user import User, RolUsuario


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created/verified.")

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        print("Seeding database (users only)...")

        # ─── Users ───────────────────────────────────────────────
        print("  Creating/updating users...")

        async def get_or_create_user(email, username, password, nombre, rol):
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                user = User(
                    email=email,
                    username=username,
                    hashed_password=get_password_hash(password),
                    nombre_completo=nombre,
                    rol=rol,
                    activo=True,
                )
                session.add(user)
                await session.flush()
                print(f"    Created user: {username}")
            else:
                user.rol = rol
                user.nombre_completo = nombre
                user.activo = True
                session.add(user)
                await session.flush()
                print(f"    Updated user: {username}")
            return user

        await get_or_create_user("admin@sanalle.com", "admin", "admin123", "Administrador Sanalle", RolUsuario.admin)
        await get_or_create_user("ventas@sanalle.com", "ventas", "ventas123", "Ventas Sanalle", RolUsuario.ventas)
        await get_or_create_user("repartidor@sanalle.com", "repartidor", "repartidor123", "Repartidor Sanalle", RolUsuario.repartidor)
        await get_or_create_user("super_admin@sanalle.com", "super_admin", "super_admin123", "Super Admin Sanalle", RolUsuario.super_admin)

        await session.commit()
        print("User seed completed successfully!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())

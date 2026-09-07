"""Alta de usuarios base del ERP.

Corre con: python -m app.seed

Las contraseñas NO están en el código: se toman de variables de entorno
(`SEED_ADMIN_PASSWORD`, `SEED_VENTAS_PASSWORD`, `SEED_REPARTIDOR_PASSWORD`,
`SEED_SUPERADMIN_PASSWORD`). Si alguna falta, se genera una aleatoria y se
imprime UNA vez al crear el usuario — nunca queda un valor por defecto usable
pegado en un repo público, que es lo que pasaba antes (`admin123` y compañía).

A los usuarios que ya existen no se les toca la contraseña.
"""
import asyncio
import os
import secrets

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.config import settings
from app.core.security import get_password_hash
from app.core.database import Base
from app.models.user import User, RolUsuario


def _password(env_var: str) -> tuple[str, bool]:
    """Devuelve (contraseña, se_generó). Si no vino por env, una aleatoria fuerte."""
    valor = os.getenv(env_var)
    if valor:
        return valor, False
    return secrets.token_urlsafe(16), True


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created/verified.")

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        print("Seeding database (users only)...")

        async def get_or_create_user(email, username, env_var, nombre, rol):
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                password, generada = _password(env_var)
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
                if generada:
                    # Única vez que se ve en claro. Anotala y cambiala al primer login.
                    print(f"      >>> contraseña generada para {username}: {password}")
                    print(f"          (seteá {env_var} para fijarla vos)")
            else:
                # No se toca la contraseña de un usuario ya existente.
                user.rol = rol
                user.nombre_completo = nombre
                user.activo = True
                session.add(user)
                await session.flush()
                print(f"    Updated user (sin tocar contraseña): {username}")
            return user

        await get_or_create_user("admin@sanalle.com", "admin", "SEED_ADMIN_PASSWORD", "Administrador Sanalle", RolUsuario.admin)
        await get_or_create_user("ventas@sanalle.com", "ventas", "SEED_VENTAS_PASSWORD", "Ventas Sanalle", RolUsuario.ventas)
        await get_or_create_user("repartidor@sanalle.com", "repartidor", "SEED_REPARTIDOR_PASSWORD", "Repartidor Sanalle", RolUsuario.repartidor)
        await get_or_create_user("super_admin@sanalle.com", "super_admin", "SEED_SUPERADMIN_PASSWORD", "Super Admin Sanalle", RolUsuario.super_admin)

        await session.commit()
        print("User seed completed successfully!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())

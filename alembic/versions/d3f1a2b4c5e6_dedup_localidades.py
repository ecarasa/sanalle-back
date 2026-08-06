"""dedup localidades y unique index nombre+provincia

Revision ID: d3f1a2b4c5e6
Revises: 0b7c0f8d5ed3
Create Date: 2026-06-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd3f1a2b4c5e6'
down_revision: Union[str, None] = '0b7c0f8d5ed3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Para cada (nombre normalizado, provincia normalizada) elige una fila canonica:
# la activa de menor id; si ninguna esta activa, la de menor id.
_RANKED = """
    WITH ranked AS (
        SELECT
            id,
            first_value(id) OVER (
                PARTITION BY lower(btrim(nombre)), coalesce(btrim(provincia), '')
                ORDER BY activo DESC, id ASC
            ) AS keep_id
        FROM localidades
    )
"""


def upgrade() -> None:
    # 1. Repuntar clientes que apuntan a una localidad duplicada hacia la canonica.
    op.execute(
        _RANKED
        + """
        UPDATE clientes c
        SET localidad_id = r.keep_id
        FROM ranked r
        WHERE c.localidad_id = r.id
          AND r.id <> r.keep_id;
        """
    )

    # 2. Eliminar las filas duplicadas (todo lo que no es canonico).
    op.execute(
        _RANKED
        + """
        DELETE FROM localidades l
        USING ranked r
        WHERE l.id = r.id
          AND r.id <> r.keep_id;
        """
    )

    # 3. Indice unico funcional para impedir nuevos duplicados.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_localidades_nombre_provincia_uq
        ON localidades (lower(btrim(nombre)), coalesce(btrim(provincia), ''));
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_localidades_nombre_provincia_uq;")

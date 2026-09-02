"""ajustes de stock con motivo y toma de inventario

Hasta ahora un ajuste de stock quedaba con una observación de texto libre que
además escribía el frontend ("Ajuste manual de stock"), así que no había forma
de responder cuánta mercadería se perdió por rotura o por vencimiento: el dato
estaba, pero en prosa. `motivo` lo convierte en una taxonomía que se puede
agrupar. Es columna y no una fila de `entidades` porque la lógica lo lee (los
motivos de merma van a alimentar un reporte de pérdidas) y un renombre desde el
ABM de combos rompería ese reporte en silencio. Queda nullable porque los
movimientos que ya existen no tienen motivo y no corresponde inventarles uno.

Las dos tablas de inventario existen porque contar un depósito no es un submit:
lleva horas, lo hacen varias personas y tiene que sobrevivir a que se cierre el
navegador. `esperado_*` es la foto de lo que el sistema creía tener al abrir la
toma, y es lo único que después permite distinguir una diferencia de inventario
de una venta ocurrida durante el conteo — que es exactamente lo que hay que
mostrarle a quien aprueba antes de pisar el stock.

Revision ID: s3m4stock0001
Revises: r2l3modalidad1
Create Date: 2026-09-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "s3m4stock0001"
down_revision: Union[str, None] = "r2l3modalidad1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tomas_inventario",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("numero", sa.String(length=50), nullable=False),
        sa.Column("deposito_id", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="borrador"),
        sa.Column("origen", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("creado_por_id", sa.Integer(), nullable=False),
        sa.Column("aplicado_por_id", sa.Integer(), nullable=True),
        sa.Column("aplicada_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["deposito_id"], ["depositos.id"]),
        sa.ForeignKeyConstraint(["creado_por_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["aplicado_por_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tomas_inventario_numero", "tomas_inventario", ["numero"], unique=True)
    op.create_index("ix_tomas_inventario_deposito_id", "tomas_inventario", ["deposito_id"])
    op.create_index("ix_tomas_inventario_estado", "tomas_inventario", ["estado"])

    op.create_table(
        "toma_inventario_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("toma_id", sa.Integer(), nullable=False),
        sa.Column("producto_id", sa.Integer(), nullable=False),
        sa.Column("esperado_cajas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("esperado_blisters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contado_cajas", sa.Integer(), nullable=True),
        sa.Column("contado_blisters", sa.Integer(), nullable=True),
        sa.Column("aplicado_delta_blisters", sa.Integer(), nullable=True),
        sa.Column("contado_por_id", sa.Integer(), nullable=True),
        sa.Column("contado_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["toma_id"], ["tomas_inventario.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["producto_id"], ["productos.id"]),
        sa.ForeignKeyConstraint(["contado_por_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("toma_id", "producto_id", name="uq_toma_producto"),
        sa.CheckConstraint(
            "(contado_cajas IS NULL OR contado_cajas >= 0) AND "
            "(contado_blisters IS NULL OR contado_blisters >= 0)",
            name="ck_toma_contado_no_negativo",
        ),
    )
    op.create_index("ix_toma_inventario_items_toma_id", "toma_inventario_items", ["toma_id"])

    op.add_column("movimientos_stock", sa.Column("motivo", sa.String(length=30), nullable=True))
    op.create_index("ix_movimientos_stock_motivo", "movimientos_stock", ["motivo"])
    op.add_column("movimientos_stock", sa.Column("toma_inventario_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_movimientos_stock_toma_inventario_id", "movimientos_stock", ["toma_inventario_id"]
    )
    op.create_foreign_key(
        "fk_movimientos_stock_toma_inventario_id",
        "movimientos_stock",
        "tomas_inventario",
        ["toma_inventario_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_movimientos_stock_toma_inventario_id", "movimientos_stock", type_="foreignkey")
    op.drop_index("ix_movimientos_stock_toma_inventario_id", table_name="movimientos_stock")
    op.drop_column("movimientos_stock", "toma_inventario_id")
    op.drop_index("ix_movimientos_stock_motivo", table_name="movimientos_stock")
    op.drop_column("movimientos_stock", "motivo")

    op.drop_index("ix_toma_inventario_items_toma_id", table_name="toma_inventario_items")
    op.drop_table("toma_inventario_items")
    op.drop_index("ix_tomas_inventario_estado", table_name="tomas_inventario")
    op.drop_index("ix_tomas_inventario_deposito_id", table_name="tomas_inventario")
    op.drop_index("ix_tomas_inventario_numero", table_name="tomas_inventario")
    op.drop_table("tomas_inventario")

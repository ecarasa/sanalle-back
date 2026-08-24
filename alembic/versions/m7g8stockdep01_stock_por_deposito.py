"""stock por depósito como única fuente de verdad

Saca las columnas stock_a_*/stock_b_* de `productos` y deja `stock_producto_deposito`
como único lugar donde vive el stock. Todo lo que movía stock pasa a apuntar a un
depósito concreto: pedido_items, ingresos, notas de crédito/débito y movimientos.

Migración de datos, no solo de esquema. Antes de correrla conviene revisar que no
haya stock negativo (ver checklist de deploy): los negativos se llevan a 0 porque
el esquema nuevo no los admite.

Revision ID: m7g8stockdep01
Revises: l6f7roloperac
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m7g8stockdep01"
down_revision: Union[str, None] = "l6f7roloperac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY = (("a", "Sanalle"), ("b", "Farmacare"))


def upgrade() -> None:
    conn = op.get_bind()

    # --- 0. Garantizar que existan los dos depósitos legacy -------------------
    # Si alguien renombró o borró Sanalle/Farmacare, el backfill de abajo no
    # tendría dónde poner el stock A/B. Se recrean antes de tocar nada.
    for legacy, nombre in LEGACY:
        conn.execute(
            sa.text(
                """
                INSERT INTO depositos (nombre, activo, orden, stock_legacy)
                SELECT CAST(:nombre AS varchar), true,
                       COALESCE((SELECT MAX(orden) FROM depositos), 0) + 1,
                       CAST(:legacy AS varchar)
                WHERE NOT EXISTS (
                          SELECT 1 FROM depositos WHERE stock_legacy = CAST(:legacy AS varchar)
                      )
                  AND NOT EXISTS (
                          SELECT 1 FROM depositos WHERE nombre = CAST(:nombre AS varchar)
                      )
                """
            ),
            {"nombre": nombre, "legacy": legacy},
        )
        # Depósito con el nombre pero sin la marca (p. ej. recreado a mano).
        conn.execute(
            sa.text(
                """
                UPDATE depositos SET stock_legacy = CAST(:legacy AS varchar)
                WHERE nombre = CAST(:nombre AS varchar)
                  AND stock_legacy IS DISTINCT FROM CAST(:legacy AS varchar)
                  AND NOT EXISTS (
                          SELECT 1 FROM depositos WHERE stock_legacy = CAST(:legacy AS varchar)
                      )
                """
            ),
            {"nombre": nombre, "legacy": legacy},
        )

    # --- 1. Reservas en la tabla por depósito --------------------------------
    op.add_column(
        "stock_producto_deposito",
        sa.Column("reservado_cajas", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "stock_producto_deposito",
        sa.Column("reservado_blisters", sa.Integer(), server_default="0", nullable=False),
    )

    # --- 2. Fila de stock para todo producto en los depósitos legacy ---------
    # La migración d7e8depos001 sembró solo los productos que existían entonces.
    conn.execute(
        sa.text(
            """
            INSERT INTO stock_producto_deposito (producto_id, deposito_id, cajas, blisters)
            SELECT p.id, d.id, 0, 0
            FROM productos p
            CROSS JOIN depositos d
            WHERE d.stock_legacy IS NOT NULL
            ON CONFLICT (producto_id, deposito_id) DO NOTHING
            """
        )
    )

    # --- 3. Backfill: las columnas legacy son la verdad hasta acá ------------
    # El dual-write escribía productos -> stock_producto_deposito, así que ante
    # cualquier divergencia gana `productos`. Los depósitos NO legacy conservan
    # lo suyo, que era su único registro.
    for legacy in ("a", "b"):
        conn.execute(
            sa.text(
                f"""
                UPDATE stock_producto_deposito s
                SET cajas              = GREATEST(p.stock_{legacy}_cajas, 0),
                    blisters           = GREATEST(p.stock_{legacy}_blisters, 0),
                    reservado_cajas    = GREATEST(p.stock_reservado_{legacy}_cajas, 0),
                    reservado_blisters = GREATEST(p.stock_reservado_{legacy}_blisters, 0)
                FROM productos p, depositos d
                WHERE s.producto_id = p.id
                  AND s.deposito_id = d.id
                  AND d.stock_legacy = '{legacy}'
                """
            )
        )
    # Los depósitos nuevos nunca tuvieron reservas ni negativos, pero por las dudas.
    conn.execute(
        sa.text(
            """
            UPDATE stock_producto_deposito
            SET cajas = GREATEST(cajas, 0), blisters = GREATEST(blisters, 0)
            WHERE cajas < 0 OR blisters < 0
            """
        )
    )

    op.create_check_constraint(
        "ck_stock_no_negativo", "stock_producto_deposito", "cajas >= 0 AND blisters >= 0"
    )
    op.create_check_constraint(
        "ck_reservado_no_negativo",
        "stock_producto_deposito",
        "reservado_cajas >= 0 AND reservado_blisters >= 0",
    )

    # --- 4. pedido_items.deposito_id ----------------------------------------
    op.add_column("pedido_items", sa.Column("deposito_id", sa.Integer(), nullable=True))
    op.create_index("ix_pedido_items_deposito_id", "pedido_items", ["deposito_id"])
    op.create_foreign_key(
        "fk_pedido_items_deposito", "pedido_items", "depositos", ["deposito_id"], ["id"]
    )
    # Backfill con la regla vieja: Sanalle o factura -> stock A; el resto -> stock B.
    conn.execute(
        sa.text(
            """
            UPDATE pedido_items pi
            SET deposito_id = (
                SELECT d.id FROM depositos d
                WHERE d.stock_legacy = CASE
                    WHEN LOWER(COALESCE(p.sociedad, '')) = 'sanalle'
                      OR p.tipo_documento = 'factura' THEN 'a'
                    ELSE 'b'
                END
                LIMIT 1
            )
            FROM pedidos p
            WHERE pi.pedido_id = p.id
            """
        )
    )

    # --- 5. ingresos_mercaderia.destino -> deposito_id ----------------------
    op.add_column("ingresos_mercaderia", sa.Column("deposito_id", sa.Integer(), nullable=True))
    conn.execute(
        sa.text(
            """
            UPDATE ingresos_mercaderia i
            SET deposito_id = (
                SELECT d.id FROM depositos d
                WHERE d.stock_legacy = CASE WHEN UPPER(COALESCE(i.destino, 'A')) = 'B'
                                            THEN 'b' ELSE 'a' END
                LIMIT 1
            )
            """
        )
    )
    op.alter_column("ingresos_mercaderia", "deposito_id", nullable=False)
    op.create_index("ix_ingresos_mercaderia_deposito_id", "ingresos_mercaderia", ["deposito_id"])
    op.create_foreign_key(
        "fk_ingresos_deposito", "ingresos_mercaderia", "depositos", ["deposito_id"], ["id"]
    )
    op.drop_column("ingresos_mercaderia", "destino")

    # --- 6. notas_credito_debito.stock_tipo -> deposito_id ------------------
    op.add_column("notas_credito_debito", sa.Column("deposito_id", sa.Integer(), nullable=True))
    conn.execute(
        sa.text(
            """
            UPDATE notas_credito_debito n
            SET deposito_id = (
                SELECT d.id FROM depositos d
                WHERE d.stock_legacy = CASE WHEN UPPER(COALESCE(n.stock_tipo, 'A')) = 'B'
                                            THEN 'b' ELSE 'a' END
                LIMIT 1
            )
            WHERE n.afecta_stock = true
            """
        )
    )
    op.create_index("ix_notas_credito_debito_deposito_id", "notas_credito_debito", ["deposito_id"])
    op.create_foreign_key(
        "fk_notas_deposito", "notas_credito_debito", "depositos", ["deposito_id"], ["id"]
    )
    op.drop_column("notas_credito_debito", "stock_tipo")

    # --- 7. movimientos_stock.origen/destino -> FKs a depósito --------------
    op.add_column("movimientos_stock", sa.Column("deposito_origen_id", sa.Integer(), nullable=True))
    op.add_column("movimientos_stock", sa.Column("deposito_destino_id", sa.Integer(), nullable=True))
    for col, campo in (("deposito_origen_id", "origen"), ("deposito_destino_id", "destino")):
        conn.execute(
            sa.text(
                f"""
                UPDATE movimientos_stock m
                SET {col} = (
                    SELECT d.id FROM depositos d
                    WHERE d.stock_legacy = CASE WHEN m.{campo} = 'STOCK_B' THEN 'b' ELSE 'a' END
                    LIMIT 1
                )
                WHERE m.{campo} IN ('STOCK_A', 'STOCK_B')
                """
            )
        )
    op.create_index("ix_movimientos_stock_deposito_origen_id", "movimientos_stock", ["deposito_origen_id"])
    op.create_index("ix_movimientos_stock_deposito_destino_id", "movimientos_stock", ["deposito_destino_id"])
    op.create_foreign_key(
        "fk_movimientos_dep_origen", "movimientos_stock", "depositos", ["deposito_origen_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_movimientos_dep_destino", "movimientos_stock", "depositos", ["deposito_destino_id"], ["id"]
    )
    op.drop_column("movimientos_stock", "origen")
    op.drop_column("movimientos_stock", "destino")

    # --- 8. Fuera las columnas legacy ---------------------------------------
    for col in (
        "stock_a_cajas",
        "stock_a_blisters",
        "stock_reservado_a_cajas",
        "stock_reservado_a_blisters",
        "stock_b_cajas",
        "stock_b_blisters",
        "stock_reservado_b_cajas",
        "stock_reservado_b_blisters",
    ):
        op.drop_column("productos", col)

    # stock_legacy solo existía para el dual-write que acabamos de eliminar.
    op.drop_column("depositos", "stock_legacy")


def downgrade() -> None:
    conn = op.get_bind()

    # --- 1. Volver a marcar los depósitos legacy por nombre -----------------
    op.add_column("depositos", sa.Column("stock_legacy", sa.String(length=1), nullable=True))
    for legacy, nombre in LEGACY:
        conn.execute(
            sa.text(
                "UPDATE depositos SET stock_legacy = CAST(:legacy AS varchar) "
                "WHERE nombre = CAST(:nombre AS varchar)"
            ),
            {"legacy": legacy, "nombre": nombre},
        )

    # --- 2. Restaurar las columnas de stock en productos --------------------
    for col in (
        "stock_a_cajas",
        "stock_a_blisters",
        "stock_reservado_a_cajas",
        "stock_reservado_a_blisters",
        "stock_b_cajas",
        "stock_b_blisters",
        "stock_reservado_b_cajas",
        "stock_reservado_b_blisters",
    ):
        op.add_column(
            "productos", sa.Column(col, sa.Integer(), server_default="0", nullable=False)
        )
    for legacy in ("a", "b"):
        conn.execute(
            sa.text(
                f"""
                UPDATE productos p
                SET stock_{legacy}_cajas              = s.cajas,
                    stock_{legacy}_blisters           = s.blisters,
                    stock_reservado_{legacy}_cajas    = s.reservado_cajas,
                    stock_reservado_{legacy}_blisters = s.reservado_blisters
                FROM stock_producto_deposito s
                JOIN depositos d ON d.id = s.deposito_id
                WHERE s.producto_id = p.id AND d.stock_legacy = '{legacy}'
                """
            )
        )

    # --- 3. movimientos_stock ------------------------------------------------
    op.add_column("movimientos_stock", sa.Column("origen", sa.String(length=20), nullable=True))
    op.add_column("movimientos_stock", sa.Column("destino", sa.String(length=20), nullable=True))
    for col, campo in (("deposito_origen_id", "origen"), ("deposito_destino_id", "destino")):
        conn.execute(
            sa.text(
                f"""
                UPDATE movimientos_stock m
                SET {campo} = CASE WHEN d.stock_legacy = 'b' THEN 'STOCK_B' ELSE 'STOCK_A' END
                FROM depositos d
                WHERE d.id = m.{col} AND d.stock_legacy IS NOT NULL
                """
            )
        )
    op.drop_constraint("fk_movimientos_dep_origen", "movimientos_stock", type_="foreignkey")
    op.drop_constraint("fk_movimientos_dep_destino", "movimientos_stock", type_="foreignkey")
    op.drop_index("ix_movimientos_stock_deposito_origen_id", table_name="movimientos_stock")
    op.drop_index("ix_movimientos_stock_deposito_destino_id", table_name="movimientos_stock")
    op.drop_column("movimientos_stock", "deposito_origen_id")
    op.drop_column("movimientos_stock", "deposito_destino_id")

    # --- 4. notas_credito_debito --------------------------------------------
    op.add_column("notas_credito_debito", sa.Column("stock_tipo", sa.String(length=10), nullable=True))
    conn.execute(
        sa.text(
            """
            UPDATE notas_credito_debito n
            SET stock_tipo = CASE WHEN d.stock_legacy = 'b' THEN 'B' ELSE 'A' END
            FROM depositos d
            WHERE d.id = n.deposito_id
            """
        )
    )
    op.drop_constraint("fk_notas_deposito", "notas_credito_debito", type_="foreignkey")
    op.drop_index("ix_notas_credito_debito_deposito_id", table_name="notas_credito_debito")
    op.drop_column("notas_credito_debito", "deposito_id")

    # --- 5. ingresos_mercaderia ---------------------------------------------
    op.add_column(
        "ingresos_mercaderia",
        sa.Column("destino", sa.String(length=1), server_default="A", nullable=False),
    )
    conn.execute(
        sa.text(
            """
            UPDATE ingresos_mercaderia i
            SET destino = CASE WHEN d.stock_legacy = 'b' THEN 'B' ELSE 'A' END
            FROM depositos d
            WHERE d.id = i.deposito_id
            """
        )
    )
    op.drop_constraint("fk_ingresos_deposito", "ingresos_mercaderia", type_="foreignkey")
    op.drop_index("ix_ingresos_mercaderia_deposito_id", table_name="ingresos_mercaderia")
    op.drop_column("ingresos_mercaderia", "deposito_id")

    # --- 6. pedido_items -----------------------------------------------------
    op.drop_constraint("fk_pedido_items_deposito", "pedido_items", type_="foreignkey")
    op.drop_index("ix_pedido_items_deposito_id", table_name="pedido_items")
    op.drop_column("pedido_items", "deposito_id")

    # --- 7. stock_producto_deposito -----------------------------------------
    op.drop_constraint("ck_reservado_no_negativo", "stock_producto_deposito", type_="check")
    op.drop_constraint("ck_stock_no_negativo", "stock_producto_deposito", type_="check")
    op.drop_column("stock_producto_deposito", "reservado_blisters")
    op.drop_column("stock_producto_deposito", "reservado_cajas")

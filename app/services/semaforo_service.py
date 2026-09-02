from datetime import date

# Umbrales (en días) del semáforo de ACTIVIDAD por recencia de compra.
# verde  = compró hace <= VERDE_DIAS (da continuidad)
# amarillo = compró hace poco, entre VERDE_DIAS y AMARILLO_DIAS
# rojo   = inactivo (> AMARILLO_DIAS) o nunca compró
ACTIVIDAD_VERDE_DIAS = 30
ACTIVIDAD_AMARILLO_DIAS = 90

# Banda de aviso del semáforo de STOCK: amarillo hasta 1,5x el mínimo.
# Se expresa como fracción entera para poder escribir la misma comparación en SQL
# sin floats (total * DEN <= minimo * NUM).
STOCK_AVISO_NUM = 3
STOCK_AVISO_DEN = 2


def calcular_semaforo_actividad(dias_ultima_compra: int | None) -> str:
    """Semáforo de actividad comercial según los días desde la última compra.

    Returns: 'verde', 'amarillo' o 'rojo'.
    None (nunca compró) => 'rojo' (inactivo).
    """
    if dias_ultima_compra is None:
        return "rojo"
    if dias_ultima_compra <= ACTIVIDAD_VERDE_DIAS:
        return "verde"
    if dias_ultima_compra <= ACTIVIDAD_AMARILLO_DIAS:
        return "amarillo"
    return "rojo"


def calcular_semaforo_stock(total_blisters: int, minimo_blisters: int) -> str | None:
    """Semáforo de stock crítico contra el mínimo configurado del producto.

    Se compara en blísters y no en cajas por dos razones: revive
    `stock_minimo_blisters`, que hoy se carga y no lo lee nadie, y hace que la
    banda amarilla exista — con mínimo "1 caja" no hay ningún entero entre 1 y
    1,5, así que en cajas el amarillo nunca se pinta.

    Returns: None si el producto no tiene mínimo configurado (no se pinta),
    'rojo', 'amarillo' o 'verde'.
    """
    if minimo_blisters <= 0:
        return None
    if total_blisters <= minimo_blisters:
        return "rojo"
    if total_blisters * STOCK_AVISO_DEN <= minimo_blisters * STOCK_AVISO_NUM:
        return "amarillo"
    return "verde"


def calcular_semaforo(deuda: float, days_overdue: int | None) -> str:
    """Calculate client traffic light based on the age of the oldest unpaid debt.

    Returns: 'verde', 'amarillo', or 'rojo'
    """
    if deuda <= 0:
        return "verde"

    if days_overdue is None:
        # If there's debt but no specific order date found (e.g. only deuda_inicial),
        # we treat it as old debt (>60 days).
        return "rojo"

    if days_overdue > 60:
        return "rojo"
    elif days_overdue >= 30:
        return "amarillo"

    return "verde"


def calcular_semaforo_pedido(
    shipping_status: str,
    payment_status: str,
    fecha_entrega: date | None,
    despachado: bool,
    fecha_compromiso_pago: date | None,
) -> str:
    """Calculate pedido traffic light based on shipping_status, payment_status, and delivery date.

    Returns: 'rojo', 'azul', 'verde', 'amarillo', or 'gris'
    - gris    → Sin circuito activo (borrador, entregado o cancelado)
    - verde   → Listo para despacho
    - amarillo → Aguardando pago (tiene fecha de compromiso y no está despachado)
    - rojo    → Despacha hoy/mañana o cargado sin fecha
    - azul    → Despacha pasado mañana
    """
    # `borrador` entra acá porque todavía no es una venta: no tiene sentido
    # apurar la entrega de un pedido que el vendedor está tipeando.
    CERRADOS = {"borrador", "entregado", "cancelado"}

    if shipping_status in CERRADOS or payment_status == "cancelado":
        return "gris"

    if shipping_status == "listo_para_despacho":
        return "verde"

    if fecha_compromiso_pago and not despachado:
        return "amarillo"

    if fecha_entrega:
        today = date.today()
        delta = (fecha_entrega - today).days
        if delta <= 1:
            return "rojo"
        if delta == 2:
            return "azul"

    return "rojo"  # sin fecha = cargado sin planificar

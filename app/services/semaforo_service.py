from datetime import date


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
    - gris    → Cerrado (entregado o cancelado)
    - verde   → Listo para despacho
    - amarillo → Aguardando pago (tiene fecha de compromiso y no está despachado)
    - rojo    → Despacha hoy/mañana o cargado sin fecha
    - azul    → Despacha pasado mañana
    """
    CERRADOS = {"entregado", "cancelado"}

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

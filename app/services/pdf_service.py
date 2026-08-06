import os
from functools import partial
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, white
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    PageBreak, KeepTogether, Flowable,
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics import renderPDF
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from num2words import num2words
from app.core.config import settings

BLUE = HexColor("#003087")
BLUE_DARK = HexColor("#001B5A")
RED = HexColor("#E31837")
LIGHT_BG = HexColor("#F0F4F8")
PAGE_W, PAGE_H = A4

APP_NAME = settings.APP_NAME


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def numero_a_letras(importe: float) -> str:
    entero = int(importe)
    centavos = int(round((importe - entero) * 100))
    texto = num2words(entero, lang='es').upper()
    return f"{texto} PESOS ARGENTINOS CON {centavos:02d}/100"


def _draw_page_header_footer(canvas, doc, title_text: str, doc_number: str):
    """Draw consistent header and footer on every page."""
    canvas.saveState()

    # --- Header bar ---
    canvas.setFillColor(BLUE_DARK)
    canvas.rect(0, PAGE_H - 28, PAGE_W, 28, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(doc.leftMargin, PAGE_H - 20, f"{APP_NAME}")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(PAGE_W - doc.rightMargin, PAGE_H - 20, f"{title_text}  |  {doc_number}")

    # --- Footer ---
    canvas.setStrokeColor(colors.grey)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 35, PAGE_W - doc.rightMargin, 35)

    canvas.setFillColor(colors.grey)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(doc.leftMargin, 24, "Documento no válido como factura")
    canvas.drawRightString(PAGE_W - doc.rightMargin, 24, f"Página {doc.page}")

    canvas.setFillColor(BLUE)
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(PAGE_W / 2, 14, f"{APP_NAME} © 2024  —  Droguería y Distribuidora de Medicamentos")

    canvas.restoreState()


def _get_styles():
    """Return a dict of reusable paragraph styles."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle('PDFTitle', parent=base['Title'], fontSize=18, textColor=BLUE, spaceAfter=4),
        "subtitle": ParagraphStyle('PDFSubtitle', parent=base['Normal'], fontSize=14, textColor=RED, alignment=TA_CENTER, spaceAfter=10, spaceBefore=4),
        "normal": ParagraphStyle('PDFNormal', parent=base['Normal'], fontSize=9, leading=12),
        "normal_sm": ParagraphStyle('PDFNormalSm', parent=base['Normal'], fontSize=8, leading=10),
        "small": ParagraphStyle('PDFSmall', parent=base['Normal'], fontSize=7, textColor=colors.grey),
        "header_cell": ParagraphStyle('PDFHdrCell', parent=base['Normal'], fontSize=8, textColor=white, leading=10),
        "section": ParagraphStyle('PDFSection', parent=base['Normal'], fontSize=11, textColor=BLUE, spaceBefore=6, spaceAfter=4),
        "right_bold": ParagraphStyle('PDFRightBold', parent=base['Normal'], fontSize=10, alignment=TA_RIGHT),
        "center": ParagraphStyle('PDFCenter', parent=base['Normal'], fontSize=9, alignment=TA_CENTER, leading=12),
        "right": ParagraphStyle('PDFRight', parent=base['Normal'], fontSize=9, alignment=TA_RIGHT, leading=12),
        "company_sub": ParagraphStyle('PDFCompSub', parent=base['Normal'], fontSize=9, textColor=BLUE, alignment=TA_CENTER),
    }


def _info_table_style():
    return TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), LIGHT_BG),
        ('BACKGROUND', (2, 0), (2, -1), LIGHT_BG),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ])


def _product_table_style(num_rows: int):
    """Build style for product tables with alternating rows."""
    cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.Color(0.8, 0.8, 0.8)),
        ('LINEBELOW', (0, 0), (-1, 0), 1, BLUE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]
    alt = [white, LIGHT_BG]
    for i in range(1, num_rows):
        cmds.append(('BACKGROUND', (0, i), (-1, i), alt[i % 2]))
    return TableStyle(cmds)


def _build_company_header(elements, s, sub_title: str):
    """Append the company header block (used on the first page body)."""
    elements.append(Paragraph(settings.APP_NAME, s["title"]))
    elements.append(Paragraph("Droguería y Distribuidora de Medicamentos", s["company_sub"]))
    elements.append(Spacer(1, 5 * mm))
    elements.append(Paragraph(sub_title, s["subtitle"]))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        "CUIT: 30-12345678-9 | Domicilio: Av. Corrientes 1234, CABA | Resp. Inscripto",
        s["small"],
    ))
    elements.append(Spacer(1, 5 * mm))


# ---------------------------------------------------------------------------
# RECIBO / REMITO PDF
# ---------------------------------------------------------------------------

def generate_pago_recibo_pdf(
    pago_data: dict,
    cliente_data: dict,
    receptor_nombre: str,
) -> str:
    """Generate a clean receipt focused ONLY on payment details."""
    filename = f"RECIBO_{pago_data['numero_recibo']}.pdf"
    filepath = os.path.join(settings.PDF_STORAGE_PATH, filename)
    os.makedirs(settings.PDF_STORAGE_PATH, exist_ok=True)

    doc_title = "COMPROBANTE DE PAGO"
    doc_number = pago_data.get('numero_recibo', '')

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        topMargin=2.2 * cm, bottomMargin=2 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )
    s = _get_styles()
    elements = []

    # --- Company header ---
    _build_company_header(elements, s, doc_title)

    # --- Header Info ---
    fecha_str = str(pago_data.get('fecha_recepcion', ''))[:10]
    info_data = [
        [Paragraph('<b>Fecha de Recibo</b>', s["normal"]), Paragraph(fecha_str, s["normal"]),
         Paragraph('<b>N° de Control</b>', s["normal"]), Paragraph(doc_number, s["normal"])],
        [Paragraph('<b>Cliente</b>', s["normal"]), Paragraph(str(cliente_data.get('nombre', '')), s["normal"]),
         Paragraph('<b>CUIT / DNI</b>', s["normal"]), Paragraph(str(cliente_data.get('cuit', '-')), s["normal"])],
        [Paragraph('<b>Dirección</b>', s["normal"]), Paragraph(str(cliente_data.get('domicilio', '')), s["normal"]),
         Paragraph('<b>Localidad</b>', s["normal"]), Paragraph(str(cliente_data.get('localidad', '')), s["normal"])],
    ]
    info_tbl = Table(info_data, colWidths=[90, 145, 90, 145])
    info_tbl.setStyle(_info_table_style())
    elements.append(info_tbl)
    elements.append(Spacer(1, 10 * mm))

    # --- Amount Block (Prominent) ---
    importe = float(pago_data.get('importe', 0))
    importe_letras = numero_a_letras(importe)
    
    amount_data = [
        [
            Paragraph(f'<font size="14">RECIBIMOS LA SUMA DE:</font><br/><br/><b><font size="18" color="#003087">{format_currency_local(importe)}</font></b>', s["center"]),
        ],
        [
            Paragraph(f'SON: <i>{importe_letras}</i>', s["center"]),
        ]
    ]
    amount_tbl = Table(amount_data, colWidths=[PAGE_W - 3.6 * cm])
    amount_tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, BLUE),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
    ]))
    elements.append(amount_tbl)
    elements.append(Spacer(1, 10 * mm))

    # --- Payment Method Details ---
    tipo_pago = pago_data.get('tipo_pago', 'efectivo')
    elements.append(Paragraph("MODALIDAD DE PAGO", s["section"]))
    
    method_rows = [
        [Paragraph('<b>Forma de Pago</b>', s["header_cell"]), Paragraph('<b>Detalle Adicional</b>', s["header_cell"])],
        [Paragraph(str(tipo_pago).replace('_', ' ').title(), s["normal"]),
         Paragraph(_build_payment_detail_string(pago_data), s["normal"])]
    ]
    method_tbl = Table(method_rows, colWidths=[150, 320])
    method_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(method_tbl)
    elements.append(Spacer(1, 10 * mm))

    # --- Detailed Method Tables if available ---
    if tipo_pago == 'cheque':
        ch_rows = [
            [Paragraph('<b>Banco</b>', s["header_cell"]), Paragraph('<b>N° Cheque</b>', s["header_cell"]),
             Paragraph('<b>Fecha Emisión</b>', s["header_cell"]), Paragraph('<b>Vencimiento</b>', s["header_cell"])],
            [Paragraph(str(pago_data.get('ch_banco', '-')), s["normal"]),
             Paragraph(str(pago_data.get('ch_numero', '-')), s["normal"]),
             Paragraph(str(pago_data.get('ch_fecha', '-')), s["normal"]),
             Paragraph(str(pago_data.get('ch_vto', '-')), s["normal"])],
        ]
        ch_tbl = Table(ch_rows, colWidths=[117, 117, 117, 117])
        ch_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(ch_tbl)
        elements.append(Spacer(1, 5 * mm))

    elif tipo_pago == 'transferencia':
        tr_rows = [
            [Paragraph('<b>N° de Comprobante / Referencia</b>', s["header_cell"]), 
             Paragraph('<b>Fecha Transferencia</b>', s["header_cell"])],
            [Paragraph(str(pago_data.get('transferencia_numero', '-')), s["normal"]),
             Paragraph(str(pago_data.get('transferencia_fecha', '-')), s["normal"])],
        ]
        tr_tbl = Table(tr_rows, colWidths=[300, 170])
        tr_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(tr_tbl)
        elements.append(Spacer(1, 5 * mm))

    # --- Observations ---
    obs = pago_data.get('observacion', '')
    if obs:
        elements.append(Paragraph("OBSERVACIONES / CONCEPTO", s["section"]))
        elements.append(Paragraph(str(obs), s["normal"]))
        elements.append(Spacer(1, 10 * mm))

    # --- Signature Block ---
    elements.append(Spacer(1, 20 * mm))
    sig_data = [
        [Spacer(1, 10 * mm), Spacer(1, 10 * mm)],
        [Paragraph("-------------------------------------------", s["center"]), 
         Paragraph("-------------------------------------------", s["center"])],
        [Paragraph(f"<b>Recibido por: {receptor_nombre}</b>", s["center"]), 
         Paragraph("<b>Firma y Sello del Cliente</b>", s["center"])]
    ]
    sig_tbl = Table(sig_data, colWidths=[240, 240])
    elements.append(sig_tbl)

    # Build PDF
    on_page = partial(_draw_page_header_footer, title_text=doc_title, doc_number=doc_number)
    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return filename


def format_currency_local(val: float) -> str:
    return f"$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _build_payment_detail_string(pago: dict) -> str:
    tipo = pago.get('tipo_pago')
    if tipo == 'cheque':
        return f"Cheque {pago.get('ch_banco', '')} N° {pago.get('ch_numero', '')}"
    if tipo == 'transferencia':
        return f"Transferencia Ref. {pago.get('transferencia_numero', '')}"
    if tipo == 'retencion':
        return f"Retención {pago.get('retencion_tipo', '')} N° {pago.get('retencion_numero', '')}"
    return "Pago al contado / Efectivo"


def generate_recibo_pdf(
    pago_data: dict,
    cliente_data: dict,
    receptor_nombre: str,
    sin_valores: bool = False,
    items: list[dict] | None = None,
) -> str:
    # We keep this generic hybrid version in case it's used as a "Remito" for goods
    suffix = "_remito" if sin_valores else ""
    filename = f"{pago_data['numero_recibo']}{suffix}.pdf"
    filepath = os.path.join(settings.PDF_STORAGE_PATH, filename)
    os.makedirs(settings.PDF_STORAGE_PATH, exist_ok=True)

    doc_title = "REMITO AUTORIZADO" if sin_valores else "RECIBO AUTORIZADO"
    doc_number = pago_data.get('numero_recibo', '')

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        topMargin=2.2 * cm, bottomMargin=2 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )
    s = _get_styles()
    elements = []

    # --- Company header ---
    _build_company_header(elements, s, doc_title)

    # --- Client / payment info ---
    fecha_str = str(pago_data.get('fecha_recepcion', ''))[:10]
    info_data = [
        [Paragraph('<b>Fecha Pago</b>', s["normal"]), Paragraph(fecha_str, s["normal"]),
         Paragraph('<b>N° Recibo</b>', s["normal"]), Paragraph(doc_number, s["normal"])],
        [Paragraph('<b>Cliente</b>', s["normal"]), Paragraph(str(cliente_data.get('nombre', '')), s["normal"]),
         Paragraph('<b>CUIT</b>', s["normal"]), Paragraph(str(cliente_data.get('cuit', '-')), s["normal"])],
        [Paragraph('<b>Domicilio</b>', s["normal"]), Paragraph(str(cliente_data.get('domicilio', '')), s["normal"]),
         Paragraph('<b>Localidad</b>', s["normal"]), Paragraph(str(cliente_data.get('localidad', '')), s["normal"])],
        [Paragraph('<b>Razón Social</b>', s["normal"]), Paragraph(str(cliente_data.get('razon_social', '-')), s["normal"]),
         Paragraph('<b>Teléfono</b>', s["normal"]), Paragraph(str(cliente_data.get('telefono', '-')), s["normal"])],
    ]
    info_tbl = Table(info_data, colWidths=[75, 160, 75, 160])
    info_tbl.setStyle(_info_table_style())
    elements.append(info_tbl)
    elements.append(Spacer(1, 6 * mm))

    # --- Payment summary ---
    section_label = "REMITO (SIN VALORES)" if sin_valores else "DETALLE DEL PAGO"
    elements.append(Paragraph(section_label, s["section"]))

    importe = 0.0 if sin_valores else float(pago_data.get('importe', 0))
    importe_letras = numero_a_letras(importe)
    tipo_display = str(pago_data.get('tipo_pago', '')).replace('_', ' ').title()

    pay_data = [
        [Paragraph('<b>Importe</b>', s["header_cell"]),
         Paragraph('<b>Detalle</b>', s["header_cell"]),
         Paragraph('<b>Medio de Pago</b>', s["header_cell"])],
        [Paragraph(f'$ {importe:,.2f}', s["normal"]),
         Paragraph(importe_letras, s["normal_sm"]),
         Paragraph(tipo_display, s["normal"])],
    ]
    pay_tbl = Table(pay_data, colWidths=[100, 250, 120])
    pay_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(pay_tbl)
    elements.append(Spacer(1, 6 * mm))

    # --- Products detail (paginated automatically) ---
    if items:
        elements.append(Paragraph("DETALLE DE PRODUCTOS", s["section"]))

        header_row = [
            Paragraph('<b>Pedido</b>', s["header_cell"]),
            Paragraph('<b>Producto</b>', s["header_cell"]),
            Paragraph('<b>Cant.</b>', s["header_cell"]),
            Paragraph('<b>Precio Unit.</b>', s["header_cell"]),
            Paragraph('<b>Subtotal</b>', s["header_cell"]),
        ]
        rows = [header_row]
        grand_total = 0.0
        for item in items:
            p_unit = 0.0 if sin_valores else float(item.get('precio_unitario', 0))
            p_total = 0.0 if sin_valores else float(item.get('precio_total', 0))
            grand_total += p_total
            rows.append([
                Paragraph(str(item.get('numero_pedido', '')), s["normal_sm"]),
                Paragraph(str(item.get('producto_nombre', '')), s["normal_sm"]),
                Paragraph(str(item.get('cantidad', 0)), ParagraphStyle('_c', parent=s["normal_sm"], alignment=TA_CENTER)),
                Paragraph(f"$ {p_unit:,.2f}", ParagraphStyle('_r', parent=s["normal_sm"], alignment=TA_RIGHT)),
                Paragraph(f"$ {p_total:,.2f}", ParagraphStyle('_r2', parent=s["normal_sm"], alignment=TA_RIGHT)),
            ])

        tbl = Table(rows, colWidths=[65, 185, 45, 85, 90], repeatRows=1)
        tbl.setStyle(_product_table_style(len(rows)))
        elements.append(tbl)
        elements.append(Spacer(1, 3 * mm))
        elements.append(Paragraph(f"<b>TOTAL PRODUCTOS: $ {grand_total:,.2f}</b>", s["right_bold"]))
        elements.append(Spacer(1, 5 * mm))

    # --- Cheque section ---
    if pago_data.get('tipo_pago') == 'cheque' and any([pago_data.get('ch_banco'), pago_data.get('ch_numero')]):
        elements.append(Paragraph("DATOS DE CHEQUE", s["section"]))
        ch_rows = [
            [Paragraph('<b>Banco</b>', s["header_cell"]), Paragraph('<b>Número</b>', s["header_cell"]),
             Paragraph('<b>Fecha</b>', s["header_cell"]), Paragraph('<b>Vencimiento</b>', s["header_cell"])],
            [Paragraph(str(pago_data.get('ch_banco', '-')), s["normal"]),
             Paragraph(str(pago_data.get('ch_numero', '-')), s["normal"]),
             Paragraph(str(pago_data.get('ch_fecha', '-')), s["normal"]),
             Paragraph(str(pago_data.get('ch_vto', '-')), s["normal"])],
        ]
        ch_tbl = Table(ch_rows, colWidths=[117, 117, 117, 117])
        ch_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(ch_tbl)
        elements.append(Spacer(1, 5 * mm))

    # --- Observations ---
    obs = pago_data.get('observacion', '')
    if obs:
        elements.append(Paragraph("OBSERVACIONES", s["section"]))
        elements.append(Paragraph(str(obs), s["normal"]))
        elements.append(Spacer(1, 5 * mm))

    # --- Signature ---
    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph(f"Recibido por: <b>{receptor_nombre}</b>", ParagraphStyle('_sig', parent=s["normal"], alignment=TA_RIGHT)))

    # Build with per-page header/footer
    on_page = partial(_draw_page_header_footer, title_text=doc_title, doc_number=doc_number)
    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return filename


def generate_recibo_pdf_sin_valores(pago_data: dict, cliente_data: dict, receptor_nombre: str, items: list[dict] | None = None) -> str:
    return generate_recibo_pdf(pago_data, cliente_data, receptor_nombre, sin_valores=True, items=items)


# ---------------------------------------------------------------------------
# PEDIDO PDF
# ---------------------------------------------------------------------------

def generate_pedido_pdf(pedido_data: dict, cliente_data: dict, vendedor_nombre: str, items: list[dict]) -> str:
    filename = f"{pedido_data['numero_pedido']}.pdf"
    filepath = os.path.join(settings.PDF_STORAGE_PATH, filename)
    os.makedirs(settings.PDF_STORAGE_PATH, exist_ok=True)

    tipo_doc = str(pedido_data.get('tipo_documento', 'remito') or 'remito').upper()
    doc_number = pedido_data['numero_pedido']
    doc_title = f"{tipo_doc} - {doc_number}"

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        topMargin=2.2 * cm, bottomMargin=2 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )
    s = _get_styles()
    elements = []

    # --- Company header ---
    _build_company_header(elements, s, doc_title)

    # --- Pedido info ---
    fecha_str = str(pedido_data.get('fecha', ''))[:10]
    fecha_ent = str(pedido_data.get('fecha_entrega', '') or '-')[:10]
    shipping = str(pedido_data.get('shipping_status', '')).upper()
    payment = str(pedido_data.get('payment_status', '')).upper()

    info_data = [
        [Paragraph('<b>N° Pedido</b>', s["normal"]), Paragraph(doc_number, s["normal"]),
         Paragraph('<b>Fecha</b>', s["normal"]), Paragraph(fecha_str, s["normal"])],
        [Paragraph('<b>Cliente</b>', s["normal"]), Paragraph(str(cliente_data.get('nombre', '')), s["normal"]),
         Paragraph('<b>CUIT</b>', s["normal"]), Paragraph(str(cliente_data.get('cuit', '-')), s["normal"])],
        [Paragraph('<b>Domicilio</b>', s["normal"]), Paragraph(str(cliente_data.get('domicilio', '')), s["normal"]),
         Paragraph('<b>Localidad</b>', s["normal"]), Paragraph(str(cliente_data.get('localidad', '')), s["normal"])],
        [Paragraph('<b>Vendedor</b>', s["normal"]), Paragraph(vendedor_nombre, s["normal"]),
         Paragraph('<b>Despacho</b>', s["normal"]), Paragraph(shipping, s["normal"])],
        [Paragraph('<b>Fecha Entrega</b>', s["normal"]), Paragraph(fecha_ent, s["normal"]),
         Paragraph('<b>Pago</b>', s["normal"]), Paragraph(payment, s["normal"])],
        [Paragraph('<b>Transporte</b>', s["normal"]), Paragraph(str(pedido_data.get('transporte') or '-'), s["normal"]),
         Paragraph('', s["normal"]), Paragraph('', s["normal"])],
    ]
    info_tbl = Table(info_data, colWidths=[75, 160, 75, 160])
    info_tbl.setStyle(_info_table_style())
    elements.append(info_tbl)
    elements.append(Spacer(1, 6 * mm))

    # --- Products (paginated, header repeats) ---
    elements.append(Paragraph("DETALLE DE PRODUCTOS", s["section"]))

    has_discount = any(item.get('descuento_porcentaje') for item in items)

    if has_discount:
        header_row = [
            Paragraph('<b>Producto</b>', s["header_cell"]),
            Paragraph('<b>Cant.</b>', s["header_cell"]),
            Paragraph('<b>P. Lista</b>', s["header_cell"]),
            Paragraph('<b>Desc%</b>', s["header_cell"]),
            Paragraph('<b>P. Unit.</b>', s["header_cell"]),
            Paragraph('<b>Subtotal</b>', s["header_cell"]),
        ]
        rows = [header_row]
        for item in items:
            desc = item.get('descuento_porcentaje')
            rows.append([
                Paragraph(str(item.get('producto_nombre', '')), s["normal_sm"]),
                Paragraph(str(item.get('cantidad', 0)), ParagraphStyle('_c', parent=s["normal_sm"], alignment=TA_CENTER)),
                Paragraph(f"$ {float(item.get('precio_lista') or item.get('precio_unitario', 0)):,.2f}", ParagraphStyle('_r', parent=s["normal_sm"], alignment=TA_RIGHT)),
                Paragraph(f"{float(desc):.1f}%" if desc else "-", ParagraphStyle('_c2', parent=s["normal_sm"], alignment=TA_CENTER)),
                Paragraph(f"$ {float(item.get('precio_unitario', 0)):,.2f}", ParagraphStyle('_r', parent=s["normal_sm"], alignment=TA_RIGHT)),
                Paragraph(f"$ {float(item.get('precio_total', 0)):,.2f}", ParagraphStyle('_r2', parent=s["normal_sm"], alignment=TA_RIGHT)),
            ])
        tbl = Table(rows, colWidths=[165, 40, 80, 45, 80, 60], repeatRows=1)
    else:
        header_row = [
            Paragraph('<b>Producto</b>', s["header_cell"]),
            Paragraph('<b>Cantidad</b>', s["header_cell"]),
            Paragraph('<b>Precio Unit.</b>', s["header_cell"]),
            Paragraph('<b>Subtotal</b>', s["header_cell"]),
        ]
        rows = [header_row]
        for item in items:
            rows.append([
                Paragraph(str(item.get('producto_nombre', '')), s["normal_sm"]),
                Paragraph(str(item.get('cantidad', 0)), ParagraphStyle('_c', parent=s["normal_sm"], alignment=TA_CENTER)),
                Paragraph(f"$ {float(item.get('precio_unitario', 0)):,.2f}", ParagraphStyle('_r', parent=s["normal_sm"], alignment=TA_RIGHT)),
                Paragraph(f"$ {float(item.get('precio_total', 0)):,.2f}", ParagraphStyle('_r2', parent=s["normal_sm"], alignment=TA_RIGHT)),
            ])
        tbl = Table(rows, colWidths=[210, 65, 100, 95], repeatRows=1)

    tbl.setStyle(_product_table_style(len(rows)))
    elements.append(tbl)
    elements.append(Spacer(1, 4 * mm))

    importe_total = float(pedido_data.get('importe_total', 0))
    elements.append(Paragraph(f"<b>TOTAL: $ {importe_total:,.2f}</b>", s["right_bold"]))
    elements.append(Spacer(1, 5 * mm))

    # --- Observations ---
    obs = pedido_data.get('observacion', '')
    if obs:
        elements.append(Paragraph("OBSERVACIONES", s["section"]))
        elements.append(Paragraph(str(obs), s["normal"]))
        elements.append(Spacer(1, 5 * mm))

    # Build with per-page header/footer
    on_page = partial(_draw_page_header_footer, title_text=doc_title, doc_number=doc_number)
    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return filename


# ---------------------------------------------------------------------------
# ORDEN DE COMPRA PDF
# ---------------------------------------------------------------------------

def generate_orden_compra_pdf(ingreso_data: dict, proveedor_data: dict, items: list[dict], pagos: list[dict] | None = None) -> str:
    """Generate a purchase order (Orden de Compra) PDF for an IngresoMercaderia."""
    doc_number = ingreso_data.get("numero", "")
    filename = f"OC_{doc_number}.pdf"
    filepath = os.path.join(settings.PDF_STORAGE_PATH, filename)
    os.makedirs(settings.PDF_STORAGE_PATH, exist_ok=True)

    doc_title = "ORDEN DE COMPRA"

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        topMargin=2.2 * cm, bottomMargin=2 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )
    s = _get_styles()
    elements = []

    # --- Company header ---
    _build_company_header(elements, s, doc_title)

    # --- Main info table ---
    fecha_str = str(ingreso_data.get("fecha", ""))[:10]
    num_comprobante = ingreso_data.get("numero_comprobante") or "—"
    destino = ingreso_data.get("destino", "A")
    destino_label = f"Stock {'A (Sanalle)' if destino == 'A' else 'B (Farmacare)'}"
    dias_plazo = ingreso_data.get("dias_plazo")
    fecha_vto = ingreso_data.get("fecha_vencimiento")
    fecha_vto_str = str(fecha_vto)[:10] if fecha_vto else "—"
    creado_por = ingreso_data.get("creado_por_nombre") or "—"

    info_data = [
        [Paragraph("<b>N° Orden</b>", s["normal"]),    Paragraph(doc_number, s["normal"]),
         Paragraph("<b>Fecha</b>", s["normal"]),        Paragraph(fecha_str, s["normal"])],
        [Paragraph("<b>N° Comprobante</b>", s["normal"]), Paragraph(num_comprobante, s["normal"]),
         Paragraph("<b>Destino</b>", s["normal"]),      Paragraph(destino_label, s["normal"])],
        [Paragraph("<b>Proveedor</b>", s["normal"]),    Paragraph(proveedor_data.get("nombre") or "—", s["normal"]),
         Paragraph("<b>Contacto</b>", s["normal"]),     Paragraph(proveedor_data.get("contacto_nombre") or "—", s["normal"])],
        [Paragraph("<b>Plazo de Pago</b>", s["normal"]), Paragraph(f"{dias_plazo} días" if dias_plazo else "—", s["normal"]),
         Paragraph("<b>Vencimiento</b>", s["normal"]),  Paragraph(fecha_vto_str, s["normal"])],
        [Paragraph("<b>Registrado por</b>", s["normal"]), Paragraph(creado_por, s["normal"]),
         Paragraph("<b>Fecha Registro</b>", s["normal"]), Paragraph(str(ingreso_data.get("created_at", ""))[:10], s["normal"])],
    ]
    info_tbl = Table(info_data, colWidths=[90, 155, 90, 135])
    info_tbl.setStyle(_info_table_style())
    elements.append(info_tbl)
    elements.append(Spacer(1, 4 * mm))

    # --- Proveedor contact details (if available) ---
    prov_lines = []
    if proveedor_data.get("direccion"):
        prov_lines.append(f"Dirección: {proveedor_data['direccion']}")
    if proveedor_data.get("telefono"):
        prov_lines.append(f"Tel.: {proveedor_data['telefono']}")
    if proveedor_data.get("contacto_telefono"):
        prov_lines.append(f"Tel. Contacto: {proveedor_data['contacto_telefono']}")
    if proveedor_data.get("contacto_email"):
        prov_lines.append(f"Email: {proveedor_data['contacto_email']}")
    if prov_lines:
        elements.append(Paragraph(
            "  |  ".join(prov_lines),
            ParagraphStyle("_prov_sub", parent=s["small"], spaceAfter=4),
        ))
    elements.append(Spacer(1, 4 * mm))

    # --- Items table ---
    elements.append(Paragraph("DETALLE DE PRODUCTOS", s["section"]))

    has_blisters = any(item.get("cantidad_blisters", 0) for item in items)
    has_costo = any(item.get("costo_unitario") is not None for item in items)

    if has_costo:
        col_hdr = [
            Paragraph("<b>Producto</b>", s["header_cell"]),
            Paragraph("<b>Cajas</b>", s["header_cell"]),
            Paragraph("<b>Blisters</b>", s["header_cell"]) if has_blisters else Paragraph("", s["header_cell"]),
            Paragraph("<b>Costo Unit.</b>", s["header_cell"]),
            Paragraph("<b>Subtotal</b>", s["header_cell"]),
        ]
        rows = [col_hdr]
        grand_total = 0.0
        for item in items:
            costo = item.get("costo_unitario")
            subtotal = float(costo) * item.get("cantidad_cajas", 0) if costo is not None else None
            if subtotal is not None:
                grand_total += subtotal
            rows.append([
                Paragraph(str(item.get("producto_nombre") or f"Producto #{item.get('producto_id', '?')}"), s["normal_sm"]),
                Paragraph(str(item.get("cantidad_cajas", 0)), ParagraphStyle("_c", parent=s["normal_sm"], alignment=TA_CENTER)),
                Paragraph(str(item.get("cantidad_blisters", 0)) if has_blisters else "", ParagraphStyle("_c2", parent=s["normal_sm"], alignment=TA_CENTER)),
                Paragraph(format_currency_local(float(costo)) if costo is not None else "—", ParagraphStyle("_r", parent=s["normal_sm"], alignment=TA_RIGHT)),
                Paragraph(format_currency_local(subtotal) if subtotal is not None else "—", ParagraphStyle("_r2", parent=s["normal_sm"], alignment=TA_RIGHT)),
            ])
        col_w = [175, 45, 45, 90, 115] if has_blisters else [220, 45, 0, 90, 115]
        if not has_blisters:
            # Remove the empty blisters column from data
            rows = [[r[0], r[1], r[3], r[4]] for r in rows]
            col_w = [230, 55, 100, 85]
    else:
        col_hdr = [
            Paragraph("<b>Producto</b>", s["header_cell"]),
            Paragraph("<b>Cajas</b>", s["header_cell"]),
            Paragraph("<b>Blisters</b>", s["header_cell"]) if has_blisters else None,
        ]
        col_hdr = [h for h in col_hdr if h is not None]
        rows = [col_hdr]
        grand_total = 0.0
        for item in items:
            row = [
                Paragraph(str(item.get("producto_nombre") or f"Producto #{item.get('producto_id', '?')}"), s["normal_sm"]),
                Paragraph(str(item.get("cantidad_cajas", 0)), ParagraphStyle("_c", parent=s["normal_sm"], alignment=TA_CENTER)),
            ]
            if has_blisters:
                row.append(Paragraph(str(item.get("cantidad_blisters", 0)), ParagraphStyle("_c2", parent=s["normal_sm"], alignment=TA_CENTER)))
            rows.append(row)
        col_w = [350, 70, 50] if has_blisters else [380, 90]

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(_product_table_style(len(rows)))
    elements.append(tbl)
    elements.append(Spacer(1, 3 * mm))

    # --- Totals block ---
    importe_total = float(ingreso_data.get("importe_total", 0))
    saldo_pendiente = float(ingreso_data.get("saldo_pendiente", 0))

    if has_costo and grand_total > 0:
        elements.append(Paragraph(
            f"<b>TOTAL CALCULADO: {format_currency_local(grand_total)}</b>",
            s["right_bold"],
        ))
        elements.append(Spacer(1, 2 * mm))

    if importe_total > 0:
        importe_letras = numero_a_letras(importe_total)
        total_data = [
            [Paragraph(
                f'<font size="13">IMPORTE TOTAL</font><br/><br/>'
                f'<b><font size="20" color="#003087">{format_currency_local(importe_total)}</font></b>',
                s["center"],
            )],
            [Paragraph(f'SON: <i>{importe_letras}</i>', s["center"])],
        ]
        if saldo_pendiente > 0 and saldo_pendiente < importe_total:
            total_data.append([
                Paragraph(
                    f'Saldo pendiente: <b><font color="#E31837">{format_currency_local(saldo_pendiente)}</font></b>',
                    s["center"],
                )
            ])
        total_tbl = Table(total_data, colWidths=[PAGE_W - 3.6 * cm])
        total_tbl.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, BLUE),
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        elements.append(total_tbl)
        elements.append(Spacer(1, 5 * mm))

    # --- Payment history ---
    if pagos:
        elements.append(Paragraph("HISTORIAL DE PAGOS", s["section"]))
        pay_header = [
            Paragraph("<b>Fecha</b>", s["header_cell"]),
            Paragraph("<b>Medio de Pago</b>", s["header_cell"]),
            Paragraph("<b>Referencia</b>", s["header_cell"]),
            Paragraph("<b>Importe Aplicado</b>", s["header_cell"]),
        ]
        pay_rows = [pay_header]
        total_pagado = 0.0
        for p in pagos:
            importe_ap = float(p.get("importe_aplicado", 0))
            total_pagado += importe_ap
            fecha_p = str(p.get("fecha_pago", ""))[:10]
            tipo_p = str(p.get("tipo_pago", "")).replace("_", " ").title()
            ref_p = str(p.get("referencia_pago") or "—")
            pay_rows.append([
                Paragraph(fecha_p, s["normal_sm"]),
                Paragraph(tipo_p, s["normal_sm"]),
                Paragraph(ref_p, s["normal_sm"]),
                Paragraph(format_currency_local(importe_ap), ParagraphStyle("_rp", parent=s["normal_sm"], alignment=TA_RIGHT)),
            ])
        GREEN = HexColor("#15803D")
        pay_rows.append([
            Paragraph("", s["normal_sm"]),
            Paragraph("", s["normal_sm"]),
            Paragraph("<b>TOTAL PAGADO</b>", ParagraphStyle("_tot", parent=s["normal_sm"], alignment=TA_RIGHT)),
            Paragraph(f"<b>{format_currency_local(total_pagado)}</b>", ParagraphStyle("_totr", parent=s["normal_sm"], alignment=TA_RIGHT, textColor=GREEN)),
        ])
        pay_tbl = Table(pay_rows, colWidths=[75, 110, 170, 115], repeatRows=1)
        pay_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("GRID", (0, 0), (-2, -2), 0.4, colors.Color(0.8, 0.8, 0.8)),
            ("LINEABOVE", (0, -1), (-1, -1), 1, BLUE),
            ("BACKGROUND", (0, -1), (-1, -1), LIGHT_BG),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            *[("BACKGROUND", (0, i), (-1, i), (white if i % 2 == 1 else LIGHT_BG)) for i in range(1, len(pay_rows) - 1)],
        ]))
        elements.append(pay_tbl)
        elements.append(Spacer(1, 5 * mm))

    # --- Observations ---
    obs = ingreso_data.get("observacion")
    if obs:
        elements.append(Paragraph("OBSERVACIONES", s["section"]))
        elements.append(Paragraph(str(obs), s["normal"]))
        elements.append(Spacer(1, 5 * mm))

    # --- Signature block ---
    elements.append(Spacer(1, 15 * mm))
    sig_data = [
        [Spacer(1, 10 * mm), Spacer(1, 10 * mm)],
        [Paragraph("———————————————————————————", s["center"]),
         Paragraph("———————————————————————————", s["center"])],
        [Paragraph(f"<b>Autorizado por: {creado_por}</b>", s["center"]),
         Paragraph("<b>Firma y Sello del Proveedor</b>", s["center"])],
    ]
    sig_tbl = Table(sig_data, colWidths=[240, 240])
    elements.append(sig_tbl)

    on_page = partial(_draw_page_header_footer, title_text=doc_title, doc_number=doc_number)
    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return filename


# ---------------------------------------------------------------------------
# ESTADO DE CUENTA PDF
# ---------------------------------------------------------------------------

def generate_estado_cuenta_pdf(
    cliente_data: dict,
    movimientos: list,
    saldo_total: float,
    filtros: dict
) -> str:
    """Generate a statement of account for collections."""
    tipo_cuenta = filtros.get('tipo_cuenta')
    fecha_desde = filtros.get('fecha_desde')
    fecha_hasta = filtros.get('fecha_hasta')

    # Determine title suffix
    suffix = " - CONSOLIDADO"
    if tipo_cuenta == "factura":
        suffix = " - BLANCO (FACTURAS)"
    elif tipo_cuenta == "remito":
        suffix = " - NEGRO (REMITOS)"
        
    doc_title = f"ESTADO DE CUENTA{suffix}"
    
    import time
    timestamp = int(time.time())
    filename = f"ESTADO_CUENTA_{cliente_data.get('id', 'X')}_{timestamp}.pdf"
    filepath = os.path.join(settings.PDF_STORAGE_PATH, filename)
    os.makedirs(settings.PDF_STORAGE_PATH, exist_ok=True)

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        topMargin=2.2 * cm, bottomMargin=2 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    s = _get_styles()
    elements = []

    # --- Company header ---
    _build_company_header(elements, s, doc_title)

    # --- Header Info ---
    fecha_emision = time.strftime("%Y-%m-%d %H:%M")
    periodo = "Histórico"
    if fecha_desde and fecha_hasta:
        periodo = f"Desde {fecha_desde} hasta {fecha_hasta}"
    elif fecha_desde:
        periodo = f"Desde {fecha_desde}"
    elif fecha_hasta:
        periodo = f"Hasta {fecha_hasta}"

    info_data = [
        [Paragraph('<b>Cliente</b>', s["normal"]), Paragraph(str(cliente_data.get('nombre', '')), s["normal"]),
         Paragraph('<b>Fecha Emisión</b>', s["normal"]), Paragraph(fecha_emision, s["normal"])],
        [Paragraph('<b>CUIT</b>', s["normal"]), Paragraph(str(cliente_data.get('cuit', '-')), s["normal"]),
         Paragraph('<b>Período</b>', s["normal"]), Paragraph(periodo, s["normal"])],
        [Paragraph('<b>Domicilio</b>', s["normal"]), Paragraph(str(cliente_data.get('domicilio', '')), s["normal"]),
         Paragraph('', s["normal"]), Paragraph('', s["normal"])],
    ]
    info_tbl = Table(info_data, colWidths=[70, 200, 80, 160])
    info_tbl.setStyle(_info_table_style())
    elements.append(info_tbl)
    elements.append(Spacer(1, 10 * mm))

    # --- Movements Table ---
    elements.append(Paragraph("DETALLE DE MOVIMIENTOS", s["section"]))

    header_row = [
        Paragraph('<b>Fecha</b>', s["header_cell"]),
        Paragraph('<b>Tipo</b>', s["header_cell"]),
        Paragraph('<b>Comprobante</b>', s["header_cell"]),
        Paragraph('<b>Debe</b>', s["header_cell"]),
        Paragraph('<b>Haber</b>', s["header_cell"]),
        Paragraph('<b>Saldo</b>', s["header_cell"]),
    ]
    rows = [header_row]

    if not movimientos:
        rows.append([
            Paragraph("No hay movimientos registrados en el período.", s["center"]),
            "", "", "", "", ""
        ])
        tbl = Table(rows, colWidths=[510, 0, 0, 0, 0, 0])
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('SPAN', (0, 1), (-1, 1)),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
    else:
        for mov in movimientos:
            # Format numbers safely based on the type of mov (could be dict or object)
            debe = getattr(mov, 'debe', mov.get('debe', 0)) if isinstance(mov, dict) else mov.debe
            haber = getattr(mov, 'haber', mov.get('haber', 0)) if isinstance(mov, dict) else mov.haber
            saldo = getattr(mov, 'saldo', mov.get('saldo', 0)) if isinstance(mov, dict) else mov.saldo
            
            fecha = getattr(mov, 'fecha', mov.get('fecha', '')) if isinstance(mov, dict) else mov.fecha
            fecha_str = str(fecha)[:10] if fecha else ""
            
            tipo = getattr(mov, 'tipo', mov.get('tipo', '')) if isinstance(mov, dict) else mov.tipo
            numero = getattr(mov, 'numero', mov.get('numero', '')) if isinstance(mov, dict) else mov.numero
            
            rows.append([
                Paragraph(fecha_str, s["normal_sm"]),
                Paragraph(str(tipo), s["normal_sm"]),
                Paragraph(str(numero), s["normal_sm"]),
                Paragraph(f"{float(debe):,.2f}" if float(debe) > 0 else "-", ParagraphStyle('_r', parent=s["normal_sm"], alignment=TA_RIGHT, textColor=RED if float(debe)>0 else colors.black)),
                Paragraph(f"{float(haber):,.2f}" if float(haber) > 0 else "-", ParagraphStyle('_r2', parent=s["normal_sm"], alignment=TA_RIGHT, textColor=colors.green if float(haber)>0 else colors.black)),
                Paragraph(f"<b>{float(saldo):,.2f}</b>", ParagraphStyle('_r3', parent=s["normal_sm"], alignment=TA_RIGHT)),
            ])
            
        tbl = Table(rows, colWidths=[65, 80, 125, 80, 80, 80], repeatRows=1)
        tbl.setStyle(_product_table_style(len(rows)))

    elements.append(tbl)
    elements.append(Spacer(1, 10 * mm))

    # --- Final Balance ---
    saldo_color = RED if saldo_total > 0 else (colors.green if saldo_total < 0 else BLUE)
    saldo_str = format_currency_local(abs(saldo_total))
    
    if saldo_total > 0:
        saldo_label = "SALDO DEUDOR (DEBE)"
    elif saldo_total < 0:
        saldo_label = "SALDO A FAVOR"
    else:
        saldo_label = "CUENTA SALDADA"

    balance_data = [
        [
            Paragraph(f'<font size="14">{saldo_label}</font><br/><br/><b><font size="18" color="{saldo_color.hexval()}">{saldo_str}</font></b>', s["center"]),
        ]
    ]
    balance_tbl = Table(balance_data, colWidths=[PAGE_W - 3.0 * cm])
    balance_tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, BLUE),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
    ]))
    
    # Use KeepTogether so the balance stays with the end of the table if possible
    elements.append(KeepTogether(balance_tbl))

    # Build PDF
    on_page = partial(_draw_page_header_footer, title_text=doc_title, doc_number="")
    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    return filename

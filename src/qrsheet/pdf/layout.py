"""Measured character wrapping and page geometry."""
from reportlab.lib.pagesizes import A4, LETTER, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from qrsheet.qr.generator import UserError

MARGIN = 15 * mm
GAP = 6 * mm


def wrap_text(text, font, size, width):
    lines, current, used = [], "", 0.0
    for char in text:
        # A tab has no printable glyph; render spacing without changing QR data.
        display = "    " if char == "\t" else char
        advance = pdfmetrics.stringWidth(display, font, size)
        if current and used + advance > width:
            lines.append(current)
            current, used = "", 0.0
        current += display
        used += advance
    if current:
        lines.append(current)
    return lines


def geometry(settings, count):
    settings.validate()
    page = A4 if settings.paper == "A4" else LETTER
    if settings.landscape:
        page = landscape(page)
    available = page[0] - 2 * MARGIN
    qr_size = settings.qr_mm * mm
    columns = settings.columns or max(1, min(4, count, int((available + GAP) // (qr_size + 4 * mm + GAP))))
    cell_width = (available - (columns - 1) * GAP) / columns
    if qr_size + 4 * mm > cell_width:
        raise UserError("指定したQRサイズでは列に収まりません。列数を減らすかQRサイズを小さくしてください。")
    return page, columns, cell_width, qr_size

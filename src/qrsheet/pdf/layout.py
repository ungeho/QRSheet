"""Measured character wrapping and page geometry."""
from reportlab.lib.pagesizes import A4, LETTER, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from qrsheet.qr.generator import UserError



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
    available = page[0] - (settings.margin_left_mm + settings.margin_right_mm) * mm
    qr_size = settings.qr_mm * mm
    # Card width depends only on QR size, never the page or the column count.
    cell_width = qr_size + 4 * mm
    gap = settings.horizontal_gap_mm * mm
    capacity = int((available + gap + 1e-7) // (cell_width + gap))
    columns = settings.columns or max(1, min(4, count, capacity))
    if columns * cell_width + (columns - 1) * gap > available + 1e-7:
        raise UserError("指定した列数がページに収まりません。列数・QRサイズ・横間隔・左右余白を小さくしてください。")
    return page, columns, cell_width, qr_size


def axis_positions(sizes, available, gap, alignment):
    """Offsets from the leading edge; justify adds free space only between items."""
    if not sizes:
        return []
    free = available - sum(sizes) - gap * (len(sizes) - 1)
    if free < -1e-7:
        raise UserError("カードがページ内に収まりません。間隔・余白・サイズを確認してください。")
    free = max(0, free)
    offset = free / 2 if alignment == "center" else free if alignment in ("right", "bottom") else 0
    if alignment == "justify" and len(sizes) > 1:
        gap += free / (len(sizes) - 1)
    positions = []
    for size in sizes:
        positions.append(offset)
        offset += size + gap
    return positions


def content_bounds(settings, page, header_height):
    left = settings.margin_left_mm * mm
    right = page[0] - settings.margin_right_mm * mm
    top = page[1] - settings.margin_top_mm * mm - header_height
    # Reserve a footer line inside the printable region, including at zero margin.
    bottom = settings.margin_bottom_mm * mm + 14
    if top <= bottom:
        raise UserError("上下余白とヘッダーが大きすぎます。カードを配置する高さがありません。")
    return left, right, top, bottom


def paginate_rows(rows, available_height, gap):
    """Keep each row together, without adding a trailing gap to page capacity."""
    page_rows, used = [], 0
    for row in rows:
        height = max(entry[3] for entry in row)
        if height > available_height + 1e-7:
            raise UserError("カードが1ページに収まりません。QRサイズ・上下余白を小さくしてください。")
        required = height + (gap if page_rows else 0)
        if page_rows and used + required > available_height + 1e-7:
            yield page_rows
            page_rows, used = [], 0
            required = height
        page_rows.append(row)
        used += required
    if page_rows:
        yield page_rows

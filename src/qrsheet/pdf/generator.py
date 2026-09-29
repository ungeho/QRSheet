"""Atomic PDF creation; each row keeps its QR and full caption together."""
from datetime import date
import os
from pathlib import Path
import tempfile
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from qrsheet.qr.generator import generate_qr, UserError
from qrsheet.pdf.fonts import japanese_font
from qrsheet.pdf.layout import geometry, wrap_text, MARGIN, GAP


def generate_pdf(texts, destination, settings, progress=None):
    if not texts:
        raise UserError("1件以上の文字列を入力してください。")
    if len(texts) > 10000:
        raise UserError("一度に生成できるのは10,000件までです。入力を分けてください。")
    page, columns, cell_width, qr_size = geometry(settings, len(texts))
    font = japanese_font()
    glyphs = pdfmetrics.getFont(font).face.charToGlyph
    for index, text in enumerate([settings.title if settings.show_title else "", *texts]):
        if any(ord(char) not in glyphs for char in text if char != "\t"):
            label = "タイトル" if index == 0 else f"{index}件目"
            raise UserError(f"{label}: 使用中のフォントで表示できない文字があります。QRSHEET_FONTで対応する日本語TrueTypeフォントを指定してください。")
    header_lines = wrap_text(settings.title, font, 16, page[0] - 2 * MARGIN) if settings.show_title else []
    header_height = len(header_lines) * 21 + (18 if settings.show_date else 0) + 12
    top = page[1] - MARGIN - header_height
    bottom = MARGIN + 14
    max_height = top - bottom
    destination = Path(destination)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(suffix=".pdf", prefix=".qrsheet-", dir=destination.parent)
        os.close(fd)
        canvas = Canvas(temporary, pagesize=page)
        canvas.setTitle(settings.title if settings.show_title else "QRSheet")
        page_number = 1

        def decorate():
            canvas.setFillColorRGB(0.10, 0.15, 0.22)
            canvas.setFont(font, 16)
            y = page[1] - MARGIN - 16
            for line in header_lines:
                canvas.drawString(MARGIN, y, line)
                y -= 21
            if settings.show_date:
                canvas.setFont(font, 9)
                canvas.drawString(MARGIN, y, date.today().isoformat())
            canvas.setFont(font, 8)
            canvas.drawRightString(page[0] - MARGIN, MARGIN - 5, str(page_number))

        decorate()
        y = top
        for start in range(0, len(texts), columns):
            row = []
            for offset, text in enumerate(texts[start:start + columns]):
                try:
                    item = generate_qr(text)
                except UserError as exc:
                    raise UserError(f"{start + offset + 1}件目: {exc}") from exc
                # Reject physically unreadable dense symbols instead of silently shrinking.
                if qr_size / len(item.matrix) < 0.30 * mm:
                    raise UserError(f"{start + offset + 1}件目: QRが細かすぎます。QRサイズを大きくするか文字列を短くしてください。")
                size = 10
                while True:
                    lines = wrap_text(text, font, size, cell_width - 8 * mm)
                    height = qr_size + 12 * mm + len(lines) * size * 1.35
                    if height <= max_height or size <= 6:
                        break
                    size -= 1
                if height > max_height:
                    raise UserError(f"{start + offset + 1}件目: 文字列が1ページに収まりません。列数を減らすか用紙方向を変更してください。")
                row.append((item, size, lines, height))
            row_height = max(entry[3] for entry in row)
            if y - row_height < bottom:
                canvas.showPage()
                page_number += 1
                decorate()
                y = top
            for column, (item, size, lines, height) in enumerate(row):
                left = MARGIN + column * (cell_width + GAP)
                canvas.setStrokeColorRGB(0.83, 0.86, 0.90)
                canvas.roundRect(left, y - row_height, cell_width, row_height, 4, stroke=1, fill=0)
                origin_x = left + (cell_width - qr_size) / 2
                origin_y = y - 4 * mm
                module = qr_size / len(item.matrix)
                canvas.setFillColorRGB(0, 0, 0)
                path = canvas.beginPath()
                for r, values in enumerate(item.matrix):
                    for c, filled in enumerate(values):
                        if filled:
                            path.rect(origin_x + c * module, origin_y - (r + 1) * module, module, module)
                canvas.drawPath(path, stroke=0, fill=1)
                canvas.setFont(font, size)
                baseline = origin_y - qr_size - 4 * mm - size
                for line in lines:
                    canvas.drawString(left + 4 * mm, baseline, line)
                    baseline -= size * 1.35
            y -= row_height + GAP
            if progress:
                progress(min(start + columns, len(texts)), len(texts))
        canvas.save()
        os.replace(temporary, destination)
        temporary = None
        return page_number
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)

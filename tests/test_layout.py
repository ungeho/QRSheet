from dataclasses import replace

import pytest
from pypdf import PdfReader
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from qrsheet.pdf.generator import generate_pdf
from qrsheet.pdf.layout import axis_positions, geometry
from qrsheet.settings.manager import PdfSettings
from qrsheet.qr.generator import UserError


@pytest.mark.parametrize("horizontal", ["left", "center", "right", "justify"])
@pytest.mark.parametrize("vertical", ["top", "center", "bottom", "justify"])
@pytest.mark.parametrize("gap", [0, 5])
@pytest.mark.parametrize("columns", [1, 2, 3])
def test_generated_card_positions(tmp_path, monkeypatch, horizontal, vertical, gap, columns):
    settings = PdfSettings(columns=columns, horizontal_align=horizontal, vertical_align=vertical,
                           horizontal_gap_mm=gap, vertical_gap_mm=gap,
                           margin_left_mm=10, margin_right_mm=20,
                           margin_top_mm=12, margin_bottom_mm=18)
    cards = {}
    original = Canvas.roundRect
    def capture(canvas, x, y, width, height, *args, **kwargs):
        cards.setdefault(canvas.getPageNumber(), []).append((x, y, width, height))
        return original(canvas, x, y, width, height, *args, **kwargs)
    monkeypatch.setattr(Canvas, "roundRect", capture)
    path = tmp_path / "layout.pdf"
    texts = [f"日本語{i:03d}" for i in range(31)]
    pages = generate_pdf(texts, path, settings)
    reader = PdfReader(path)
    assert pages == len(reader.pages) > 1
    assert sum(map(len, cards.values())) == len(texts)
    page_width, page_height = geometry(settings, len(texts))[0]
    left, right = 10 * mm, page_width - 20 * mm
    top, bottom = page_height - 12 * mm - 51, 18 * mm + 14
    for rectangles in cards.values():
        rows = [rectangles[i:i + columns] for i in range(0, len(rectangles), columns)]
        for row in rows:
            for x, y, width, height in row:
                assert width == pytest.approx(39 * mm)
                assert x >= left - 1e-7 and x + width <= right + 1e-7
                assert y >= bottom - 1e-7 and y + height <= top + 1e-7
            for first, second in zip(row, row[1:]):
                actual_gap = second[0] - first[0] - first[2]
                if horizontal == "justify":
                    assert actual_gap >= gap * mm - 1e-7
                else:
                    assert actual_gap == pytest.approx(gap * mm)
        first_row = rows[0]
        xmin, xmax = first_row[0][0], first_row[-1][0] + first_row[-1][2]
        if horizontal == "left" or horizontal == "justify":
            assert xmin == pytest.approx(left)
        if horizontal == "right" or (horizontal == "justify" and len(first_row) > 1):
            assert xmax == pytest.approx(right)
        if horizontal == "center":
            assert xmin - left == pytest.approx(right - xmax)
        ymax, ymin = rows[0][0][1] + rows[0][0][3], rows[-1][0][1]
        if vertical in ("top", "justify"):
            assert ymax == pytest.approx(top)
        if vertical == "bottom" or (vertical == "justify" and len(rows) > 1):
            assert ymin == pytest.approx(bottom)
        if vertical == "center":
            assert top - ymax == pytest.approx(ymin - bottom)
        for first, second in zip(rows, rows[1:]):
            actual_gap = first[0][1] - second[0][1] - second[0][3]
            if vertical == "justify":
                assert actual_gap >= gap * mm - 1e-7
            else:
                assert actual_gap == pytest.approx(gap * mm)
    content = "".join(page.extract_text() for page in reader.pages)
    assert all(text in content for text in texts)


def test_fixed_width_and_example_positions():
    base = PdfSettings(columns=2)
    for variant in [base, replace(base, columns=1), replace(base, columns=3),
                    replace(base, paper="Letter", landscape=True), replace(base, horizontal_gap_mm=0)]:
        assert geometry(variant, 10)[2] == pytest.approx(39 * mm)
    positions = axis_positions([60 * mm] * 2, 190 * mm, 5 * mm, "left")
    assert [10 * mm + x for x in positions] == pytest.approx([10 * mm, 75 * mm])


@pytest.mark.parametrize("settings", [PdfSettings(columns=4, horizontal_gap_mm=20),
    PdfSettings(margin_left_mm=100, margin_right_mm=100), PdfSettings(vertical_gap_mm=-1),
    PdfSettings(horizontal_align="bad"), PdfSettings(margin_top_mm=101)])
def test_invalid_layout(tmp_path, settings):
    with pytest.raises(UserError):
        generate_pdf(["日本語"] * 5, tmp_path / "bad.pdf", settings)


def test_no_header_starts_at_top_margin(tmp_path, monkeypatch):
    tops = []
    original = Canvas.roundRect
    def capture(canvas, x, y, width, height, *args, **kwargs):
        tops.append(y + height)
        return original(canvas, x, y, width, height, *args, **kwargs)
    monkeypatch.setattr(Canvas, "roundRect", capture)
    settings = PdfSettings(show_title=False, show_date=False, margin_top_mm=0, margin_bottom_mm=0)
    generate_pdf(["日本語"], tmp_path / "zero.pdf", settings)
    assert tops[0] == pytest.approx(geometry(settings, 1)[0][1])

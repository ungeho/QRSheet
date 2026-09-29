from dataclasses import replace
import pytest
from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics
from qrsheet.pdf.generator import generate_pdf
from qrsheet.pdf.fonts import japanese_font
from qrsheet.pdf.layout import wrap_text
from qrsheet.settings.manager import PdfSettings
from qrsheet.qr.generator import UserError


@pytest.mark.parametrize("columns", [0, 1, 2, 3, 4])
@pytest.mark.parametrize("count", [1, 3, 100])
def test_pdf_pages_and_labels(tmp_path, columns, count):
    texts = [f"項目{i:03d} https://example.com/{i}" for i in range(count)]
    path = tmp_path / "test.pdf"
    pages = generate_pdf(texts, path, PdfSettings(columns=columns))
    reader = PdfReader(path)
    assert len(reader.pages) == pages
    if count == 100:
        assert pages > 1
    content = "".join(page.extract_text() for page in reader.pages).replace("\n", "")
    for text in texts:
        assert text in content
    assert "QRコード一覧" in content


def test_long_url(tmp_path):
    text = "https://example.com/" + "abcdef?x=1&y=2/" * 85
    path = tmp_path / "long.pdf"
    generate_pdf([text, "日本語"], path, PdfSettings(qr_mm=60, columns=2))
    content = "".join(p.extract_text() for p in PdfReader(path).pages).replace("\n", "")
    assert text in content


def test_wrapping_measured():
    font = japanese_font()
    text = "日本語の長い文字列https://example.com/" * 30
    lines = wrap_text(text, font, 10, 110)
    assert "".join(lines) == text
    assert all(pdfmetrics.stringWidth(line, font, 10) <= 110 for line in lines)


def test_orientation_and_hidden_header(tmp_path):
    path = tmp_path / "letter.pdf"
    generate_pdf(["hello"], path, PdfSettings(paper="Letter", landscape=True, show_title=False, show_date=False))
    page = PdfReader(path).pages[0]
    assert float(page.mediabox.width) == 792
    assert float(page.mediabox.height) == 612
    assert "QRコード一覧" not in page.extract_text()


@pytest.mark.parametrize("settings", [PdfSettings(columns=4, qr_mm=60), PdfSettings(columns=7), PdfSettings(paper="bad"), PdfSettings(qr_mm=0)])
def test_invalid_settings(tmp_path, settings):
    with pytest.raises(UserError):
        generate_pdf(["abc"], tmp_path / "bad.pdf", settings)


def test_atomic_failure(tmp_path):
    path = tmp_path / "existing.pdf"
    path.write_bytes(b"original")
    with pytest.raises(UserError):
        generate_pdf(["okay", "あ" * 2000], path, PdfSettings())
    assert path.read_bytes() == b"original"
    assert not list(tmp_path.glob(".qrsheet-*"))


def test_empty_and_too_many(tmp_path):
    for texts in [[], ["abc"] * 10001]:
        with pytest.raises(UserError):
            generate_pdf(texts, tmp_path / "bad.pdf", PdfSettings())


def test_dense_qr_requires_size(tmp_path):
    with pytest.raises(UserError, match="QRサイズ"):
        generate_pdf(["abc" * 400], tmp_path / "dense.pdf", PdfSettings(qr_mm=20))


def test_unwritable_destination(tmp_path):
    with pytest.raises(OSError):
        generate_pdf(["abc"], tmp_path / "missing" / "file.pdf", PdfSettings())

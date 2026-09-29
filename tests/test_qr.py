import pytest
from PIL import Image
import zxingcpp
from qrsheet.qr.generator import generate_qr, parse_lines, UserError


@pytest.mark.parametrize("text", ["ABC-12345", "https://example.com/?a=1&b=%20", "テスト用文字列 日本語", " !@#$%^&*()_+-=[]{};:,.<>/? ", "https://example.com/" + "abcdef" * 150])
def test_qr_roundtrip(text):
    item = generate_qr(text)
    width = len(item.matrix)
    image = Image.new("L", (width, width), 255)
    image.putdata([0 if cell else 255 for row in item.matrix for cell in row])
    decoded = zxingcpp.read_barcode(image.resize((width * 8, width * 8), Image.Resampling.NEAREST))
    assert decoded is not None
    assert decoded.bytes == text.encode("utf-8")
    assert item.text == text
    assert all(not cell for row in item.matrix[:4] for cell in row)


def test_parse_preserves_content():
    assert parse_lines("\r\n  ABC  \n \n日本語\rhttps://example.com/\n") == ["  ABC  ", "日本語", "https://example.com/"]


@pytest.mark.parametrize("text", ["", " ", "あ" * 2000, "a\x00b"])
def test_bad_input(text):
    with pytest.raises(UserError):
        generate_qr(text)

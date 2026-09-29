"""Lossless input parsing and QR encoding, independent of Qt."""
from dataclasses import dataclass
import qrcode
from qrcode.exceptions import DataOverflowError


class UserError(ValueError):
    """An actionable message suitable for the Japanese UI."""


def parse_lines(text: str) -> list[str]:
    # Only line separators are removed; spaces within valid lines are preserved.
    return [line for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]


@dataclass(frozen=True)
class QRItem:
    text: str
    matrix: tuple[tuple[bool, ...], ...]


def generate_qr(text: str) -> QRItem:
    if not text.strip():
        raise UserError("文字列を入力してください。")
    if any(ord(char) < 32 and char != "\t" for char in text):
        raise UserError("表示できない制御文字が含まれています。入力を確認してください。")
    if len(text.encode("utf-8")) > 2953:
        raise UserError("文字列が長すぎます。1件あたりの文字数を減らしてください。")
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    qr.add_data(text.encode("utf-8"), optimize=0)
    try:
        qr.make(fit=True)
    except DataOverflowError as exc:
        raise UserError("QRコードの容量を超えています。文字列を短くしてください。") from exc
    return QRItem(text, tuple(tuple(row) for row in qr.get_matrix()))

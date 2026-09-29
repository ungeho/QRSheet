import logging
import os
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from qrsheet.qr.generator import UserError


def japanese_font():
    name = "QRSheetJapanese"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = [fonts / "msgothic.ttc", fonts / "meiryo.ttc", fonts / "YuGothM.ttc"]
    override = os.environ.get("QRSHEET_FONT")
    if override:
        candidates.insert(0, Path(override))
    for path in candidates:
        if path.is_file():
            try:
                pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=0))
                return name
            except Exception:
                logging.getLogger(__name__).warning("Font registration failed: %s", path, exc_info=True)
    raise UserError("日本語フォントが見つかりません。Windowsの日本語追加フォントを導入するか、QRSHEET_FONTに日本語TrueTypeフォントを指定してください。")

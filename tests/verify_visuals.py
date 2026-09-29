"""Manual QA helper: generate samples, render using Qt PDF, decode printed QR."""
from pathlib import Path
import time
from PIL import Image
import zxingcpp
from PySide6.QtCore import QSize, QSettings
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication
from qrsheet.pdf.generator import generate_pdf
from qrsheet.settings.manager import PdfSettings, SettingsManager
from qrsheet.ui.main_window import MainWindow


def main():
    app = QApplication.instance() or QApplication([])
    output = Path("output/pdf")
    output.mkdir(parents=True, exist_ok=True)
    samples = ["https://example.com/", "ABC-12345", "テスト用文字列", "日本語・英数字 ABC 123", " !@#$% & (test) ", "https://example.com/search?q=QRSheet&lang=ja"]
    generate_pdf(samples, output / "QRSheet_sample.pdf", PdfSettings(columns=2))
    long_url = "https://example.com/" + "abcdef?x=1&y=2/" * 85
    generate_pdf([long_url, "長いURLの折り返し確認"], output / "QRSheet_long.pdf", PdfSettings(qr_mm=60, columns=2))
    generate_pdf([f"日本語の項目 {i:03d}" for i in range(100)], output / "QRSheet_100.pdf", PdfSettings(columns=4))
    for name in ["QRSheet_sample", "QRSheet_long", "QRSheet_100"]:
        document = QPdfDocument()
        document.load(str(output / f"{name}.pdf"))
        for page in range(document.pageCount()):
            size = document.pagePointSize(page)
            image = document.render(page, QSize(int(size.width() * 3), int(size.height() * 3)))
            image.save(str(output / f"{name}_{page + 1}.png"))
            image_path = output / f"{name}_{page + 1}.png"
            with Image.open(image_path) as rendered:
                foreground = rendered.convert("RGBA")
                background = Image.new("RGBA", foreground.size, "white")
                background.alpha_composite(foreground)
                background.convert("RGB").save(image_path)
        print(f"{name}: {document.pageCount()} pages")
        document.close()
    decoded = zxingcpp.read_barcodes(Image.open(output / "QRSheet_sample_1.png"))
    assert {code.bytes for code in decoded} == {text.encode("utf-8") for text in samples}
    print("PDF rendered QR decode: all 6 match original UTF-8 bytes")
    window = MainWindow(SettingsManager(QSettings(str(output.resolve() / "qa-settings.ini"), QSettings.Format.IniFormat)))
    window.editor.setPlainText("\n".join(samples))
    window.columns.setCurrentIndex(2)
    window.show()
    window.start_generation(True)
    deadline = time.monotonic() + 30
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    for _ in range(30):
        app.processEvents()
        time.sleep(0.02)
    window.grab().save("assets/screenshot.png")
    window.close()


if __name__ == "__main__":
    main()

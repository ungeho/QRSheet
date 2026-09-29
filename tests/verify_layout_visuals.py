"""Generate and render layout samples, then decode every printed QR."""
from dataclasses import replace
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QTabWidget
import zxingcpp

from qrsheet.pdf.generator import generate_pdf
from qrsheet.settings.manager import PdfSettings, SettingsManager
from qrsheet.ui.main_window import MainWindow


def main():
    output = Path("output/pdf/layout")
    output.mkdir(parents=True, exist_ok=True)
    base = PdfSettings(columns=2)
    cases = {
        "left-top": base,
        "center-top": replace(base, horizontal_align="center"),
        "right-top": replace(base, horizontal_align="right"),
        "gap-x-0": replace(base, horizontal_gap_mm=0),
        "gap-x-5": base,
        "gap-y-0": replace(base, vertical_gap_mm=0),
        "gap-y-5": base,
        "columns-1": replace(base, columns=1),
        "columns-3": replace(base, columns=3),
        "center-center": replace(base, horizontal_align="center", vertical_align="center"),
        "right-bottom": replace(base, horizontal_align="right", vertical_align="bottom"),
        "justify": replace(base, horizontal_align="justify", vertical_align="justify"),
        "multiple-pages": replace(base, columns=3),
        "letter-landscape": replace(base, paper="Letter", landscape=True, margin_left_mm=10, margin_right_mm=25),
        "zero-margins": replace(base, margin_top_mm=0, margin_bottom_mm=0, margin_left_mm=0, margin_right_mm=0, show_title=False, show_date=False),
    }
    thumbnails = []
    for name, settings in cases.items():
        count = 31 if name == "multiple-pages" else 5
        texts = [f"日本語の項目{i:03d}" for i in range(count)]
        path = output / f"{name}.pdf"
        pages = generate_pdf(texts, path, settings)
        subprocess.run(["pdftoppm", "-r", "120", "-png", str(path), str(output / name)], check=True, capture_output=True)
        decoded = []
        for png in sorted(output.glob(f"{name}-[0-9]*.png")):
            with Image.open(png) as image:
                decoded.extend(code.bytes for code in zxingcpp.read_barcodes(image))
                image.thumbnail((290, 380))
                thumb = Image.new("RGB", (310, 410), "#e4e8ed")
                thumb.paste(image, ((310 - image.width) // 2, 25))
                ImageDraw.Draw(thumb).text((10, 7), png.stem, fill="black")
                thumbnails.append(thumb)
        assert sorted(decoded) == sorted(text.encode("utf-8") for text in texts), name
        print(f"{name}: {pages} pages, {len(decoded)} QR codes decoded")
    sheet = Image.new("RGB", (310 * 4, 410 * ((len(thumbnails) + 3) // 4)), "white")
    for index, thumb in enumerate(thumbnails):
        sheet.paste(thumb, ((index % 4) * 310, (index // 4) * 410))
    sheet.save(output / "contact-sheet.png")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(SettingsManager(QSettings(str(output.resolve() / "gui.ini"), QSettings.Format.IniFormat)))
    window.findChild(QTabWidget).setCurrentIndex(1)
    window.show()
    app.processEvents()
    window.grab().save(str(output / "layout-ui.png"))
    window.resize(800, 620)
    app.processEvents()
    window.grab().save(str(output / "layout-ui-small.png"))
    window.close()


if __name__ == "__main__":
    main()

import time
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from qrsheet.settings.manager import SettingsManager, PdfSettings
from qrsheet.ui.main_window import MainWindow


def test_settings_roundtrip(tmp_path):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = SettingsManager(store)
    value = PdfSettings(paper="Letter", columns=2, landscape=True, show_date=False)
    manager.save(value)
    assert SettingsManager(store).load() == value
    assert set(store.allKeys()) == {"title", "show_title", "show_date", "paper", "landscape", "qr_mm", "columns"}
    store.setValue("columns", 99)
    assert manager.load() == PdfSettings()


def test_gui_preview_worker(tmp_path):
    app = QApplication.instance() or QApplication([])
    manager = SettingsManager(QSettings(str(tmp_path / "gui.ini"), QSettings.Format.IniFormat))
    window = MainWindow(manager)
    window.show()
    window.editor.setPlainText("https://example.com/\n\n日本語\n  ABC  ")
    assert window.count.text() == "3件"
    window.start_generation(True)
    deadline = time.monotonic() + 30
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.worker is None
    assert window.document.pageCount() == 1
    assert window.generate_button.isEnabled()
    window.editor.setPlainText("更新された日本語")
    window.start_generation(True)
    deadline = time.monotonic() + 30
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.worker is None
    assert "更新された日本語" in window.document.getAllText(0).text()
    window.close()

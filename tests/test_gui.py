import time
from dataclasses import asdict
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from qrsheet.settings.manager import SettingsManager, PdfSettings
from qrsheet.ui.main_window import MainWindow
from qrsheet.ui.main_window import PdfWorker
from PySide6.QtWidgets import QFileDialog
from pypdf import PdfReader


def test_settings_roundtrip(tmp_path):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = SettingsManager(store)
    value = PdfSettings(paper="Letter", columns=2, landscape=True, show_date=False)
    manager.save(value)
    assert SettingsManager(store).load() == value
    assert set(store.allKeys()) == set(asdict(PdfSettings()))
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


def test_output_directory_default_change_and_reset(tmp_path, monkeypatch):
    default = tmp_path / "Documents" / "QRSheet"
    monkeypatch.setattr(SettingsManager, "default_output_directory", staticmethod(lambda: default))
    store = QSettings(str(tmp_path / "output.ini"), QSettings.Format.IniFormat)
    app = QApplication.instance() or QApplication([])
    manager = SettingsManager(store)
    window = MainWindow(manager)
    assert window.output_path.text() == str(default)
    custom = tmp_path / "日本語の保存先"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(custom))
    window.choose_output_directory()
    assert SettingsManager(store).output_directory() == custom
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: "")
    window.choose_output_directory()
    assert manager.output_directory() == custom
    window.reset_output_directory()
    assert manager.output_directory() == default
    assert not default.exists()
    window.close()


def test_automatic_save_preserves_existing_and_cleans_failed_output(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "new-folder" / "QRSheet.pdf"
    first = PdfWorker(["最初のPDF"], path, PdfSettings(), automatic=True)
    first.run()
    original = path.read_bytes()
    second = PdfWorker(["次のPDF"], path, PdfSettings(), automatic=True)
    second.run()
    assert path.read_bytes() == original
    assert "次のPDF" in PdfReader(path.with_stem("QRSheet_001")).pages[0].extract_text()
    failed = PdfWorker(["x" * 4000], path, PdfSettings(), automatic=True)
    failed.run()
    assert not path.with_stem("QRSheet_002").exists()


def test_gui_saves_without_dialog(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    manager = SettingsManager(QSettings(str(tmp_path / "save.ini"), QSettings.Format.IniFormat))
    manager.set_output_directory(tmp_path / "PDF")
    window = MainWindow(manager)
    window.editor.setPlainText("保存テスト")
    def unexpected_dialog(*args):
        raise AssertionError("Automatic generation must not ask for a filename")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", unexpected_dialog)
    window.start_generation()
    deadline = time.monotonic() + 30
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.worker is None
    assert window.last_pdf.parent == manager.output_directory()
    assert "保存テスト" in PdfReader(window.last_pdf).pages[0].extract_text()
    assert window.open_folder.isEnabled()
    window.close()


def test_layout_settings_restore_and_reset(tmp_path):
    app = QApplication.instance() or QApplication([])
    manager = SettingsManager(QSettings(str(tmp_path / "layout.ini"), QSettings.Format.IniFormat))
    custom = PdfSettings(horizontal_align="right", vertical_align="bottom", horizontal_gap_mm=0,
                         vertical_gap_mm=12, margin_top_mm=20, margin_bottom_mm=7,
                         margin_left_mm=8, margin_right_mm=9)
    manager.save(custom)
    window = MainWindow(manager)
    assert window.current_settings() == custom
    window.layout_controls["horizontal_align"].setCurrentIndex(1)
    window.layout_controls["vertical_gap_mm"].setValue(0)
    changed = window.current_settings()
    window.close()
    restored = MainWindow(manager)
    assert restored.current_settings() == changed
    restored.editor.setPlainText("入力を保持")
    restored.reset_pdf_settings_button.click()
    assert restored.current_settings() == PdfSettings()
    assert manager.load() == PdfSettings()
    assert restored.editor.toPlainText() == "入力を保持"
    assert "プレビューを更新" in restored.preview_note.text()
    restored.close()


def wait_for_preview(app, window):
    deadline = time.monotonic() + 10
    while (window.preview_timer.isActive() or window.worker is not None or window.preview_pending) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.worker is None
    assert not window.preview_pending
    assert not window.preview_timer.isActive()


def test_auto_preview_debounce_and_latest_settings(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    manager = SettingsManager(QSettings(str(tmp_path / "auto.ini"), QSettings.Format.IniFormat))
    manager.set_output_directory(tmp_path / "saved")
    window = MainWindow(manager)
    starts = []
    original = PdfWorker.start
    def record(worker):
        starts.append((worker.texts, worker.settings))
        original(worker)
    monkeypatch.setattr(PdfWorker, "start", record)
    window.editor.setPlainText("初めの入力")
    window.title.setText("更新タイトル")
    window.layout_controls["horizontal_align"].setCurrentIndex(2)
    window.layout_controls["horizontal_gap_mm"].setValue(0)
    assert not starts
    wait_for_preview(app, window)
    assert len(starts) == 1
    assert starts[0][1].horizontal_align == "right"
    assert starts[0][1].horizontal_gap_mm == 0
    assert "更新タイトル" in window.document.getAllText(0).text()
    assert not (tmp_path / "saved").exists()
    window.editor.setPlainText("古い入力")
    window.start_generation(True)
    window.editor.setPlainText("最新の入力")
    window.orientation.setCurrentIndex(1)
    # Fire while busy: the queued update must survive until the worker finishes.
    window.preview_timer.stop()
    window.update_preview_automatically()
    assert window.preview_pending
    wait_for_preview(app, window)
    assert len(starts) == 3
    assert "最新の入力" in window.document.getAllText(0).text()
    assert "古い入力" not in window.document.getAllText(0).text()
    size = window.document.pagePointSize(0)
    assert size.width() > size.height()
    window.close()


def test_auto_preview_clear_errors_and_recovery(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    app = QApplication.instance() or QApplication([])
    window = MainWindow(SettingsManager(QSettings(str(tmp_path / "errors.ini"), QSettings.Format.IniFormat)))
    def unexpected(*args):
        raise AssertionError("Automatic preview must not open a modal dialog")
    monkeypatch.setattr(QMessageBox, "warning", unexpected)
    monkeypatch.setattr(QMessageBox, "information", unexpected)
    window.editor.setPlainText("入力")
    window.columns.setCurrentIndex(4)
    window.qr_size.setValue(60)
    wait_for_preview(app, window)
    assert "プレビューを更新できません" in window.preview_note.text()
    window.qr_size.setValue(35)
    wait_for_preview(app, window)
    assert window.document.pageCount() == 1
    window.start_generation(True)
    window.editor.clear()
    wait_for_preview(app, window)
    assert window.document.pageCount() == 0
    assert not window.preview_pending
    window.editor.setPlainText("終了前の入力")
    assert window.preview_timer.isActive()
    window.close()
    assert not window.preview_timer.isActive()


def test_auto_preview_after_save(tmp_path):
    app = QApplication.instance() or QApplication([])
    manager = SettingsManager(QSettings(str(tmp_path / "save-auto.ini"), QSettings.Format.IniFormat))
    manager.set_output_directory(tmp_path / "saved")
    window = MainWindow(manager)
    window.editor.setPlainText("保存内容")
    window.start_generation()
    window.editor.setPlainText("プレビュー用の変更")
    wait_for_preview(app, window)
    assert "保存内容" in PdfReader(window.last_pdf).pages[0].extract_text()
    assert "プレビュー用の変更" in window.document.getAllText(0).text().replace("\r", "").replace("\n", "")
    assert len(list((tmp_path / "saved").glob("*.pdf"))) == 1
    window.close()

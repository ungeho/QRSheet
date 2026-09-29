import logging
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QThread, Signal, QUrl, QBuffer, QIODevice, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget, QTabWidget, QScrollArea, QSizePolicy,
)
from qrsheet.pdf.generator import generate_pdf
from qrsheet.qr.generator import parse_lines, UserError
from qrsheet.settings.manager import PdfSettings, SettingsManager

logger = logging.getLogger(__name__)


class PdfWorker(QThread):
    progress = Signal(int, int)
    succeeded = Signal(str, int)
    failed = Signal(str)

    def __init__(self, texts, path, settings, parent=None, automatic=False):
        super().__init__(parent)
        self.texts, self.path, self.settings = texts, path, settings
        self.automatic = automatic

    def run(self):
        reserved = None
        try:
            if self.automatic:
                base = Path(self.path)
                base.parent.mkdir(parents=True, exist_ok=True)
                number = 0
                while True:
                    candidate = base if number == 0 else base.with_stem(f"{base.stem}_{number:03d}")
                    try:
                        with candidate.open("xb"):
                            pass
                        reserved = candidate
                        self.path = candidate
                        break
                    except FileExistsError:
                        number += 1
            pages = generate_pdf(self.texts, self.path, self.settings, self.progress.emit)
            reserved = None
            self.succeeded.emit(str(self.path), pages)
        except UserError as exc:
            self.failed.emit(str(exc))
        except OSError:
            logger.exception("PDF write failed")
            self.failed.emit("保存先に書き込めません。フォルダーの権限や、PDFが他のアプリで開かれていないか確認してください。")
        except Exception:
            logger.exception("PDF generation failed")
            self.failed.emit("PDFを生成できませんでした。設定と入力を確認して、もう一度お試しください。")
        finally:
            if reserved is not None:
                try:
                    reserved.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove reserved output file", exc_info=True)


class MainWindow(QMainWindow):
    def __init__(self, manager=None):
        super().__init__()
        self.manager = manager or SettingsManager()
        self.worker = None
        self.last_pdf = None
        self.preview_revision = 0
        self.preview_pending = False
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(500)
        self.preview_timer.timeout.connect(self.update_preview_automatically)
        self.preview_directory = TemporaryDirectory(prefix="QRSheet-preview-")
        self.setWindowTitle("QRSheet")
        self.resize(1160, 800)
        self.setMinimumSize(800, 620)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        heading = QLabel("QRSheet")
        heading.setStyleSheet("font-size: 25px; font-weight: 600;")
        layout.addWidget(heading)
        layout.addWidget(QLabel("文字列をまとめて、読み取りやすいQRコードのPDFに。"))
        split = QSplitter()
        layout.addWidget(split, 1)
        editor_panel = QWidget()
        left = QVBoxLayout(editor_panel)
        left.setContentsMargins(0, 12, 12, 0)
        input_header = QHBoxLayout()
        input_header.addWidget(QLabel("1行につき1つのQRコードを生成します"))
        input_header.addStretch()
        self.count = QLabel("0件")
        input_header.addWidget(self.count)
        left.addLayout(input_header)
        self.editor = QPlainTextEdit()
        self.editor.setMinimumHeight(72)
        self.editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.editor.setPlaceholderText("https://example.com/\nABC-12345\nテスト用文字列")
        self.editor.textChanged.connect(self.update_count)
        left.addWidget(self.editor, 1)
        helpers = QHBoxLayout()
        for text, action in [("入力をクリア", self.editor.clear), ("貼り付け", self.editor.paste), (".txtを読み込む", self.import_text)]:
            button = QPushButton(text)
            button.clicked.connect(action)
            helpers.addWidget(button)
        left.addLayout(helpers)
        group = QGroupBox("PDF設定")
        group_layout = QVBoxLayout(group)
        tabs = QTabWidget()
        group_layout.addWidget(tabs)
        basic = QWidget()
        tabs.addTab(basic, "基本")
        form = QFormLayout(basic)
        self.title = QLineEdit()
        self.title.setMaxLength(120)
        form.addRow("タイトル", self.title)
        flags = QHBoxLayout()
        self.show_title = QCheckBox("タイトルを表示")
        self.show_date = QCheckBox("生成日を表示")
        flags.addWidget(self.show_title)
        flags.addWidget(self.show_date)
        form.addRow("表示", flags)
        self.paper = QComboBox()
        self.paper.addItems(["A4", "Letter"])
        form.addRow("用紙サイズ", self.paper)
        self.orientation = QComboBox()
        self.orientation.addItems(["縦", "横"])
        form.addRow("用紙方向", self.orientation)
        self.qr_size = QSpinBox()
        self.qr_size.setRange(20, 60)
        self.qr_size.setSuffix(" mm")
        form.addRow("QRコードサイズ", self.qr_size)
        self.columns = QComboBox()
        self.columns.addItems(["自動", "1列", "2列", "3列", "4列"])
        form.addRow("カラム数", self.columns)
        self.reset_pdf_settings_button = QPushButton("初期値に戻す")
        self.reset_pdf_settings_button.clicked.connect(self.reset_pdf_settings)
        layout_panel = QWidget()
        tabs.addTab(layout_panel, "レイアウト")
        placement = QFormLayout(layout_panel)
        self.layout_controls = {}
        for key, label, options in [
            ("horizontal_align", "横方向の配置", [("左詰め", "left"), ("中央", "center"), ("右詰め", "right"), ("均等配置", "justify")]),
            ("vertical_align", "縦方向の配置", [("上詰め", "top"), ("中央", "center"), ("下詰め", "bottom"), ("均等配置", "justify")]),
        ]:
            control = QComboBox()
            for text, value in options:
                control.addItem(text, value)
            self.layout_controls[key] = control
            placement.addRow(label, control)
        for label, fields in [
            ("カード間隔", [("horizontal_gap_mm", "横"), ("vertical_gap_mm", "縦")]),
            ("上下余白", [("margin_top_mm", "上"), ("margin_bottom_mm", "下")]),
            ("左右余白", [("margin_left_mm", "左"), ("margin_right_mm", "右")]),
        ]:
            row = QHBoxLayout()
            for key, caption in fields:
                control = QSpinBox()
                control.setRange(0, 100)
                control.setSuffix(" mm")
                control.setAccessibleName(label + caption)
                self.layout_controls[key] = control
                row.addWidget(QLabel(caption))
                row.addWidget(control)
            placement.addRow(label, row)
        note = QLabel("均等配置は指定間隔を最小にして余りを分配します。\nカード幅はQRサイズ＋4mm。入りきらない列数はエラーになります。")
        note.setWordWrap(True)
        note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        placement.addRow(note)
        group_layout.addWidget(self.reset_pdf_settings_button)
        left.addWidget(group)
        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        editor_scroll.setWidget(editor_panel)
        split.addWidget(editor_scroll)
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(QLabel("PDFプレビュー"))
        self.preview_note = QLabel("入力や設定を変更すると、プレビューが自動更新されます。")
        self.preview_note.setWordWrap(True)
        preview_layout.addWidget(self.preview_note)
        self.document = QPdfDocument(self)
        self.preview_buffer = QBuffer(self)
        self.preview = QPdfView()
        self.preview.setDocument(self.document)
        self.preview.setPageMode(QPdfView.PageMode.MultiPage)
        self.preview.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        preview_layout.addWidget(self.preview, 1)
        split.addWidget(preview_panel)
        split.setSizes([530, 580])
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.status = QLabel("文字列を入力して、PDFを生成してください。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        destination = QHBoxLayout()
        destination.addWidget(QLabel("PDF保存先"))
        self.output_path = QLineEdit(str(self.manager.output_directory()))
        self.output_path.setReadOnly(True)
        self.output_path.setToolTip(self.output_path.text())
        destination.addWidget(self.output_path, 1)
        self.change_folder = QPushButton("変更…")
        self.change_folder.clicked.connect(self.choose_output_directory)
        destination.addWidget(self.change_folder)
        self.reset_folder = QPushButton("既定に戻す")
        self.reset_folder.clicked.connect(self.reset_output_directory)
        destination.addWidget(self.reset_folder)
        layout.addLayout(destination)
        actions = QHBoxLayout()
        self.open_pdf = QPushButton("PDFを開く")
        self.open_folder = QPushButton("保存先フォルダーを開く")
        self.open_pdf.setEnabled(False)
        self.open_folder.setEnabled(False)
        self.open_pdf.clicked.connect(lambda: self.open_path(self.last_pdf))
        self.open_folder.clicked.connect(lambda: self.open_path(self.last_pdf.parent))
        actions.addWidget(self.open_pdf)
        actions.addWidget(self.open_folder)
        actions.addStretch()
        self.save_as_button = QPushButton("名前を付けて保存…")
        self.save_as_button.clicked.connect(lambda: self.start_generation(False, True))
        actions.addWidget(self.save_as_button)
        self.preview_button = QPushButton("プレビューを更新")
        self.preview_button.clicked.connect(lambda: self.start_generation(True))
        actions.addWidget(self.preview_button)
        self.generate_button = QPushButton("PDFを生成")
        self.generate_button.setStyleSheet("QPushButton { background: #1769aa; color: white; font-weight: 600; padding: 8px 24px; } QPushButton:disabled { background: #8b99a5; }")
        self.generate_button.clicked.connect(lambda: self.start_generation(False))
        actions.addWidget(self.generate_button)
        layout.addLayout(actions)
        self.setCentralWidget(root)
        self.setStyleSheet("QPushButton { min-height: 26px; padding: 4px 10px; } QGroupBox { margin-top: 10px; padding-top: 16px; } QPlainTextEdit { padding: 8px; }")
        tabs.setMinimumHeight(tabs.sizeHint().height())
        group.setMinimumHeight(group.sizeHint().height())
        self.apply_pdf_settings(self.manager.load())
        for signal in [self.title.textChanged, self.show_title.toggled, self.show_date.toggled, self.paper.currentIndexChanged, self.orientation.currentIndexChanged, self.qr_size.valueChanged, self.columns.currentIndexChanged]:
            signal.connect(self.mark_stale)
        for control in self.layout_controls.values():
            signal = control.currentIndexChanged if isinstance(control, QComboBox) else control.valueChanged
            signal.connect(self.mark_stale)

    def apply_pdf_settings(self, settings):
        self.title.setText(settings.title)
        self.show_title.setChecked(settings.show_title)
        self.show_date.setChecked(settings.show_date)
        self.paper.setCurrentText(settings.paper)
        self.orientation.setCurrentIndex(int(settings.landscape))
        self.qr_size.setValue(settings.qr_mm)
        self.columns.setCurrentIndex(settings.columns)
        for key, control in self.layout_controls.items():
            value = getattr(settings, key)
            if isinstance(control, QComboBox):
                control.setCurrentIndex(control.findData(value))
            else:
                control.setValue(value)

    def reset_pdf_settings(self):
        settings = PdfSettings()
        self.apply_pdf_settings(settings)
        self.manager.save(settings)
        self.mark_stale()

    def mark_stale(self, *_):
        self.preview_revision += 1
        self.preview_timer.stop()
        self.preview_pending = bool(parse_lines(self.editor.toPlainText()))
        if not self.preview_pending:
            self.document.close()
            self.preview_buffer.close()
            self.preview_note.setText("文字列を入力すると、プレビューが自動更新されます。")
            return
        self.preview_note.setText("プレビューを更新待ちです…")
        self.preview_timer.start()

    def update_preview_automatically(self):
        if self.preview_pending and self.worker is None:
            self.start_generation(preview_only=True, auto_preview=True)

    def refresh_output_directory(self):
        self.output_path.setText(str(self.manager.output_directory()))
        self.output_path.setToolTip(self.output_path.text())

    def choose_output_directory(self):
        path = QFileDialog.getExistingDirectory(self, "PDFの保存先フォルダーを選択", self.output_path.text())
        if path:
            self.manager.set_output_directory(path)
            self.refresh_output_directory()

    def reset_output_directory(self):
        self.manager.set_output_directory()
        self.refresh_output_directory()

    def update_count(self):
        self.count.setText(f"{len(parse_lines(self.editor.toPlainText())):,}件")
        self.mark_stale()

    def current_settings(self):
        return PdfSettings(self.title.text(), self.show_title.isChecked(), self.show_date.isChecked(), self.paper.currentText(), bool(self.orientation.currentIndex()), self.qr_size.value(), self.columns.currentIndex(), **{key: control.currentData() if isinstance(control, QComboBox) else control.value() for key, control in self.layout_controls.items()})

    def import_text(self):
        path, _ = QFileDialog.getOpenFileName(self, "テキストファイルを読み込む", "", "テキストファイル (*.txt)")
        if not path:
            return
        try:
            if Path(path).stat().st_size > 10 * 1024 * 1024:
                raise UserError("テキストファイルは10MB以下にしてください。")
            text = Path(path).read_text(encoding="utf-8-sig")
            self.editor.setPlainText(text)
        except UnicodeError:
            QMessageBox.warning(self, "読み込みエラー", "UTF-8形式のテキストファイルを選択してください。")
        except (OSError, UserError) as exc:
            logger.warning("Text import failed", exc_info=True)
            QMessageBox.warning(self, "読み込みエラー", str(exc) if isinstance(exc, UserError) else "ファイルを読み込めません。アクセス権を確認してください。")

    def start_generation(self, preview_only=False, save_as=False, auto_preview=False):
        if self.worker is not None:
            return
        texts = parse_lines(self.editor.toPlainText())
        if not texts:
            if not auto_preview:
                QMessageBox.information(self, "入力を確認", "1件以上の文字列を入力してください。")
            return
        revision = self.preview_revision
        if preview_only:
            self.preview_timer.stop()
            self.preview_pending = False
        settings = self.current_settings()
        try:
            settings.validate()
        except UserError as exc:
            if auto_preview:
                self.preview_note.setText(f"プレビューを更新できません: {exc}")
            else:
                QMessageBox.warning(self, "設定を確認", str(exc))
            return
        if preview_only:
            path = str(Path(self.preview_directory.name) / "preview.pdf")
        elif save_as:
            self.preview_timer.stop()
            proposed = self.manager.output_directory() / f"QRSheet_{date.today().isoformat()}.pdf"
            path, _ = QFileDialog.getSaveFileName(self, "PDFを保存", str(proposed), "PDF (*.pdf)")
            if not path:
                if self.preview_pending:
                    self.preview_timer.start()
                return
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
                if Path(path).exists() and QMessageBox.question(self, "上書き確認", "同名のPDFがあります。上書きしますか？") != QMessageBox.StandardButton.Yes:
                    if self.preview_pending:
                        self.preview_timer.start()
                    return
        else:
            path = self.manager.output_directory() / f"QRSheet_{date.today().isoformat()}.pdf"
        self.preview_timer.stop()
        self.manager.save(settings)
        self.generate_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.save_as_button.setEnabled(False)
        self.change_folder.setEnabled(False)
        self.reset_folder.setEnabled(False)
        self.reset_pdf_settings_button.setEnabled(False)
        self.progress.setRange(0, len(texts))
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText("PDFを生成しています…")
        self.worker = PdfWorker(texts, path, settings, self, automatic=not preview_only and not save_as)
        self.worker.progress.connect(lambda done, total: self.progress.setValue(done))
        self.worker.succeeded.connect(lambda saved, pages: self.generation_done(saved, pages, preview_only, revision))
        self.worker.failed.connect(lambda message: self.generation_failed(message, auto_preview, revision))
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def generation_done(self, path, pages, preview_only, revision=None):
        if preview_only:
            if revision is not None and revision != self.preview_revision:
                return
            self.document.close()
            self.preview_buffer.close()
            self.preview_buffer.setData(Path(path).read_bytes())
            self.preview_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            self.document.load(self.preview_buffer)
            self.preview_note.setText(f"更新時点のプレビュー · {pages}ページ")
            self.status.setText("プレビューを更新しました。")
        else:
            self.last_pdf = Path(path)
            self.open_pdf.setEnabled(True)
            self.open_folder.setEnabled(True)
            self.status.setText(f"PDFを生成しました · {pages}ページ · {path}")

    def generation_failed(self, message, auto_preview=False, revision=None):
        if auto_preview:
            if revision == self.preview_revision:
                self.preview_note.setText(f"プレビューを更新できません: {message}")
                self.status.setText("入力・設定を変更すると、再び自動更新します。")
            return
        self.status.setText("生成できませんでした。入力・設定を確認してください。")
        QMessageBox.warning(self, "PDF生成エラー", message)

    def worker_finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        self.generate_button.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.save_as_button.setEnabled(True)
        self.change_folder.setEnabled(True)
        self.reset_folder.setEnabled(True)
        self.reset_pdf_settings_button.setEnabled(True)
        self.progress.hide()
        if self.preview_pending and not self.preview_timer.isActive():
            self.preview_timer.start()

    def open_path(self, path):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, "開けませんでした", "関連付けられたアプリを確認してください。")

    def closeEvent(self, event):
        if self.worker is not None:
            self.status.setText("生成が完了してからウィンドウを閉じてください。")
            event.ignore()
            return
        try:
            self.manager.save(self.current_settings())
        except UserError:
            logger.warning("Invalid settings were not saved on close")
        self.document.close()
        self.preview_buffer.close()
        self.preview_timer.stop()
        self.preview_pending = False
        self.preview_directory.cleanup()
        event.accept()

import logging
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QThread, Signal, QUrl, QBuffer, QIODevice
from PySide6.QtGui import QDesktopServices
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)
from qrsheet.pdf.generator import generate_pdf
from qrsheet.qr.generator import parse_lines, UserError
from qrsheet.settings.manager import PdfSettings, SettingsManager

logger = logging.getLogger(__name__)


class PdfWorker(QThread):
    progress = Signal(int, int)
    succeeded = Signal(str, int)
    failed = Signal(str)

    def __init__(self, texts, path, settings, parent=None):
        super().__init__(parent)
        self.texts, self.path, self.settings = texts, path, settings

    def run(self):
        try:
            pages = generate_pdf(self.texts, self.path, self.settings, self.progress.emit)
            self.succeeded.emit(str(self.path), pages)
        except UserError as exc:
            self.failed.emit(str(exc))
        except OSError:
            logger.exception("PDF write failed")
            self.failed.emit("保存先に書き込めません。フォルダーの権限や、PDFが他のアプリで開かれていないか確認してください。")
        except Exception:
            logger.exception("PDF generation failed")
            self.failed.emit("PDFを生成できませんでした。設定と入力を確認して、もう一度お試しください。")


class MainWindow(QMainWindow):
    def __init__(self, manager=None):
        super().__init__()
        self.manager = manager or SettingsManager()
        self.worker = None
        self.last_pdf = None
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
        form = QFormLayout(group)
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
        left.addWidget(group)
        split.addWidget(editor_panel)
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(QLabel("PDFプレビュー"))
        self.preview_note = QLabel("「プレビューを更新」で、現在の入力・設定を確認できます。")
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
        settings = self.manager.load()
        self.title.setText(settings.title)
        self.show_title.setChecked(settings.show_title)
        self.show_date.setChecked(settings.show_date)
        self.paper.setCurrentText(settings.paper)
        self.orientation.setCurrentIndex(int(settings.landscape))
        self.qr_size.setValue(settings.qr_mm)
        self.columns.setCurrentIndex(settings.columns)
        for signal in [self.title.textChanged, self.show_title.toggled, self.show_date.toggled, self.paper.currentIndexChanged, self.orientation.currentIndexChanged, self.qr_size.valueChanged, self.columns.currentIndexChanged]:
            signal.connect(self.mark_stale)

    def mark_stale(self, *_):
        self.preview_note.setText("現在の入力・設定を反映するには「プレビューを更新」を押してください。")

    def update_count(self):
        self.count.setText(f"{len(parse_lines(self.editor.toPlainText())):,}件")
        self.mark_stale()

    def current_settings(self):
        return PdfSettings(self.title.text(), self.show_title.isChecked(), self.show_date.isChecked(), self.paper.currentText(), bool(self.orientation.currentIndex()), self.qr_size.value(), self.columns.currentIndex())

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

    def start_generation(self, preview_only=False):
        if self.worker is not None:
            return
        texts = parse_lines(self.editor.toPlainText())
        if not texts:
            QMessageBox.information(self, "入力を確認", "1件以上の文字列を入力してください。")
            return
        settings = self.current_settings()
        try:
            settings.validate()
        except UserError as exc:
            QMessageBox.warning(self, "設定を確認", str(exc))
            return
        if preview_only:
            self.document.close()
            self.preview_buffer.close()
            path = str(Path(self.preview_directory.name) / "preview.pdf")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "PDFを保存", f"QRSheet_{date.today().isoformat()}.pdf", "PDF (*.pdf)")
            if not path:
                return
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
                if Path(path).exists() and QMessageBox.question(self, "上書き確認", "同名のPDFがあります。上書きしますか？") != QMessageBox.StandardButton.Yes:
                    return
        self.manager.save(settings)
        self.generate_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.progress.setRange(0, len(texts))
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText("PDFを生成しています…")
        self.worker = PdfWorker(texts, path, settings, self)
        self.worker.progress.connect(lambda done, total: self.progress.setValue(done))
        self.worker.succeeded.connect(lambda saved, pages: self.generation_done(saved, pages, preview_only))
        self.worker.failed.connect(self.generation_failed)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def generation_done(self, path, pages, preview_only):
        if preview_only:
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

    def generation_failed(self, message):
        self.status.setText("生成できませんでした。入力・設定を確認してください。")
        QMessageBox.warning(self, "PDF生成エラー", message)

    def worker_finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        self.generate_button.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.progress.hide()

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
        self.preview_directory.cleanup()
        event.accept()

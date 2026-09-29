from dataclasses import asdict, dataclass
from qrsheet.qr.generator import UserError


@dataclass(frozen=True)
class PdfSettings:
    title: str = "QRコード一覧"
    show_title: bool = True
    show_date: bool = True
    paper: str = "A4"
    landscape: bool = False
    qr_mm: int = 35
    columns: int = 0

    def validate(self):
        if not isinstance(self.title, str) or any(type(value) is not bool for value in (self.show_title, self.show_date, self.landscape)):
            raise UserError("タイトルまたは表示設定が無効です。設定を確認してください。")
        if self.paper not in ("A4", "Letter") or type(self.qr_mm) is not int or not 20 <= self.qr_mm <= 60 or type(self.columns) is not int or self.columns not in range(5):
            raise UserError("PDF設定が無効です。用紙・サイズ・列数を確認してください。")
        if len(self.title) > 120 or any(ord(c) < 32 for c in self.title):
            raise UserError("タイトルは改行なしの120文字以内で入力してください。")


class SettingsManager:
    def __init__(self, store=None):
        from PySide6.QtCore import QSettings
        self.store = store if store is not None else QSettings("QRSheet", "QRSheet")

    def load(self):
        defaults = PdfSettings()
        values = {}
        for key, default in asdict(defaults).items():
            try:
                values[key] = self.store.value(key, default, type=type(default))
            except (TypeError, ValueError):
                values[key] = default
        settings = PdfSettings(**values)
        try:
            settings.validate()
            return settings
        except UserError:
            return defaults

    def save(self, settings):
        settings.validate()
        for key, value in asdict(settings).items():
            self.store.setValue(key, value)
        self.store.sync()

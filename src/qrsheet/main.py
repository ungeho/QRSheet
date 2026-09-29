import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from PySide6.QtCore import QStandardPaths, QTimer
from PySide6.QtWidgets import QApplication
from qrsheet.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("QRSheet")
    app.setApplicationName("QRSheet")
    log_directory = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    try:
        log_directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_directory / "qrsheet.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s %(message)s")
    except OSError:
        logging.basicConfig(handlers=[logging.NullHandler()])
    window = MainWindow()
    window.show()
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(1500, window.close)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

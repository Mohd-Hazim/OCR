# main.py
import sys
from PySide6.QtWidgets import QApplication
from gui.popup import PopupWindow
from utils.config import logger, load_config

if __name__ == "__main__":
    logger.info("Starting OCR App (Tray mode)...")
    config = load_config()

    app = QApplication(sys.argv)
    window = PopupWindow()

    window.hide()
    logger.info("App launched silently to system tray.")
    sys.exit(app.exec())

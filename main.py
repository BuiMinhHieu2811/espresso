"""
Coffee Machine UART Controller
===============================
Entry point for the application.
"""

import sys
import os

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

from main_window import MainWindow


def resource_path(relative_path):
    """ Lấy đường dẫn tuyệt đối đến tài nguyên, hỗ trợ cả lúc dev và đóng gói .exe """
    try:
        # PyInstaller tạo thư mục tạm và lưu đường dẫn ở _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Nếu đang chạy file .py bình thường
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def load_stylesheet(app: QApplication):
    """Load the QSS stylesheet."""
    qss_path = resource_path("resources/style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Coffee Machine Controller")

    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Load stylesheet
    load_stylesheet(app)

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

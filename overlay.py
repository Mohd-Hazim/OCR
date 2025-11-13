# gui/overlay.py
import ctypes
import logging
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtCore import Qt, QRect, QPoint, QTimer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
def get_virtual_screen_geometry() -> QRect:
    """
    Return full virtual desktop geometry.
    Works across multi-monitor setups. Uses Windows system metrics if available,
    otherwise falls back to Qt screens union.
    """
    try:
        user32 = ctypes.windll.user32
        left = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        top = user32.GetSystemMetrics(77)    # SM_YVIRTUALSCREEN
        width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        height = user32.GetSystemMetrics(79) # SM_CYVIRTUALSCREEN
        return QRect(left, top, width, height)
    except Exception:
        # Fallback: union of all available screens via Qt
        from PySide6.QtGui import QGuiApplication
        rect = QRect()
        for screen in QGuiApplication.screens():
            rect = rect.united(screen.geometry())
        if rect.isNull():
            # As a last resort, use primary screen geometry
            primary = QGuiApplication.primaryScreen()
            if primary:
                return primary.geometry()
            return QRect(0, 0, 1920, 1080)
        return rect

# ---------------------------------------------------------
class SelectionOverlay(QWidget):
    """
    Transparent overlay for selecting a screen region.
    Emits selection rectangle to parent via parent_window.on_selection_made(rect).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.start_global = QPoint()
        self.end_global = QPoint()
        self.dragging = False

        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)


    # -----------------------------------------------------
    def showFullDesktop(self):
        """Show overlay covering all monitors."""
        virtual_rect = get_virtual_screen_geometry()
        self.setGeometry(virtual_rect)
        self.show()
        self.raise_()
        self.activateWindow()
        logger.info(f"Overlay covering full desktop: {virtual_rect}")

    # -----------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_global = event.globalPos()
            self.end_global = self.start_global
            self.dragging = True
            logger.debug(f"Selection started at: {self.start_global}")
            self.update()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.end_global = event.globalPos()
            self.update()

    def mouseReleaseEvent(self, event):
        if not self.dragging or event.button() != Qt.LeftButton:
            return

        self.dragging = False
        rect = QRect(self.start_global, self.end_global).normalized()
        logger.info(f"Selection complete: {rect}")
        self.hide()

        if self.parent_window:
            # Delay signal slightly to avoid race with hide()
            QTimer.singleShot(120, lambda r=rect: self.parent_window.on_selection_made(r))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            logger.info("Selection cancelled by user.")
            self.dragging = False
            self.hide()

    # -----------------------------------------------------
    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Dim the entire screen
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        # Draw selection rectangle if dragging
        if self.dragging:
            pen = QPen(QColor(0, 255, 0), 2)
            painter.setPen(pen)
            painter.setBrush(QColor(0, 255, 0, 40))
            top_left = self.mapFromGlobal(self.start_global)
            bottom_right = self.mapFromGlobal(self.end_global)
            selection_rect = QRect(top_left, bottom_right).normalized()
            painter.drawRect(selection_rect)

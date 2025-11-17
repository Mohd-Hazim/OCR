# gui/overlay.py - SIMPLIFIED VERSION (No Mode Selector)
"""
Clean overlay for screen selection only.
Mode is selected via main window dropdown before capture starts.
"""
import ctypes
import logging
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QGuiApplication
from PySide6.QtCore import Qt, QRect, QPoint, QTimer

logger = logging.getLogger(__name__)


def get_virtual_screen_geometry() -> QRect:
    """Return full virtual desktop geometry."""
    try:
        user32 = ctypes.windll.user32
        left = user32.GetSystemMetrics(76)
        top = user32.GetSystemMetrics(77)
        width = user32.GetSystemMetrics(78)
        height = user32.GetSystemMetrics(79)
        return QRect(left, top, width, height)
    except Exception:
        rect = QRect()
        for screen in QGuiApplication.screens():
            rect = rect.united(screen.geometry())
        if rect.isNull():
            primary = QGuiApplication.primaryScreen()
            if primary:
                return primary.geometry()
            return QRect(0, 0, 1920, 1080)
        return rect


class SelectionOverlay(QWidget):
    """
    Simplified overlay for screen region selection.
    No mode selector - mode is chosen in main window.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.start_global = QPoint()
        self.end_global = QPoint()
        self.dragging = False
        self.selected_mode = "text"  # Default (set by parent before showing)
        self.triggered_screen = None

        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)

    def showFullDesktop(self):
        """Show overlay covering all monitors."""
        # Detect which screen the mouse is currently on
        from PySide6.QtGui import QCursor
        cursor_pos = QCursor.pos()
        self.triggered_screen = QGuiApplication.screenAt(cursor_pos)
        
        if not self.triggered_screen:
            self.triggered_screen = QGuiApplication.primaryScreen()
        
        logger.info(f"Overlay triggered on screen: {self.triggered_screen.name()}")
        
        # Cover all screens
        virtual_rect = get_virtual_screen_geometry()
        self.setGeometry(virtual_rect)
        
        # Show overlay
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        
        logger.info(f"Overlay covering full desktop: {virtual_rect}")
        logger.info(f"Mode: {self.selected_mode}")

    def mousePressEvent(self, event):
        """Start selection."""
        if event.button() == Qt.LeftButton:
            self.start_global = event.globalPosition().toPoint()
            self.end_global = self.start_global
            self.dragging = True
            logger.debug(f"Selection started at: {self.start_global}")
            self.update()

    def mouseMoveEvent(self, event):
        """Update selection."""
        if self.dragging:
            self.end_global = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        """Complete selection."""
        if not self.dragging or event.button() != Qt.LeftButton:
            return

        self.dragging = False
        rect = QRect(self.start_global, self.end_global).normalized()
        
        # Minimum size check
        if rect.width() < 10 or rect.height() < 10:
            logger.info("Selection too small - ignored")
            self.update()
            return
        
        logger.info(f"Selection complete: {rect} | Mode: {self.selected_mode}")
        
        # Hide overlay
        self.hide()

        if self.parent_window:
            # Pass selection with slight delay
            QTimer.singleShot(120, lambda r=rect: self.parent_window.on_selection_made(r))

    def keyPressEvent(self, event):
        """Handle ESC to cancel."""
        if event.key() == Qt.Key_Escape:
            logger.info("🚫 ESC pressed - INSTANT CLOSE")
            
            # Stop everything immediately
            self.dragging = False
            self.setVisible(False)
            self.close()
            
            # Restore main window
            if self.parent_window:
                self.parent_window.setVisible(True)
                self.parent_window.show()
                self.parent_window.raise_()
                self.parent_window.activateWindow()
            
            event.accept()
            logger.info("✅ Overlay closed instantly")
            return
        
        super().keyPressEvent(event)

    def paintEvent(self, _):
        """Draw overlay with punched-out selection and dotted border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1️⃣ DIM ENTIRE SCREEN (global overlay)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

        if not self.dragging:
            return

        # Build selection rect
        top_left = self.mapFromGlobal(self.start_global)
        bottom_right = self.mapFromGlobal(self.end_global)
        rect = QRect(top_left, bottom_right).normalized()

        # 2️⃣ CLEAR INSIDE SELECTION (make that area NOT DIM)
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(rect, Qt.SolidPattern)

        # Restore normal drawing
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # 3️⃣ DOTTED BORDER (minimal visibility)
       # Ultra-thin dotted border
        pen = QPen(QColor(255, 255, 255, 160))   # softer white
        pen.setWidth(1)                          # thinner line
        pen.setStyle(Qt.DotLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

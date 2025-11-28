# gui/mode_selector.py - ENHANCED VERSION
"""
Floating mode selector that appears when overlay is shown.
Allows user to choose Text or Table mode before capturing.
"""
from PySide6.QtWidgets import QWidget, QPushButton, QLabel, QVBoxLayout, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, Signal, QTimer, QPoint
from PySide6.QtGui import QCursor, QColor
import logging

logger = logging.getLogger(__name__)


class ModeSelector(QWidget):
    """
    Floating mode selector popup.
    Appears at mouse cursor when overlay is shown.
    """
    mode_selected = Signal(str)  # Emits "text" or "table"
    cancelled = Signal()  # Emits when user cancels (ESC or clicks outside)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Window flags for floating behavior
        self.setWindowFlags(
            Qt.Tool |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.X11BypassWindowManagerHint  # Ensures it stays on top
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)  # DO activate
        
        # Fixed size
        self.setFixedSize(240, 160)
        
        # Get theme from parent or default to dark
        self.current_theme = "dark"
        if parent and hasattr(parent, "current_theme"):
            self.current_theme = parent.current_theme
        
        self._init_ui()
        self._apply_theme()
        
        # Auto-hide timer (optional - 10 seconds)
        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.timeout.connect(self._on_timeout)
        self.auto_hide_timer.setSingleShot(True)

    def _init_ui(self):
        """Build the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title
        self.title_label = QLabel("Choose Capture Mode")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 600;")

        # Text mode button
        self.btn_text = QPushButton("📝 Text")
        self.btn_text.setFixedHeight(40)
        self.btn_text.setCursor(Qt.PointingHandCursor)
        self.btn_text.clicked.connect(lambda: self._select("text"))

        # Table mode button
        self.btn_table = QPushButton("📊 Table")
        self.btn_table.setFixedHeight(40)
        self.btn_table.setCursor(Qt.PointingHandCursor)
        self.btn_table.clicked.connect(lambda: self._select("table"))

        # Cancel hint
        self.hint_label = QLabel("Press ESC to cancel")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setStyleSheet("font-size: 10px; opacity: 0.7;")

        # Add to layout
        layout.addWidget(self.title_label)
        layout.addWidget(self.btn_text)
        layout.addWidget(self.btn_table)
        layout.addStretch(1)
        layout.addWidget(self.hint_label)

        # Add drop shadow for depth
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

    def _apply_theme(self):
        """Apply theme-specific colors."""
        if self.current_theme == "dark":
            bg = "#1E293B"
            border = "#334155"
            text = "#E2E8F0"
            btn_bg = "#334155"
            btn_hover = "#3B82F6"
            btn_text = "#F1F5F9"
        else:
            bg = "#FFFFFF"
            border = "#E5E7EB"
            text = "#111827"
            btn_bg = "#F3F4F6"
            btn_hover = "#7C3AED"
            btn_text = "#1F2937"

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border: 2px solid {border};
                border-radius: 12px;
            }}
            QLabel {{
                color: {text};
                background: transparent;
                border: none;
            }}
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_text};
                border: 1px solid {border};
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
                color: white;
                border-color: {btn_hover};
            }}
            QPushButton:pressed {{
                background-color: {btn_hover};
                opacity: 0.8;
            }}
        """)

    def show_at_cursor(self):
        """Show the popup near the mouse cursor."""
        # Get cursor position
        cursor_pos = QCursor.pos()
        
        # Offset slightly to avoid cursor overlap
        offset_x = 20
        offset_y = 20
        
        # Calculate position
        x = cursor_pos.x() + offset_x
        y = cursor_pos.y() + offset_y
        
        # Ensure it stays on screen
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.screenAt(QPoint(x, y))
        if screen:
            screen_geo = screen.geometry()
            
            # Keep within screen bounds
            if x + self.width() > screen_geo.right():
                x = screen_geo.right() - self.width() - 10
            if y + self.height() > screen_geo.bottom():
                y = screen_geo.bottom() - self.height() - 10
            if x < screen_geo.left():
                x = screen_geo.left() + 10
            if y < screen_geo.top():
                y = screen_geo.top() + 10
        
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        
        # Start auto-hide timer (10 seconds)
        self.auto_hide_timer.start(10000)
        
        logger.info(f"Mode selector shown at ({x}, {y})")

    def _select(self, mode: str):
        """Handle mode selection."""
        logger.info(f"Mode selected: {mode}")
        self.auto_hide_timer.stop()
        self.hide()
        self.mode_selected.emit(mode)

    def _on_timeout(self):
        """Handle auto-hide timeout."""
        logger.info("Mode selector timed out - defaulting to text mode")
        self._select("text")

    def keyPressEvent(self, event):
        """Handle keyboard events."""
        if event.key() == Qt.Key_Escape:
            logger.info("Mode selection cancelled by user")
            self.auto_hide_timer.stop()
            self.hide()
            self.cancelled.emit()
            event.accept()
        elif event.key() == Qt.Key_1:
            # Shortcut: 1 for Text
            self._select("text")
            event.accept()
        elif event.key() == Qt.Key_2:
            # Shortcut: 2 for Table
            self._select("table")
            event.accept()
        else:
            super().keyPressEvent(event)

    def update_theme(self, theme: str):
        """Update theme when parent theme changes."""
        self.current_theme = theme
        self._apply_theme()
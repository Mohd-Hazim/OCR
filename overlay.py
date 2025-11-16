# gui/overlay.py - FIXED VERSION
"""
Overlay with centered mode selector dropdown (Windows Snipping Tool style).
FIXES:
- Instant ESC response (no delays)
- Mode selector appears on the screen where overlay was triggered
- Proper multi-monitor support
"""
import ctypes
import logging
from PySide6.QtWidgets import QWidget, QComboBox, QLabel, QHBoxLayout, QApplication
from PySide6.QtGui import QPainter, QColor, QPen, QGuiApplication, QCursor
from PySide6.QtCore import Qt, QRect, QPoint, QTimer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
def get_virtual_screen_geometry() -> QRect:
    """
    Return full virtual desktop geometry.
    Works across multi-monitor setups.
    """
    try:
        user32 = ctypes.windll.user32
        left = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        top = user32.GetSystemMetrics(77)    # SM_YVIRTUALSCREEN
        width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        height = user32.GetSystemMetrics(79) # SM_CYVIRTUALSCREEN
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


# ---------------------------------------------------------
class SelectionOverlay(QWidget):
    """
    Enhanced overlay with centered mode dropdown (Windows Snipping Tool style).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.start_global = QPoint()
        self.end_global = QPoint()
        self.dragging = False
        self.selected_mode = "text"  # Default mode
        self.triggered_screen = None  # Track which screen triggered the overlay

        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)
        
        self._init_mode_controls()

    def _init_mode_controls(self):
        """Create the mode selector dropdown bar at the top."""
        # Container widget for the top bar
        self.control_bar = QWidget(self)
        self.control_bar.setObjectName("controlBar")
        
        # Layout for controls
        layout = QHBoxLayout(self.control_bar)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # LEFT STRETCH - pushes content to center
        layout.addStretch(1)
        
        # Label
        self.mode_label = QLabel("Capture Mode:")
        self.mode_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            }
        """)
        
        # Dropdown
        self.mode_dropdown = QComboBox()
        self.mode_dropdown.addItems(["Text", "Table"])
        self.mode_dropdown.setCurrentText("Text")  # Default selection
        self.mode_dropdown.setFixedWidth(140)
        self.mode_dropdown.setFixedHeight(32)
        self.mode_dropdown.setCursor(Qt.PointingHandCursor)
        
        # Dropdown styling (Windows-like)
        self.mode_dropdown.setStyleSheet("""
            QComboBox {
                background-color: rgba(30, 30, 30, 200);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 500;
            }
            QComboBox:hover {
                background-color: rgba(50, 50, 50, 220);
                border-color: rgba(255, 255, 255, 0.5);
            }
            QComboBox:focus {
                border-color: #0078D4;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
                padding-right: 4px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid white;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: rgba(30, 30, 30, 240);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                selection-background-color: #0078D4;
                selection-color: white;
                padding: 4px;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 6px 12px;
                min-height: 28px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: rgba(0, 120, 212, 0.8);
            }
        """)
        
        # Instruction label
        self.instruction_label = QLabel("Click and drag to select region • Press ESC to cancel")
        self.instruction_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.9);
                font-size: 11px;
                background: transparent;
            }
        """)
        
        # Connect signal
        self.mode_dropdown.currentTextChanged.connect(self._on_mode_changed)
        
        # Add to layout (CENTERED GROUP)
        layout.addWidget(self.mode_label)
        layout.addWidget(self.mode_dropdown)
        layout.addSpacing(20)
        layout.addWidget(self.instruction_label)
        
        # RIGHT STRETCH - balances left stretch to center everything
        layout.addStretch(1)
        
        # Style the control bar
        self.control_bar.setStyleSheet("""
            QWidget#controlBar {
                background-color: rgba(20, 20, 20, 200);
                border-bottom: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 0px;
            }
        """)
        
        # Initially hidden
        self.control_bar.hide()

    def _on_mode_changed(self, mode_text):
        """Handle mode selection change."""
        self.selected_mode = "text" if mode_text == "Text" else "table"
        logger.info(f"Overlay mode changed to: {self.selected_mode}")
        
        # Update parent window's mode if available
        if self.parent_window and hasattr(self.parent_window, 'selected_content_mode'):
            self.parent_window.selected_content_mode = self.selected_mode

    def _position_control_bar(self):
        """
        ✅ FIXED: Place control bar on the screen where overlay was triggered.
        Handles negative coordinates in multi-monitor setups.
        """
        bar_width = 700
        bar_height = 56

        # ✅ Get the screen where overlay was triggered
        if self.triggered_screen:
            target_screen = self.triggered_screen
        else:
            # Fallback: use primary screen
            target_screen = QGuiApplication.primaryScreen()
        
        if target_screen:
            screen_geo = target_screen.geometry()
            
            # ✅ CRITICAL FIX: Convert screen coordinates to overlay local coordinates
            # The overlay covers the entire virtual desktop starting at (0,0) in its own coordinate system
            # But screens can have negative global coordinates (like -1080 for monitor above primary)
            
            # Get virtual desktop geometry
            virtual_rect = get_virtual_screen_geometry()
            
            # Calculate offset between virtual desktop origin and overlay origin
            # Overlay always starts at (0,0) in its own coordinates
            # Virtual desktop might start at negative coordinates
            offset_x = -virtual_rect.x()
            offset_y = -virtual_rect.y()
            
            # Convert screen position to overlay-local coordinates
            screen_x_local = screen_geo.x() + offset_x
            screen_y_local = screen_geo.y() + offset_y
            
            # Center horizontally on target screen
            screen_center_x = screen_x_local + (screen_geo.width() // 2)
            x = screen_center_x - (bar_width // 2)
            
            # Position near top of target screen
            y = screen_y_local + 40
            
            logger.info(f"Control bar positioning:")
            logger.info(f"  Screen: {target_screen.name()}")
            logger.info(f"  Screen global: ({screen_geo.x()}, {screen_geo.y()})")
            logger.info(f"  Virtual offset: ({offset_x}, {offset_y})")
            logger.info(f"  Overlay local: ({screen_x_local}, {screen_y_local})")
            logger.info(f"  Control bar at: ({x}, {y})")
        else:
            # Fallback: center on overlay
            x = (self.width() - bar_width) // 2
            y = 40
            logger.warning("Target screen not detected, using fallback positioning")

        self.control_bar.setGeometry(x, y, bar_width, bar_height)

    # -----------------------------------------------------
    def showFullDesktop(self):
        """Show overlay covering all monitors with mode selector."""
        # ✅ Detect which screen the mouse is currently on
        from PySide6.QtGui import QCursor
        cursor_pos = QCursor.pos()
        self.triggered_screen = QGuiApplication.screenAt(cursor_pos)
        
        if not self.triggered_screen:
            self.triggered_screen = QGuiApplication.primaryScreen()
        
        logger.info(f"Overlay triggered on screen: {self.triggered_screen.name()}")
        
        # Cover all screens
        virtual_rect = get_virtual_screen_geometry()
        self.setGeometry(virtual_rect)
        
        # Show and position control bar on triggered screen
        self.control_bar.show()
        self._position_control_bar()
        
        # Show overlay
        self.show()
        self.raise_()
        self.activateWindow()
        
        # Set focus to allow keyboard input
        self.setFocus()
        
        logger.info(f"Overlay covering full desktop: {virtual_rect}")
        logger.info(f"Default mode: {self.selected_mode}")

    # -----------------------------------------------------
    def mousePressEvent(self, event):
        """Handle mouse press - start selection."""
        if event.button() == Qt.LeftButton:
            # Check if click is on control bar
            if self.control_bar.geometry().contains(event.pos()):
                # Let the control bar handle it
                event.ignore()
                return
            
            self.start_global = event.globalPosition().toPoint()
            self.end_global = self.start_global
            self.dragging = True
            logger.debug(f"Selection started at: {self.start_global}")
            self.update()

    def mouseMoveEvent(self, event):
        """Handle mouse move - update selection."""
        if self.dragging:
            self.end_global = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release - complete selection."""
        if not self.dragging or event.button() != Qt.LeftButton:
            return

        self.dragging = False
        rect = QRect(self.start_global, self.end_global).normalized()
        
        # Minimum size check (avoid accidental clicks)
        if rect.width() < 10 or rect.height() < 10:
            logger.info("Selection too small - ignored")
            self.update()
            return
        
        logger.info(f"Selection complete: {rect} | Mode: {self.selected_mode}")
        
        # Hide control bar and overlay
        self.control_bar.hide()
        self.hide()

        if self.parent_window:
            # Pass selection with slight delay to avoid race condition
            QTimer.singleShot(120, lambda r=rect: self.parent_window.on_selection_made(r))

    def keyPressEvent(self, event):
        """
        ✅ FIXED: Handle keyboard events with INSTANT response.
        No delays, no animations, pure immediate close.
        """
        if event.key() == Qt.Key_Escape:
            logger.info("🚫 ESC pressed - INSTANT CLOSE")
            
            # Stop everything immediately
            self.dragging = False
            
            # Hide UI instantly (no animations)
            self.control_bar.setVisible(False)
            self.setVisible(False)
            
            # Force immediate window destruction
            self.close()
            
            # Restore main window immediately
            if self.parent_window:
                self.parent_window.setVisible(True)
                self.parent_window.show()
                self.parent_window.raise_()
                self.parent_window.activateWindow()
            
            # Accept event to stop propagation
            event.accept()
            
            logger.info("✅ Overlay closed instantly")
            return
        
        super().keyPressEvent(event)

    # -----------------------------------------------------
    def paintEvent(self, _):
        """Paint the overlay with dimmed background and selection rectangle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Dim the entire screen (darker for better visibility)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

        # Draw selection rectangle if dragging
        if self.dragging:
            # Green selection box
            pen = QPen(QColor(0, 255, 0), 2)
            painter.setPen(pen)
            painter.setBrush(QColor(0, 255, 0, 30))
            
            top_left = self.mapFromGlobal(self.start_global)
            bottom_right = self.mapFromGlobal(self.end_global)
            selection_rect = QRect(top_left, bottom_right).normalized()
            
            painter.drawRect(selection_rect)
            
            # Draw dimensions text
            width = abs(self.end_global.x() - self.start_global.x())
            height = abs(self.end_global.y() - self.start_global.y())
            
            dim_text = f"{width} × {height}"
            
            # Position text near cursor
            text_pos = bottom_right + QPoint(10, 10)
            
            # Draw text background
            font = painter.font()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            
            metrics = painter.fontMetrics()
            text_rect = metrics.boundingRect(dim_text)
            text_rect.adjust(-6, -3, 6, 3)
            text_rect.moveTo(text_pos)
            
            painter.fillRect(text_rect, QColor(0, 0, 0, 180))
            
            # Draw text
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(text_rect, Qt.AlignCenter, dim_text)

    def resizeEvent(self, event):
        """Handle resize - reposition control bar."""
        super().resizeEvent(event)
        if self.control_bar.isVisible():
            self._position_control_bar()
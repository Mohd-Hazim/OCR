# gui/resizable_box.py
"""
Resizable container with drag handle for manual height adjustment.
"""
import logging
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget, QSizePolicy
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QCursor

logger = logging.getLogger(__name__)


class ResizeHandle(QWidget):
    """Draggable resize handle for manual height adjustment."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(8)
        self.setCursor(Qt.SizeVerCursor)
        self.dragging = False
        self.drag_start_y = 0
        self.setStyleSheet("""
            ResizeHandle {
                background: transparent;
            }
        """)
    
    def paintEvent(self, event):
        """Draw visual resize indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get theme from parent chain
        theme = "dark"
        parent = self.parent()
        while parent:
            if hasattr(parent, "current_theme"):
                theme = parent.current_theme
                break
            parent = parent.parent() if hasattr(parent, "parent") else None
        
        # Draw grip dots
        if theme == "dark":
            color = QColor("#94A3B8")
        else:
            color = QColor("#6B7280")
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        
        center_y = self.height() // 2
        center_x = self.width() // 2
        
        # Draw 3 dots
        for i in range(-1, 2):
            painter.drawEllipse(center_x + i * 6 - 1, center_y - 1, 3, 3)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_start_y = event.globalPos().y()
            event.accept()
    
    def mouseMoveEvent(self, event):
        if self.dragging:
            delta = event.globalPos().y() - self.drag_start_y
            self.drag_start_y = event.globalPos().y()
            
            # Notify parent to resize
            container = self.parent()
            if isinstance(container, ResizableBox):
                container.adjust_height(delta)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            
            # Save height after resize complete
            container = self.parent()
            if isinstance(container, ResizableBox):
                container.save_height()


class ResizableBox(QFrame):
    """
    Container with draggable resize handle.
    
    Features:
    - Visual resize grip
    - Minimum/maximum height constraints
    - Auto-save on resize complete
    - Restore saved height on startup
    """
    
    heightChanged = Signal(int)  # Emits new height
    
    def __init__(self, content_widget: QWidget, min_height=100, max_height=600, 
                 save_key=None, parent=None):
        super().__init__(parent)
        self.content_widget = content_widget
        self.min_height = min_height
        self.max_height = max_height
        self.save_key = save_key  # e.g., "preview_height"
        
        self.setObjectName("resizableBox")
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Add content
        layout.addWidget(content_widget)
        
        # Add resize handle
        self.resize_handle = ResizeHandle(self)
        layout.addWidget(self.resize_handle)
        
        # Set initial size policy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        # Debounce timer for save
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save)
    
    def adjust_height(self, delta: int):
        """Adjust height by delta pixels."""
        current_height = self.height()
        new_height = max(self.min_height, min(self.max_height, current_height + delta))
        
        if new_height != current_height:
            self.setFixedHeight(new_height)
            self.heightChanged.emit(new_height)
            logger.debug(f"Adjusted height to {new_height}px")
    
    def set_height(self, height: int):
        """Set height directly."""
        height = max(self.min_height, min(self.max_height, height))
        self.setFixedHeight(height)
        self.heightChanged.emit(height)
    
    def save_height(self):
        """Debounced save to config."""
        if self.save_key:
            self._save_timer.start(500)  # Save after 500ms of no changes
    
    def _do_save(self):
        """Actually save to config."""
        if self.save_key:
            from utils.layout_persistence import LayoutManager
            height = self.height()
            
            if self.save_key == "preview_height":
                LayoutManager.save_preview_height(height)
            elif self.save_key == "extracted_height":
                LayoutManager.save_extracted_height(height)
            elif self.save_key == "translated_height":
                LayoutManager.save_translated_height(height)
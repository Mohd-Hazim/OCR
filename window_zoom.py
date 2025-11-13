# gui/window_zoom.py
"""
Window-level zoom controller for scaling the entire UI.
Supports:
- Ctrl+Scroll for global zoom
- Zoom buttons in UI
- Preserves layout proportions
"""

import logging
from PySide6.QtCore import QObject, Signal, Qt, QEvent
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QWheelEvent

logger = logging.getLogger(__name__)


class WindowZoomController(QObject):
    """
    Controls zoom level for the entire application window.
    Uses CSS transform scaling for smooth zoom without layout reflow.
    """
    
    zoomChanged = Signal(float)  # Emits current zoom level
    
    def __init__(self, target_widget: QWidget, parent=None):
        super().__init__(parent)
        self.target_widget = target_widget
        self.zoom_level = 1.0
        self.min_zoom = 0.5
        self.max_zoom = 2.0
        self.zoom_step = 0.1
        
        # Install event filter to capture Ctrl+Scroll globally
        self.target_widget.installEventFilter(self)
        
        # Store original size for reference
        self.base_width = target_widget.width()
        self.base_height = target_widget.height()
    
    def eventFilter(self, obj, event):
        """Filter events to capture Ctrl+Scroll for window zoom."""
        if event.type() == QEvent.Wheel:
            wheel_event = event
            # Check if Ctrl is pressed
            if wheel_event.modifiers() & Qt.ControlModifier:
                # Check if the event is not already handled by a child widget
                # (e.g., the zoomable preview)
                focused_widget = self.target_widget.focusWidget()
                from gui.zoomable_preview import ZoomableGraphicsView
                
                # Skip if focused on preview view (let it handle its own zoom)
                if focused_widget and isinstance(focused_widget, ZoomableGraphicsView):
                    return False
                
                delta = wheel_event.angleDelta().y()
                
                if delta > 0:
                    self.zoom_in()
                elif delta < 0:
                    self.zoom_out()
                
                return True  # Event handled
        
        return False  # Pass event to next handler
    
    def zoom_in(self):
        """Increase window zoom level."""
        new_zoom = min(self.zoom_level + self.zoom_step, self.max_zoom)
        self.set_zoom(new_zoom)
    
    def zoom_out(self):
        """Decrease window zoom level."""
        new_zoom = max(self.zoom_level - self.zoom_step, self.min_zoom)
        self.set_zoom(new_zoom)
    
    def reset_zoom(self):
        """Reset zoom to 100%."""
        self.set_zoom(1.0)
    
    def set_zoom(self, zoom_level: float):
        """Set the zoom level directly."""
        zoom_level = max(self.min_zoom, min(zoom_level, self.max_zoom))
        
        if abs(zoom_level - self.zoom_level) < 0.01:
            return  # No significant change
        
        self.zoom_level = zoom_level
        self._apply_zoom()
        self.zoomChanged.emit(self.zoom_level)
        logger.info(f"Window zoom set to {self.zoom_level:.1f}x ({int(self.zoom_level * 100)}%)")
    
    def _apply_zoom(self):
        """Apply the zoom transformation to the target widget."""
        # Method 1: Using QWidget scaling (smoother but may affect interactions)
        # Note: This scales the content but doesn't resize the window
        
        # Get the content widget (the scrollable area's widget)
        scroll_area = None
        for child in self.target_widget.children():
            from PySide6.QtWidgets import QScrollArea
            if isinstance(child, QScrollArea):
                scroll_area = child
                break
        
        if scroll_area:
            content_widget = scroll_area.widget()
            if content_widget:
                # Apply transform scaling
                transform = f"scale({self.zoom_level})"
                
                # Update the widget's stylesheet to include transform
                # Note: Qt doesn't support CSS transforms directly, so we use setMinimumSize
                # Alternative: scale using QGraphicsView/QGraphicsProxyWidget
                
                # For PySide6, we'll use a different approach:
                # Adjust font sizes and widget scaling
                self._scale_fonts(content_widget, self.zoom_level)
    
    def _scale_fonts(self, widget: QWidget, scale: float):
        """Recursively scale fonts in the widget tree."""
        # Get base font size
        base_font_size = 11.5  # From your stylesheet
        new_font_size = int(base_font_size * scale)
        
        # Apply to main widget
        font = widget.font()
        font.setPointSize(max(8, new_font_size))  # Minimum 8pt
        widget.setFont(font)
        
        # Recursively apply to children
        for child in widget.findChildren(QWidget):
            child_font = child.font()
            child_font.setPointSize(max(8, new_font_size))
            child.setFont(child_font)


class WindowZoomControllerV3(QObject):
    """
    Scales the *content* of the window instead of resizing the window itself.
    Affects font sizes, spacing, paddings, and widgets inside the scroll area.
    """

    zoomChanged = Signal(float)

    def __init__(self, target_widget: QWidget, parent=None):
        super().__init__(parent)
        self.target_widget = target_widget
        self.zoom_level = 1.0
        self.min_zoom = 0.7
        self.max_zoom = 1.6
        self.zoom_step = 0.1

        # Keep reference to content widget (inside scroll area)
        self.content_widget = None
        for child in target_widget.findChildren(QWidget):
            from PySide6.QtWidgets import QScrollArea
            if isinstance(child, QScrollArea):
                self.content_widget = child.widget()
                break

        # Install event filter for Ctrl+Scroll
        target_widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            wheel_event = event
            if wheel_event.modifiers() & Qt.ControlModifier:
                from gui.zoomable_preview import ZoomableGraphicsView
                focused = self.target_widget.focusWidget()
                if focused and isinstance(focused, ZoomableGraphicsView):
                    return False  # let preview handle it

                delta = wheel_event.angleDelta().y()
                if delta > 0:
                    self.zoom_in()
                elif delta < 0:
                    self.zoom_out()
                return True
        return False

    def zoom_in(self):
        self.set_zoom(min(self.zoom_level + self.zoom_step, self.max_zoom))

    def zoom_out(self):
        self.set_zoom(max(self.zoom_level - self.zoom_step, self.min_zoom))

    def reset_zoom(self):
        self.set_zoom(1.0)

    def set_zoom(self, level: float):
        level = max(self.min_zoom, min(level, self.max_zoom))
        if abs(level - self.zoom_level) < 0.01:
            return

        self.zoom_level = level
        self._apply_content_zoom(level)
        self.zoomChanged.emit(level)
        logger.info(f"Content zoom set to {int(level * 100)}%")

    def _apply_content_zoom(self, scale: float):
        """Recursively scale fonts, margins, and spacings for all child widgets."""
        if not self.content_widget:
            return

        base_font = self.content_widget.font()
        base_font.setPointSizeF(11.5 * scale)
        self.content_widget.setFont(base_font)

        # Recursively apply to children
        for child in self.content_widget.findChildren(QWidget):
            # Skip zoom controls inside ZoomablePreviewWidget
            if child.objectName() in ("zoomControlBar",) or child.property("noZoomScale"):
                continue

            f = child.font()
            f.setPointSizeF(max(8, 11.5 * scale))
            child.setFont(f)

            layout = child.layout()
            if layout:
                m = int(8 * scale)
                layout.setContentsMargins(m, m, m, m)
                layout.setSpacing(int(8 * scale))

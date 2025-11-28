# gui/zoomable_preview.py
"""
Zoomable image preview widget with zoom controls.
Supports:
- Ctrl+Scroll wheel zoom
- Touchpad pinch zoom (via Ctrl+Scroll)
- Zoom buttons (+/-)
- Click and drag to pan when zoomed
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QFrame
)
from PySide6.QtCore import Qt, QPointF, Signal, QRectF, QSize
from PySide6.QtGui import QPixmap, QPainter, QWheelEvent, QImage, QIcon

logger = logging.getLogger(__name__)


class ZoomableGraphicsView(QGraphicsView):
    """Custom QGraphicsView with zoom and pan support."""
    
    zoomChanged = Signal(float)  # Emits current zoom level
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Zoom settings
        self.zoom_factor = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 10.0
        self.zoom_step = 1.15  # 15% per step
        
        # Enable mouse tracking for smooth zoom
        self.setMouseTracking(True)
        
    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel for zooming (with Ctrl modifier)."""
        # Check if Ctrl is pressed (or Cmd on macOS)
        if event.modifiers() & Qt.ControlModifier:
            # Get the scroll direction
            delta = event.angleDelta().y()
            
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
                
            event.accept()
        else:
            # Normal scroll behavior
            super().wheelEvent(event)
    
    def zoom_in(self, factor=None):
        """Zoom in by the specified factor."""
        # Handle accidental bool/zero input from Qt signals
        if not isinstance(factor, (int, float)) or factor <= 0:
            factor = self.zoom_step

        new_zoom = self.zoom_factor * factor
        if new_zoom <= self.max_zoom:
            self.scale(factor, factor)
            self.zoom_factor = new_zoom
            self.zoomChanged.emit(self.zoom_factor)
            logger.debug(f"Zoomed in to {self.zoom_factor:.2f}x")

    def zoom_out(self, factor=None):
        """Zoom out by the specified factor."""
        # Handle accidental bool/zero input from Qt signals
        if not isinstance(factor, (int, float)) or factor <= 0:
            factor = self.zoom_step

        new_zoom = self.zoom_factor / factor
        if new_zoom >= self.min_zoom:
            self.scale(1 / factor, 1 / factor)
            self.zoom_factor = new_zoom
            self.zoomChanged.emit(self.zoom_factor)
            logger.debug(f"Zoomed out to {self.zoom_factor:.2f}x")

    
    def reset_zoom(self):
        """Reset zoom to 100%."""
        self.resetTransform()
        self.zoom_factor = 1.0
        self.zoomChanged.emit(self.zoom_factor)
        logger.debug("Zoom reset to 1.0x")
    
    def fit_in_view(self):
        """Fit the entire image in the view."""
        if self.scene():
            self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)
            # Calculate the actual zoom factor after fitting
            if self.scene().sceneRect().width() > 0:
                self.zoom_factor = self.transform().m11()
                self.zoomChanged.emit(self.zoom_factor)
                logger.debug(f"Fit in view, zoom = {self.zoom_factor:.2f}x")


class ZoomablePreviewWidget(QWidget):
    """
    Complete zoomable preview widget with controls.
    Replaces the standard QTextEdit preview box.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_pixmap = None
        self._init_ui()
        
    def _init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # --- Graphics View for Image Display ---
        self.scene = QGraphicsScene(self)
        self.view = ZoomableGraphicsView(self)
        self.view.setScene(self.scene)
        self.view.setMinimumHeight(180)
        self.view.setMinimumHeight(100)

        
        # Pixmap item (will hold the image)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        
        layout.addWidget(self.view)
        
        # --- Zoom Controls Bar ---
        controls_frame = QFrame()
        controls_frame.setObjectName("zoomControlBar")      # ✅ used to skip global zoom scaling
        controls_frame.setProperty("noZoomScale", True)     # ✅ opt-out flag
        controls_frame.setFixedWidth(220)                   # keeps size stable
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(6, 2, 6, 2)
        controls_layout.setSpacing(6)
        controls_layout.setAlignment(Qt.AlignCenter)

        from PySide6.QtGui import QIcon
        import os

        BASE_DIR = os.path.dirname(__file__)
        ASSETS_DIR = os.path.join(BASE_DIR, "..", "assets", "icons")
        
        # Theme-adaptive icons
        self.plus_icon_light = os.path.join(ASSETS_DIR, "plus_light.png")
        self.plus_icon_dark = os.path.join(ASSETS_DIR, "plus_dark.png")
        self.minus_icon_light = os.path.join(ASSETS_DIR, "minus_light.png")
        self.minus_icon_dark = os.path.join(ASSETS_DIR, "minus_dark.png")

        # Zoom Out Button
        self.zoom_out_btn = QPushButton()
        self.zoom_out_btn.setFixedSize(28, 28)
        self.zoom_out_btn.setToolTip("Zoom Out (Ctrl + Scroll Down)")
        self.zoom_out_btn.clicked.connect(self.view.zoom_out)
        
        # Zoom Level Label
        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setMinimumWidth(50)
        self.zoom_label.setStyleSheet("font-weight: 500; font-size: 10px;")
        
        # Zoom In Button
        self.zoom_in_btn = QPushButton()
        self.zoom_in_btn.setFixedSize(28, 28)
        self.zoom_in_btn.setToolTip("Zoom In (Ctrl + Scroll Up)")
        self.zoom_in_btn.clicked.connect(self.view.zoom_in)
        
        from PySide6.QtGui import QIcon
        import os

        BASE_DIR = os.path.dirname(__file__)
        ASSETS_DIR = os.path.join(BASE_DIR, "..", "assets", "icons")

        # Theme-adaptive icons (light/dark)
        self.reset_icon_light = os.path.join(ASSETS_DIR, "reset_light.png")
        self.reset_icon_dark = os.path.join(ASSETS_DIR, "reset_dark.png")
        self.resize_icon_light = os.path.join(ASSETS_DIR, "resize_light.png")
        self.resize_icon_dark = os.path.join(ASSETS_DIR, "resize_dark.png")

        # Buttons
        self.reset_btn = QPushButton()
        self.reset_btn.setFixedSize(28, 28)
        self.reset_btn.setToolTip("Reset Zoom (100%)")
        self.reset_btn.clicked.connect(self.view.reset_zoom)

        self.fit_btn = QPushButton()
        self.fit_btn.setFixedSize(28, 28)
        self.fit_btn.setToolTip("Fit to View")
        self.fit_btn.clicked.connect(self.view.fit_in_view)

                # Uniform sizing and alignment
        for btn in [self.zoom_out_btn, self.zoom_in_btn, self.reset_btn, self.fit_btn]:
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.PointingHandCursor)

        self.zoom_label.setFixedHeight(24)
        self.zoom_label.setAlignment(Qt.AlignVCenter | Qt.AlignHCenter)
        self.zoom_label.setMinimumWidth(50)
        self.zoom_label.setStyleSheet("font-weight: 500; font-size: 10px; margin-top: 1px;")

        # Centered, balanced order
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.zoom_out_btn)
        controls_layout.addSpacing(4)
        controls_layout.addWidget(self.zoom_label)
        controls_layout.addSpacing(4)
        controls_layout.addWidget(self.zoom_in_btn)
        controls_layout.addSpacing(10)
        controls_layout.addWidget(self.reset_btn)
        controls_layout.addSpacing(4)
        controls_layout.addWidget(self.fit_btn)
        controls_layout.addStretch(1)

        layout.addWidget(controls_frame, alignment=Qt.AlignCenter)

        
        # Connect zoom change signal
        self.view.zoomChanged.connect(self._update_zoom_label)
        
        # Apply styling
        self._apply_control_styles()
    
    def _apply_control_styles(self):
        """Apply consistent styling to zoom controls."""
        button_style = """
            QPushButton {
                background: transparent;
                border: none;
                color: #E2E8F0;
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(62, 156, 246, 0.15);
                border-radius: 6px;
            }
            QPushButton:pressed {
                background-color: rgba(62, 156, 246, 0.25);
            }
        """
        
        self.zoom_out_btn.setStyleSheet(button_style)
        self.zoom_in_btn.setStyleSheet(button_style)
        self.reset_btn.setStyleSheet(button_style)
        self.fit_btn.setStyleSheet(button_style)
    
    def update_icons_for_theme(self, theme: str):
        """Switch all zoom control icons based on theme."""
        if theme == "light":
            self.reset_btn.setIcon(QIcon(self.reset_icon_dark))
            self.fit_btn.setIcon(QIcon(self.resize_icon_dark))
            self.zoom_in_btn.setIcon(QIcon(self.plus_icon_dark))
            self.zoom_out_btn.setIcon(QIcon(self.minus_icon_dark))
        else:
            self.reset_btn.setIcon(QIcon(self.reset_icon_light))
            self.fit_btn.setIcon(QIcon(self.resize_icon_light))
            self.zoom_in_btn.setIcon(QIcon(self.plus_icon_light))
            self.zoom_out_btn.setIcon(QIcon(self.minus_icon_light))

        for btn in (self.reset_btn, self.fit_btn, self.zoom_in_btn, self.zoom_out_btn):
            btn.setIconSize(QSize(20, 20))

    def _update_zoom_label(self, zoom_factor: float):
        """Update the zoom percentage label."""
        percentage = int(zoom_factor * 100)
        self.zoom_label.setText(f"{percentage}%")
    
    def set_image_from_base64(self, base64_data: str):
        """Set the preview image from base64 data."""
        try:
            import base64
            from io import BytesIO
            
            # Decode base64
            image_data = base64.b64decode(base64_data)
            
            # Convert to QPixmap
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            
            self.set_pixmap(pixmap)
            
        except Exception as e:
            logger.error(f"Failed to load image from base64: {e}")
    
    def set_pixmap(self, pixmap: QPixmap):
        """Set the preview image from a QPixmap."""
        if pixmap and not pixmap.isNull():
            self.current_pixmap = pixmap
            self.pixmap_item.setPixmap(pixmap)
            
            # Update scene rect to match image size
            self.scene.setSceneRect(QRectF(pixmap.rect()))
            
            # Fit image in view initially
            self.view.fit_in_view()
            
            logger.debug(f"Image loaded: {pixmap.width()}×{pixmap.height()}")
        else:
            logger.warning("Invalid pixmap provided")
    
    def set_image_from_pil(self, pil_image):
        """Set the preview image from a PIL Image."""
        try:
            from PIL import Image
            import io
            
            # Convert PIL to QPixmap
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG')
            buffer.seek(0)
            
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.read())
            
            self.set_pixmap(pixmap)
            
        except Exception as e:
            logger.error(f"Failed to load PIL image: {e}")
    
    def clear(self):
        """Clear the preview image."""
        self.pixmap_item.setPixmap(QPixmap())
        self.scene.setSceneRect(QRectF())
        self.current_pixmap = None
        self.view.reset_zoom()
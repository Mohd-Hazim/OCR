# gui/popup.py
"""
Fluent Dark OCR Capture Tool (Final Build with ThemeSwitch)
Features:
- Compact 440×560 window
- Copy icons inside text boxes (24x24)
- 2-second 'Copied!' feedback
- Editable text boxes
- Scrollable Fluent UI
- Animated icon-only ThemeSwitch with soft thumb glow
- Unified card-style text boxes (Preview, Extracted, Translated)
"""

import os
import logging

import tempfile
import os

import base64
from io import BytesIO
import cv2
import numpy as np
from .animations import make_anim, ANIM_FAST, ANIM_NORMAL, ANIM_SLOW, EASE_SOFT
from markdown import markdown
import re
from gui.zoomable_preview import ZoomablePreviewWidget
from gui.window_zoom import WindowZoomControllerV3
from PySide6.QtCore import QEventLoop

from gui.resizable_box import ResizableBox, ResizeHandle
from utils.layout_persistence import LayoutManager
from PySide6.QtGui import QCursor

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QLabel, QComboBox, QProgressBar, QSystemTrayIcon, QMenu,
    QFrame, QScrollArea, QSizePolicy
)
from PySide6.QtGui import QIcon, QGuiApplication, QPainter, QColor, QAction, QPen, QMovie
from PySide6.QtCore import (
    Qt, QThread, QTimer, Signal, QObject, QPropertyAnimation, QPoint, QSize, Property, QEasingCurve
)
from core import capture
from core.capture import capture_region
from core.worker import OCRWorker

try:
    from gui.overlay import SelectionOverlay
except Exception:
    from gui.overlay import SelectionOverlay

try:
    from utils.config import load_config, save_config
except Exception:
    from uls.config import load_config, save_config  # type: ignore
from utils.config import get_config_value, set_config_value
logger = logging.getLogger(__name__)

# --- Palette base (dark theme) ---
COLOR_BG = "#0F172A"
COLOR_CARD = "#1E293B"
COLOR_DARKER = "#172032"
COLOR_BORDER = "#334155"
COLOR_ACCENT = "#475569"
COLOR_TEXT = "#E2E8F0"
COLOR_MUTED = "#94A3B8"

# --- Icon paths (absolute) ---
BASE_DIR = os.path.dirname(__file__)
COPY_ICON_LIGHT = os.path.join(BASE_DIR, "..", "assets", "icons", "copy_light.png")  # white icon
COPY_ICON_DARK = os.path.join(BASE_DIR, "..", "assets", "icons", "copy_dark.png")   # black icon
CAPTURE_ICON_PATH = os.path.join(BASE_DIR, "..", "assets", "icons", "capture_light.png")
TRANSLATE_ICON_PATH = os.path.join(BASE_DIR, "..", "assets", "icons", "translate_icon.png")

def get_app_icon():
    path = os.path.join(os.path.dirname(__file__), "..", "assets", "icons", "ocr_icon.png")
    return QIcon(path) if os.path.exists(path) else QIcon()


def pil_to_base64(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class TranslatorThread(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, text, dest):
        super().__init__()
        self.text = text
        self.dest = dest

    def run(self):
        try:
            from core.ocr_translate import translate_text
            self.finished.emit(translate_text(self.text, dest_lang=self.dest) or "")
        except Exception as e:
            self.failed.emit(str(e))


# ---------------- ThemeSwitch widget ----------------
class ThemeSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent=None, initial_on: bool = True, size: QSize = QSize(42, 24)):
        super().__init__(parent)
        self.setStyleSheet("background: none; border: none;")
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setFixedSize(size)
        self._offset = 1.0 if initial_on else 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(160)
        self._on = initial_on
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, ev):
        self.setChecked(not self._on)
        super().mouseReleaseEvent(ev)

    def setChecked(self, on: bool):
        if self._on == on:
            return
        self._on = on
        start = self._offset
        end = 1.0 if on else 0.0
        self._animation.stop()
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.start()
        self.toggled.emit(on)
        self.update()

    def isChecked(self) -> bool:
        return self._on

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        r = h / 2
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # ✅ Get theme from parent window
        theme = "dark"
        if hasattr(self.parent(), "current_theme"):
            theme = self.parent().current_theme
        elif hasattr(self.parent(), "parent") and hasattr(self.parent().parent(), "current_theme"):
            theme = self.parent().parent().current_theme

        # 🎨 REFINED: Balanced color palette for both themes
        if theme == "light":
            # Active state (ON) - Purple accent
            on_col = QColor("#7C3AED")      # Vibrant violet
            # Inactive state (OFF) - Neutral gray (no lavender)
            off_col = QColor("#E5E7EB")     # Light neutral gray
        else:
            # Dark theme - Enhanced with depth
            on_col = QColor("#3B82F6")      # Brighter blue for better contrast
            off_col = QColor("#334155")     # Deeper slate for better depth

        # Determine current state colors (NO BORDERS)
        bg_col = on_col if self._on else off_col

        # Draw track (no borders)
        p.setPen(Qt.NoPen)
        p.setBrush(bg_col)
        p.drawRoundedRect(0, 0, w, h, r, r)

        # Draw thumb with glow
        padding = 2
        thumb_d = h - padding * 2
        x = padding + (w - padding * 2 - thumb_d) * self._offset
        y = padding

        # Glow effect (active state only)
        if self._on:
            glow_col = QColor(on_col.red(), on_col.green(), on_col.blue(), int(80 * (0.6 + 0.4 * self._offset)))
            p.setBrush(glow_col)
            p.setPen(Qt.NoPen)
            glow_r = thumb_d * 1.2
            glow_x = x + thumb_d / 2 - glow_r / 2
            glow_y = y + thumb_d / 2 - glow_r / 2
            p.drawEllipse(int(glow_x), int(glow_y), int(glow_r), int(glow_r))

        # Thumb itself
        p.setBrush(QColor("#FFFFFF"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(int(x), int(y), int(thumb_d), int(thumb_d))

        # Icon inside thumb
        p.setPen(QColor("#172032"))
        icon_char = "🌙" if self._offset > 0.5 else "☀️"
        p.drawText(int(x), int(y), int(thumb_d), int(thumb_d), Qt.AlignCenter, icon_char)

        p.end()

    def getOffset(self):
        return self._offset

    def setOffset(self, v):
        self._offset = float(v)
        self.update()

    offset = Property(float, getOffset, setOffset)


# ========================================================================
# Replace the ToggleSwitch class (lines 289-391) with this:
# ========================================================================

class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent=None, checked=False):
        super().__init__(parent)
        self.setStyleSheet("background: none; border: none;")
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setFixedSize(46, 24)
        self._offset = 1.0 if checked else 0.0
        self._checked = checked
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(180)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        self.setChecked(not self._checked)
        super().mouseReleaseEvent(event)

    def isChecked(self):
        return self._checked

    def setChecked(self, state: bool):
        if self._checked == state:
            return
        self._checked = state
        start = getattr(self, "_offset", 0.0)
        end = 1.0 if state else 0.0
        self._anim.stop()
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()
        self.toggled.emit(state)
        self.update()

    def getOffset(self):
        return getattr(self, "_offset", 0.0)

    def setOffset(self, value):
        self._offset = float(value)
        self.update()

    offset = Property(float, getOffset, setOffset)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.height() / 2
        thumb_d = self.height() - 6

        # ✅ FIXED: Proper theme detection from parent chain
        theme = "dark"
        parent = self.parent()
        while parent:
            if hasattr(parent, "current_theme"):
                theme = parent.current_theme
                break
            parent = parent.parent() if hasattr(parent, "parent") else None

        # 🎨 FIXED: Colors now match the new light theme palette
        if self._checked:
            # Active/ON state
            if theme == "light":
                bg = QColor("#7C3AED")       # Vibrant violet
            else:
                bg = QColor("#3E9CF6")       # Blue
            border_pen = Qt.NoPen
        else:
            # Inactive/OFF state - THIS WAS THE MAIN ISSUE
            if theme == "light":
                bg = QColor("#D8C9F6")       # Soft lavender (instead of gray!)
                border_pen = QPen(QColor("#A78BFA"), 1)  # Lavender border
            else:
                bg = QColor("#475569")       # Slate gray
                border_pen = Qt.NoPen

        # Draw track
        p.setPen(border_pen)
        p.setBrush(bg)
        p.drawRoundedRect(0, 0, self.width(), self.height(), r, r)

        # Draw thumb
        x = 3 + (self.width() - thumb_d - 6) * self._offset
        p.setBrush(Qt.white)
        p.setPen(Qt.NoPen)
        p.drawEllipse(int(x), 3, thumb_d, thumb_d)

        p.end()
# ---------------- Main Popup ----------------
class PopupWindow(QWidget):
    from PySide6.QtCore import Signal

    trigger_text = Signal()
    trigger_table = Signal()
    trigger_popup = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Teaching Pariksha")
        self.setWindowIcon(get_app_icon())
        
        # --- Fixed, slightly larger window ---
        fixed_width = 520
        fixed_height = 620

        self.setFixedSize(fixed_width, fixed_height)
        self.setGeometry(120, 120, fixed_width, fixed_height)
        
        # ✅ Prevent automatic resizing when switching monitors or themes
        self.setAttribute(Qt.WA_StaticContents, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setAttribute(Qt.WA_Hover, True)

        scr = QGuiApplication.primaryScreen().geometry().center()
        self.move(scr.x() - self.width() // 2, scr.y() - self.height() // 2)

        # Load config and theme
        self.config = load_config()
        self.config["use_gemini_api"] = True
        save_config(self.config)
        self.current_theme = self.config.get("theme", "dark")
        self.config["theme"] = self.current_theme
        self._deferred_save_config()

        # Initialize states
        self.ocr_text = ""
        self.translated_text = ""

        # Default opacity for copy icons (prevents AttributeError)
        self.copy_icon_opacity = 0.6

        self.selected_content_mode = "text"  # Default capture mode
        self.layout_type = "text"
        self.layout_confidence = 1.0
        self.override_table_model = False
        
        # Initialize UI and logic
        self._init_scroll_ui()
        self._init_window_zoom_controls()
        self._apply_theme(self.current_theme)
        self._setup_tray()
        self._init_copied_label()
        self._init_loaders()
        from gui.mode_selector import ModeSelector
        self.mode_popup = ModeSelector()
        self.mode_popup.mode_selected.connect(self._on_mode_chosen)
        # no cancelled signal, so don't connect anything

        self._init_shortcuts()
        self.installEventFilter(self)
        self._start_hotkey_listener()
        self._tray_menu_open = False
        self._ignore_tray_click_until = 0

        self.shortcut_override_mode = None

        self.trigger_text.connect(lambda: self._start_capture_mode("text"))
        self.trigger_table.connect(lambda: self._start_capture_mode("table"))
        self.trigger_popup.connect(self.show_main_window)

        from core.capture import initialize_capture_debug
        initialize_capture_debug()
    
    def show_main_window(self):
        """Show the main GUI when the 'popup' hotkey is pressed."""
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    # ===============================================================
    #  MULTI-KEY CHORD SHORTCUTS (Alt+T+1, Alt+T+2, Alt+T+P)
    # ===============================================================
    def _init_shortcuts(self):
        self._key_buffer = []
        self._key_timer = QTimer(self)
        self._key_timer.setInterval(600)   # 0.6 seconds to complete the combo
        self._key_timer.setSingleShot(True)
        self._key_timer.timeout.connect(self._clear_key_buffer)
        
    def _begin_record_shortcut(self, box, key_name):
        box.setText("Recording…")
        box.recording = True
        box.key_name = key_name

    def _finish_record_shortcut(self, box, final_text):
        box.setText(final_text)
        box.recording = False
        self.config[box.key_name] = final_text
        save_config(self.config)

    def _clear_key_buffer(self):
        self._key_buffer.clear()

    def eventFilter(self, obj, event):
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent
        # ---------------- SHORTCUT RECORDING ----------------
        for box in [self.shortcut_text_box, self.shortcut_table_box, self.shortcut_popup_box]:
            if hasattr(box, "recording") and box.recording:
                if event.type() == QEvent.KeyPress:
                    mods = []
                    if event.modifiers() & Qt.ControlModifier: mods.append("ctrl")
                    if event.modifiers() & Qt.ShiftModifier: mods.append("shift")
                    if event.modifiers() & Qt.AltModifier: mods.append("alt")

                    key = event.text().lower()
                    if not key:
                        return True

                    parts = mods + [key]
                    hotkey = "+".join(parts)

                    self._finish_record_shortcut(box, hotkey)
                    return True

        if isinstance(event, QKeyEvent) and event.type() == QEvent.KeyPress:

            # detect modifier
            mods = event.modifiers()
            if mods & Qt.AltModifier:

                ch = event.text().lower()

                if ch:
                    self._key_buffer.append(ch)
                    self._key_timer.start()

                    # -------- Load shortcuts from config --------
                    text_sc = self.config.get("shortcut_text", "alt+t+1").split("+")
                    table_sc = self.config.get("shortcut_table", "alt+t+2").split("+")
                    popup_sc = self.config.get("shortcut_popup", "alt+t+p").split("+")

                    # Remove "alt" because eventFilter already matched ALT
                    text_keys = text_sc[1:]
                    table_keys = table_sc[1:]
                    popup_keys = popup_sc[1:]

                    # -------- Match keys for TEXT mode --------
                    if self._key_buffer == text_keys:
                        self._clear_key_buffer()
                        self._start_capture_mode("text")
                        return True

                    # -------- Match keys for TABLE mode --------
                    if self._key_buffer == table_keys:
                        self._clear_key_buffer()
                        self._start_capture_mode("table")
                        return True

                    # -------- Match keys for POPUP --------
                    if self._key_buffer == popup_keys:
                        self._clear_key_buffer()
                        self._show_left_click_menu()
                        return True

        return super().eventFilter(obj, event)

    def _on_mode_chosen(self, mode):
        """Handle mode (Text/Table) selection from ModeSelector."""
        self.selected_content_mode = mode
        self.start_capture()
        
    def _show_left_click_menu(self):
        import time
        self._tray_menu_open = True

        menu = QMenu()

        text_action = QAction("Text", self)
        table_action = QAction("Table", self)
        cancel_action = QAction("Cancel", self)

        text_action.triggered.connect(lambda: self._start_capture_mode("text"))
        table_action.triggered.connect(lambda: self._start_capture_mode("table"))
        cancel_action.triggered.connect(lambda: None)

        menu.addAction(text_action)
        menu.addAction(table_action)
        menu.addSeparator()
        menu.addAction(cancel_action)

        # When menu closes → delay tray acceptance for 200ms
        def _on_close():
            self._tray_menu_open = False
            self._ignore_tray_click_until = time.time() + 0.25

        menu.aboutToHide.connect(_on_close)

        menu.exec(QCursor.pos())

    def _reset_layout_sizes(self):
        """Reset all sizes to defaults."""
        # Reset window size
        self.resize(440, 560)
        
        # Reset box heights
        if hasattr(self, 'preview_box'):
            self.preview_box.set_height(210)
            self.preview_box.save_height()
        
        if hasattr(self, 'extracted_resizable'):
            self.extracted_resizable.set_height(180)
            self.extracted_resizable.save_height()
        
        if hasattr(self, 'translated_resizable'):
            self.translated_resizable.set_height(180)
            self.translated_resizable.save_height()
        
        # Save window size
        LayoutManager.save_window_size(440, 560)
        
        # Show confirmation
        self.status_label.setText("✅ Layout reset to defaults")
        self.status_label.setVisible(True)
        QTimer.singleShot(2000, lambda: self.status_label.setVisible(False))
        
        logger.info("Layout sizes reset to defaults")
        
    # ---------- Copied feedback ----------
    def _init_copied_label(self):
        self.copied_label = QLabel("Copied!", self)
        self.copied_label.setAlignment(Qt.AlignCenter)
        self.copied_label.setVisible(False)
        self.copied_label.setStyleSheet(f"""
            QLabel {{
                background: {COLOR_ACCENT};
                color: white;
                border-radius: 6px;
                padding: 3px 10px;
                font-size: 11px;
            }}
        """)

    def _init_loaders(self):
        """
        Create centered GIF loaders with immediate visibility.
        Loaders are positioned as overlays inside their respective frames.
        """
        # Create loader labels (children of the frame, not the text box)
        self.loader_extracted = QLabel(self.extracted_frame)
        self.loader_translated = QLabel(self.translated_frame)

        for loader in (self.loader_extracted, self.loader_translated):
            loader.setAlignment(Qt.AlignCenter)
            loader.setAttribute(Qt.WA_TranslucentBackground, True)
            loader.setStyleSheet("background: transparent; border: none;")
            loader.setVisible(False)
            loader.setFixedSize(64, 64)
            loader.raise_()  # Ensure it's on top

        # Initialize GIF movies for both themes
        self._setup_loader_movies()

        # Connect resize events for repositioning
        self.extracted_frame.resizeEvent = self._make_resize_handler(
            self.extracted_frame.resizeEvent, 
            self.loader_extracted, 
            self.extracted_box
        )
        
        self.translated_frame.resizeEvent = self._make_resize_handler(
            self.translated_frame.resizeEvent,
            self.loader_translated,
            self.translated_box
        )

        # Position loaders immediately
        QTimer.singleShot(10, self._reposition_all_loaders)

    def _setup_loader_movies(self):
        """Initialize GIF movies for current theme (deferred start)."""
        from PySide6.QtGui import QMovie  # import here so module imports are resilient

        base_path = os.path.join(os.path.dirname(__file__), "..", "assets", "loaders")

        # Map theme -> file (ensure filenames match intent)
        if self.current_theme == "dark":
            gif_path = os.path.join(base_path, "loader_light.gif")   # dark theme GIF
        else:
            gif_path = os.path.join(base_path, "loader_dark.gif")  # light theme GIF

        # Add file existence check
        if not os.path.exists(gif_path):
            logger.warning(f"Loader GIF not found: {gif_path}")
            # clear any existing movies
            for loader in (getattr(self, "loader_extracted", None), getattr(self, "loader_translated", None)):
                if loader and loader.movie():
                    loader.movie().stop()
                    loader.setMovie(None)
            return

        # Create and configure movies but do NOT start them until shown
        for loader in (self.loader_extracted, self.loader_translated):
            if loader is None:
                continue
            movie = QMovie(gif_path)
            loader.setFixedSize(70, 70)
            loader.setMovie(movie)
            # do NOT call movie.start() here; start only when making visible
            logger.debug(f"Loaded GIF for theme '{self.current_theme}': {gif_path}")

    def _make_resize_handler(self, original_handler, loader, target_box):
        """Factory for resize event handlers that reposition loaders."""
        def handler(event):
            self._reposition_loader(loader, target_box)
            if original_handler:
                original_handler(event)
        return handler

    def _reposition_loader(self, loader, target_box):
        """Center loader over target text box."""
        tb_geo = target_box.geometry()
        x = tb_geo.left() + (tb_geo.width() - loader.width()) // 2
        y = tb_geo.top() + (tb_geo.height() - loader.height()) // 2
        loader.move(max(0, x), max(0, y))

    def _reposition_all_loaders(self):
        """Reposition both loaders (called after layout changes)."""
        self._reposition_loader(self.loader_extracted, self.extracted_box)
        self._reposition_loader(self.loader_translated, self.translated_box)

    def _update_loader_theme(self):
        """Update loader GIFs when theme changes."""
        self._setup_loader_movies()

    # =========================================================================
    # SHOW/HIDE LOADERS WITH IMMEDIATE VISIBILITY
    # =========================================================================

    def _show_loader(self, loader: QLabel, immediate: bool = True):
        """Show loader with guaranteed immediate visibility."""
        logger.info(f"🔄 Showing loader: visible={loader.isVisible()}, immediate={immediate}")
        
        # Ensure loader is on top and centered
        loader.raise_()
        if loader == self.loader_extracted:
            self._reposition_loader(loader, self.extracted_box)
        else:
            self._reposition_loader(loader, self.translated_box)
        
        # Make visible
        loader.setVisible(True)
        
        # Restart animation
        movie = loader.movie()
        if movie:
            movie.start()
            logger.debug(f"✅ Loader animation started: frameCount={movie.frameCount()}")
        else:
            logger.warning("⚠️ Loader has no movie!")
        
        if immediate:
            # Force Qt to process all pending events and render
            QApplication.processEvents(QEventLoop.AllEvents, 100)
            loader.repaint()  # Force immediate repaint
            logger.info(f"✅ Loader now visible: {loader.isVisible()}")

    def _hide_loader(self, loader: QLabel, delay_ms: int = 0):
        """Hide loader after optional delay."""
        logger.info(f"⏹️ Hiding loader: delay={delay_ms}ms")
        
        def do_hide():
            loader.setVisible(False)
            movie = loader.movie()
            if movie:
                movie.stop()
            logger.debug("✅ Loader hidden")
        
        if delay_ms > 0:
            QTimer.singleShot(delay_ms, do_hide)
        else:
            do_hide()

    def _fade_widget(self, widget, show=True, duration=ANIM_NORMAL):
        """Smooth fade-in/out animation for widgets (used for loaders)."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

        anim = make_anim(
            effect,
            b"opacity",
            0.0 if show else 1.0,
            1.0 if show else 0.0,
            dur=duration,
            curve=EASE_SOFT
        )
        anim.start()
        self._fade_widget_anim = anim

        widget.setVisible(True)
        if not show:
            anim.finished.connect(lambda: widget.setVisible(False))

    from gui.animations import make_anim, ANIM_FAST, EASE_SOFT

    def _show_copied(self, pos):
        """Show 'Copied!' label with fade-in/out using unified animation system."""
        self.copied_label.move(pos - QPoint(30, 28))
        self.copied_label.setWindowOpacity(0.0)
        self.copied_label.setVisible(True)

        fade_in = make_anim(self.copied_label, b"windowOpacity", 0.0, 1.0, dur=ANIM_FAST, curve=EASE_SOFT)
        fade_in.start()
        self._fade_anim_in = fade_in

        QTimer.singleShot(1800, self._fade_out_copied)

    def _fade_out_copied(self):
        fade_out = make_anim(self.copied_label, b"windowOpacity", 1.0, 0.0, dur=300, curve=EASE_SOFT)
        fade_out.start()
        fade_out.finished.connect(lambda: self.copied_label.setVisible(False))
        self._fade_anim_out = fade_out

    # ---------- Scroll container ----------
    def _init_scroll_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self._init_ui_layout(layout)
        scroll.setWidget(content)

        main = QVBoxLayout(self)
        main.addWidget(scroll)
        self.setLayout(main)

    # ---------- UI layout ----------
    def _init_ui_layout(self, root):
        # --- Capture Button (icon-only, minimal style) ---
        self.capture_btn = QPushButton()
        self.capture_btn.setObjectName("captureButton")
        self.capture_btn.setFixedSize(34, 34)
        self.capture_btn.setIcon(QIcon(CAPTURE_ICON_PATH))
        self.capture_btn.setIconSize(QSize(20, 20))
        self.capture_btn.setCursor(Qt.PointingHandCursor)
        self.capture_btn.setFlat(True)
        self.capture_btn.setToolTip("Capture Screen")
        self.capture_btn.clicked.connect(self.start_capture)

        # Minimal Fluent hover glow, no background color
        self.capture_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: rgba(62,156,246,0.15);
                border-radius: 8px;
            }
        """)

        # --- Header Bar (Logo + Tool Name + Capture + Settings) ---
        header_frame = QFrame()
        header_frame.setObjectName("headerBar")
        header_frame.setAttribute(Qt.WA_StyledBackground, True)

        # ✅ Fixed height, stretchable width
        header_frame.setFixedHeight(48)  # or 42 if you prefer slightly thinner
        header_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # ✅ Optional: subtle drop shadow for visual depth
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(0, 0, 0, 50 if self.current_theme == "dark" else 80))
        shadow.setOffset(0, 1)
        header_frame.setGraphicsEffect(shadow)

        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 0, 10, 0)  # add small side padding
        header_layout.setSpacing(8)
        header_layout.setAlignment(Qt.AlignVCenter)  # ✅ vertically center contents

        # Logo (transparent background)
        logo_path = os.path.join(BASE_DIR, "..", "assets", "icons", "ocr_icon.png")
        logo_label = QLabel()
        logo_label.setAttribute(Qt.WA_TranslucentBackground, True)
        logo_label.setStyleSheet("background: transparent; padding: 0; margin: 0;")
        if os.path.exists(logo_path):
            logo_label.setPixmap(QIcon(logo_path).pixmap(28, 28))
        logo_label.setFixedSize(28, 28)

        # Title
        title_label = QLabel("OCR Capture Tool")
        title_label.setStyleSheet("""
            QLabel {
                background: transparent;    /* ✅ removes that dark box */
                font-size: 15px;
                font-weight: 600;
                letter-spacing: 0.3px;
                padding: 0;
                margin: 0;
            }
        """)
        # --- Menu Button ---
        self.menu_btn = QPushButton()
        self.menu_btn.setObjectName("menuButton")
        self.menu_btn.setFixedSize(34, 34)
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.setFlat(True)
        self.menu_btn.setToolTip("Menu")
        self.menu_btn.clicked.connect(self.toggle_settings_panel)
        self.menu_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: rgba(62,156,246,0.15);
                border-radius: 8px;
            }
        """)

        # Layout order
        header_layout.addWidget(logo_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        # --- Content Type Dropdown ---
        self.mode_dropdown = QComboBox()
        self.mode_dropdown.addItems(["Text", "Tables"])
        self.mode_dropdown.setFixedHeight(32)
        self.mode_dropdown.setMinimumWidth(150)
        self.mode_dropdown.setCursor(Qt.PointingHandCursor)
        
        # Default capture mode
        self.selected_content_mode = "text"

        def _on_mode_changed(index):
            """Handle content mode dropdown changes."""
            mode = self.mode_dropdown.currentText()
            if mode == "Text":
                self.selected_content_mode = "text"
                logger.info("Capture mode: TEXT")
            elif mode == "Tables":
                self.selected_content_mode = "table"
                logger.info("Capture mode: TABLE")
            
            # Show brief feedback
            self.status_label.setText(f"Mode: {self.selected_content_mode.title()}")
            self.status_label.setVisible(True)
            QTimer.singleShot(1500, lambda: self.status_label.setVisible(False))

        # Connect the signal
        self.mode_dropdown.currentIndexChanged.connect(_on_mode_changed)

        header_layout.addWidget(self.mode_dropdown)
        header_layout.addWidget(self.capture_btn)
        header_layout.addSpacing(6)
        header_layout.addWidget(self.menu_btn)

        # Add header to root
        root.addWidget(header_frame)
        root.addSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)       

        # Initialize hidden settings side panel
        self._init_settings_panel()

        # --- Preview Box (Zoomable) ---
        root.addWidget(self._section_label("Preview Image"))
        self.preview_widget = ZoomablePreviewWidget()
        self.preview_widget.setMinimumHeight(100)
        self.preview_widget.setMaximumHeight(400)

        # Wrap in resizable container
        saved_preview_height = LayoutManager.get_preview_height()
        self.preview_box = ResizableBox(
            self.preview_widget,
            min_height=100,
            max_height=400,
            save_key="preview_height"
        )
        self.preview_box.setObjectName("previewBox")
        self.preview_box.set_height(saved_preview_height)
        root.addWidget(self._with_card(self.preview_box))

        # --- Extracted Text ---
        self.extracted_frame, self.extracted_box, ex_copy_btn = self._textbox_with_copy()

        row = QHBoxLayout()
        row.addWidget(QLabel("Extracted Text"))
        row.addStretch()
        row.addWidget(ex_copy_btn)

        root.addLayout(row)
        root.addWidget(self.extracted_frame)

        self.extracted_box.setMinimumHeight(100)
        self.extracted_box.setMaximumHeight(500)

        # Make scrollable
        self.extracted_box.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.extracted_box.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Wrap in resizable container
        saved_extracted_height = LayoutManager.get_extracted_height()
        self.extracted_resizable = ResizableBox(
            self.extracted_frame,
            min_height=120,
            max_height=500,
            save_key="extracted_height"
        )
        self.extracted_resizable.set_height(saved_extracted_height)
        root.addWidget(self.extracted_resizable)

        # --- Translate Row ---
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setAlignment(Qt.AlignLeft)

        # --- Wrap in container frame (prevents layout reflow) ---
        translate_container = QFrame()
        translate_container.setFixedHeight(42)
        translate_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        translate_layout = QHBoxLayout(translate_container)
        translate_layout.setContentsMargins(0, 0, 0, 0)
        translate_layout.setSpacing(8)


        # --- Translate Button ---
        self.translate_btn = QPushButton("Translate Text")
        self.translate_btn.setObjectName("translateButton")
        self.translate_btn.setFixedHeight(36)
        self.translate_btn.setMinimumWidth(160)
        self.translate_btn.setMaximumWidth(160)
        self.translate_btn.setFocusPolicy(Qt.NoFocus)
        self.translate_btn.setIcon(QIcon(TRANSLATE_ICON_PATH))
        self.translate_btn.setIconSize(QSize(18, 18))
        self.translate_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.translate_btn.clicked.connect(self.run_translation)
        self.translate_btn.setStyleSheet("""
            QPushButton {
                text-align: center;
                padding: 6px 12px;
                qproperty-iconSize: 18px;
                border-radius: 6px;
            }
            QPushButton:hover {
                opacity: 0.95;
            }
            QPushButton:pressed {
                background-color: #2DBD6E;
                border: none;
            }
        """)

        # --- Translation Language Selector ---
        self.trans_lang = QComboBox()
        self.trans_lang.setFixedHeight(34)
        self.trans_lang.setMinimumWidth(150)
        self.trans_lang.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.trans_lang.addItems([
            "Hindi (hi)", "English (en)", "Marathi (mr)",
            "Gujarati (gu)", "Bengali (bn)", "Tamil (ta)",
            "Telugu (te)", "Urdu (ur)"
        ])
        self.trans_codes = {
            "Hindi (hi)": "hi", "English (en)": "en", "Marathi (mr)": "mr",
            "Gujarati (gu)": "gu", "Bengali (bn)": "bn", "Tamil (ta)": "ta",
            "Telugu (te)": "te", "Urdu (ur)": "ur"
        }

        # Add to container layout
        translate_layout.addWidget(self.translate_btn)
        translate_layout.addWidget(self.trans_lang)
        translate_layout.addStretch(1)

        # Add container to root layout (instead of direct row)
        root.addWidget(translate_container)
        root.addLayout(row)

       # --- Translated Text (hidden until Translate) ---

        # Label (stored for theme update, but NOT added to layout directly)
        self.translated_label = self._section_label("Translated Text")
        self.translated_label.setVisible(False)

        # Build textbox + copy button
        self.translated_frame, self.translated_box, tr_copy_btn = self._textbox_with_copy()

        # Row with label + copy button (this is the ONLY visible row)
        self.tr_row = QHBoxLayout()
        self.tr_label = QLabel("Translated Text")
        self.tr_label.setObjectName("sectionLabel")

        self.tr_row.addWidget(self.tr_label)
        self.tr_row.addStretch()
        self.tr_row.addWidget(tr_copy_btn)

        # Add row to layout
        root.addLayout(self.tr_row)

        # Hide entire section until translation
        self.tr_label.setVisible(False)
        tr_copy_btn.setVisible(False)
        self.translated_frame.setVisible(False)

        # Add the translated text frame
        root.addWidget(self.translated_frame)

        # Box sizing & scrollbars
        self.translated_box.setMinimumHeight(100)
        self.translated_box.setMaximumHeight(500)
        self.translated_box.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.translated_box.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Resizable container (initially hidden)
        saved_translated_height = LayoutManager.get_translated_height()
        self.translated_resizable = ResizableBox(
            self.translated_frame,
            min_height=120,
            max_height=500,
            save_key="translated_height"
        )
        self.translated_resizable.set_height(saved_translated_height)
        self.translated_resizable.setVisible(False)
        root.addWidget(self.translated_resizable)

        # Save reference for theme refresh
        self.copy_translated_btn = tr_copy_btn

        # Status label
        self.status_label = QLabel("")
        self.status_label.setObjectName("status")
        self.status_label.setVisible(False)
        root.addWidget(self.status_label)

        # --- Overlay + Lang Sync ---
        self.overlay = SelectionOverlay(None)
        self.overlay.parent_window = self
        self._restore_last_langs()
        self.trans_lang.currentIndexChanged.connect(self._save_langs)
        
    def _set_capture_mode(self, mode):
        self.capture_mode = mode
        self.status_label.setText(f"Mode: {mode.title()}")
        self.status_label.setVisible(True)
        QTimer.singleShot(1500, lambda: self.status_label.setVisible(False))

    def _init_window_zoom_controls(self):
        """Initialize window-level zoom controls."""
        # Create zoom controller
        self.window_zoom_controller = WindowZoomControllerV3(self)
        
        # Add zoom indicator label (top-right corner)
        self.window_zoom_label = QLabel("100%", self)
        self.window_zoom_label.setObjectName("windowZoomLabel")
        self.window_zoom_label.setStyleSheet("""
            QLabel#windowZoomLabel {
                background: rgba(0, 0, 0, 0.7);
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
            }
        """)
        self.window_zoom_label.setVisible(False)
        
        # Connect zoom change signal
        self.window_zoom_controller.zoomChanged.connect(self._on_window_zoom_changed)
        
        logger.info("Window zoom controls initialized")

    def _on_window_zoom_changed(self, zoom_level: float):
        """Handle window zoom level changes."""
        percentage = int(zoom_level * 100)
        self.window_zoom_label.setText(f"{percentage}%")
        
        # Show indicator temporarily
        self.window_zoom_label.setVisible(True)
        self.window_zoom_label.move(self.width() - self.window_zoom_label.width() - 20, 20)
        self.window_zoom_label.raise_()
        
        # Hide after 2 seconds
        QTimer.singleShot(2000, lambda: self.window_zoom_label.setVisible(False))
        
        # ---------- Settings Side Panel ----------
    def _init_settings_panel(self):
        """Create a hidden right-side settings drawer that matches the current theme."""
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QPushButton, QComboBox,
            QCheckBox, QListWidget, QHBoxLayout, QGraphicsDropShadowEffect
        )
        from PySide6.QtCore import QRect, QTimer
        from PySide6.QtGui import QColor
        from utils.autostart import (
            is_auto_start_enabled, enable_auto_start, disable_auto_start
        )

        # Create and style base panel
        self.settings_panel = QWidget(self)
        self.settings_panel.setObjectName("settingsPanel")
        self.settings_panel.setGeometry(self.width(), 0, 260, self.height())
        self.settings_panel.setFixedWidth(260)
        self.settings_panel.setVisible(False)

        # Dynamic palette based on main theme
        if self.current_theme == "dark":
            panel_bg = "#1E293B"
            border_color = "#334155"
            text_color = "#E2E8F0"
            button_bg = "#334155"
            button_hover = "#3B4E6A"
            entry_bg = "#0F172A"
            entry_border = "#475569"
        else:
            # 🌸 Lavender light settings panel
            panel_bg = "#F8F3FF"        # slightly lighter lavender
            border_color = "#D8C9F6"    # soft violet border
            text_color = "#1E1032"      # deep plum text
            button_bg = "#FFFFFF"       # clean white buttons
            button_hover = "#EDE3FE"    # lavender hover
            entry_bg = "#FFFFFF"        # consistent with cards
            entry_border = "#D8C9F6"    # lavender border

        self.settings_panel.setStyleSheet(f"""
            QWidget#settingsPanel {{
                background-color: {panel_bg};
                border-left: 1px solid {border_color};
            }}
            QLabel {{
                color: {text_color};
                font-weight: 600;
            }}
            QPushButton {{
                background-color: {button_bg};
                border: 1px solid {border_color};
                border-radius: 6px;
                color: {text_color};
                padding: 6px 10px;
            }}
            QPushButton:hover {{
                background-color: {button_hover};
            }}
            QLineEdit, QListWidget {{
                background-color: {entry_bg};
                border: 1px solid {entry_border};
                border-radius: 6px;
                padding: 4px 6px;
                color: {text_color};
            }}
            QComboBox, QCheckBox {{
                color: {text_color};
            }}
        """)

        # Layout setup
        layout = QVBoxLayout(self.settings_panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # --- Theme Toggle ---
        theme_toggle = ToggleSwitch(self, checked=(self.current_theme == "dark"))
        theme_label = QLabel("Dark Mode")
        theme_toggle.toggled.connect(lambda s: self._on_theme_toggled(s))
        row1 = QHBoxLayout()
        row1.addWidget(theme_label)
        row1.addStretch(1)
        row1.addWidget(theme_toggle)
        layout.addLayout(row1)

        # --- Autostart Toggle ---
        auto_toggle = ToggleSwitch(self, checked=is_auto_start_enabled())
        auto_label = QLabel("Autostart")
        auto_toggle.toggled.connect(lambda s: enable_auto_start() if s else disable_auto_start())
        row2 = QHBoxLayout()
        row2.addWidget(auto_label)
        row2.addStretch(1)
        row2.addWidget(auto_toggle)
        layout.addLayout(row2)

        # --- Gemini model selector ---
        layout.addWidget(QLabel("Gemini Model"))
        self.gemini_model_combo = QComboBox()
        self.gemini_model_combo.addItems([
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite"
        ])
        current_model = self.config.get("gemini_model", "gemini-2.5-flash-lite")
        if current_model not in [
            "gemini-2.5-flash-lite", "gemini-2.5-flash",
            "gemini-2.0-flash", "gemini-2.0-flash-lite"
        ]:
            current_model = "gemini-2.5-flash-lite"
        self.gemini_model_combo.setCurrentText(current_model)

        def on_model_changed(model_name):
            set_config_value("gemini_model", model_name)
            self.config["gemini_model"] = model_name
            save_config(self.config)
            self.status_label.setText(f"Model set to: {model_name}")
            self.status_label.setVisible(True)
            QTimer.singleShot(1500, lambda: self.status_label.setVisible(False))
            logger.info(f"Gemini model changed → {model_name}")

        self.gemini_model_combo.currentTextChanged.connect(on_model_changed)
        layout.addWidget(self.gemini_model_combo)

        # --- Gemini API Key Manager ---
        layout.addWidget(QLabel("Gemini API Keys"))
        self.api_key_list = QListWidget()
        keys = self.config.get("gemini_api_keys", [])
        self.api_key_list.addItems(keys)
        layout.addWidget(self.api_key_list)

        layout.addWidget(QLabel("Active API Key"))
        self.active_key_combo = QComboBox()
        self.active_key_combo.addItems(keys)
        current_key = self.config.get("gemini_api_key", "")
        if current_key in keys:
            self.active_key_combo.setCurrentText(current_key)
        self.active_key_combo.currentTextChanged.connect(self._on_active_key_changed)
        layout.addWidget(self.active_key_combo)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Key")
        rem_btn = QPushButton("Remove Key")
        add_btn.clicked.connect(self.add_api_key)
        rem_btn.clicked.connect(self.remove_api_key)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rem_btn)
        # --- ADD THIS SECTION (Reset Layout Button) ---
        layout.addWidget(QLabel(""))  # Spacer
        reset_layout_btn = QPushButton("Reset Layout to Defaults")
        reset_layout_btn.setToolTip("Reset window and box sizes to default values")
        reset_layout_btn.clicked.connect(self._reset_layout_sizes)
        layout.addWidget(reset_layout_btn)
        layout.addLayout(btn_row)
        
        # ------------------ SHORTCUT SETTINGS ------------------
        layout.addWidget(QLabel("Shortcut Keys"))

        from PySide6.QtWidgets import QLineEdit

        # Text Capture Shortcut
        self.shortcut_text_box = QLineEdit()
        self.shortcut_text_box.setPlaceholderText("Press keys…")
        self.shortcut_text_box.setReadOnly(True)
        self.shortcut_text_box.setText(self.config.get("shortcut_text", "alt+t+1"))
        layout.addWidget(QLabel("Text Capture"))
        layout.addWidget(self.shortcut_text_box)

        # Table Capture Shortcut
        self.shortcut_table_box = QLineEdit()
        self.shortcut_table_box.setPlaceholderText("Press keys…")
        self.shortcut_table_box.setReadOnly(True)
        self.shortcut_table_box.setText(self.config.get("shortcut_table", "alt+t+2"))
        layout.addWidget(QLabel("Table Capture"))
        layout.addWidget(self.shortcut_table_box)

        # Popup Shortcut
        self.shortcut_popup_box = QLineEdit()
        self.shortcut_popup_box.setPlaceholderText("Press keys…")
        self.shortcut_popup_box.setReadOnly(True)
        self.shortcut_popup_box.setText(self.config.get("shortcut_popup", "alt+t+p"))
        layout.addWidget(QLabel("Mode Popup"))
        layout.addWidget(self.shortcut_popup_box)

        self.shortcut_text_box.mousePressEvent = lambda e: self._begin_record_shortcut(self.shortcut_text_box, "shortcut_text")
        self.shortcut_table_box.mousePressEvent = lambda e: self._begin_record_shortcut(self.shortcut_table_box, "shortcut_table")
        self.shortcut_popup_box.mousePressEvent = lambda e: self._begin_record_shortcut(self.shortcut_popup_box, "shortcut_popup")

    def _on_active_key_changed(self, key):
        """Update the currently active Gemini API key."""
        if key.strip():
            self.config["gemini_api_key"] = key.strip()
            save_config(self.config)
            logger.info(f"Active Gemini API key changed to {key[:8]}...")
        
    def _ensure_overlay_widget(self):
        """Create or reuse a blurred translucent overlay behind the settings panel (Mica-style)."""
        from PySide6.QtWidgets import QWidget, QGraphicsBlurEffect
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor

        # Reuse overlay if it exists
        if hasattr(self, "_overlay_widget"):
            # Update its tint on theme change
            if self.current_theme == "dark":
                self._overlay_widget.setStyleSheet("background-color: rgba(15, 23, 42, 80);")  # smoky dark tint
            else:
                self._overlay_widget.setStyleSheet("background-color: rgba(243, 246, 249, 130);")  # bright frost tint
            return

        # --- Create new overlay ---
        self._overlay_widget = QWidget(self)
        self._overlay_widget.setObjectName("overlayWidget")
        self._overlay_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._overlay_widget.hide()

        # --- Apply initial theme tint ---
        if self.current_theme == "dark":
            tint_color = "rgba(15, 23, 42, 80)"     # subtle dark fog
        else:
            tint_color = "rgba(243, 246, 249, 130)"  # light frosted glass

        self._overlay_widget.setStyleSheet(f"background-color: {tint_color};")

        # --- Add smooth blur (Frosted glass look) ---
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(18 if self.current_theme == "light" else 12)
        self._overlay_widget.setGraphicsEffect(blur)

        # --- Click outside panel closes it ---
        def _on_click(event):
            self.toggle_settings_panel(force_close=True)
        self._overlay_widget.mousePressEvent = _on_click
        
    def _update_settings_panel_theme(self):
        """Dynamically update side panel colors to match current theme."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from gui.animations import make_anim, ANIM_SLOW, EASE_SOFT

        if not hasattr(self, "settings_panel"):
            return

        # Smooth fade-in animation
        fade = QGraphicsOpacityEffect(self.settings_panel)
        self.settings_panel.setGraphicsEffect(fade)
        fade.setOpacity(0.0)
        fade_anim = make_anim(fade, b"opacity", 0.0, 1.0, dur=ANIM_SLOW, curve=EASE_SOFT)
        fade_anim.start()
        self.fade_anim = fade_anim

        # 🎨 Enhanced theme-specific colors
        if self.current_theme == "dark":
            panel_bg = "#1E293B"
            border_color = "#334155"
            text_color = "#F1F5F9"
            accent = "#3B82F6"
            combo_bg = "#0F172A"
            combo_popup = "#1E293B"
            combo_hover = "#334155"
            list_bg = "#0F172A"
            button_bg = "transparent"
            button_hover = "rgba(59, 130, 246, 0.1)"
        else:
            # Balanced light theme - less lavender
            panel_bg = "#FFFFFF"
            border_color = "#E5E7EB"
            text_color = "#111827"
            accent = "#7C3AED"
            combo_bg = "#F9FAFB"
            combo_popup = "#FFFFFF"
            combo_hover = "#F3F4F6"
            list_bg = "#F9FAFB"
            button_bg = "transparent"
            button_hover = "rgba(124, 58, 237, 0.08)"

        # Apply unified stylesheet
        self.settings_panel.setStyleSheet(f"""
            QWidget#settingsPanel {{
                background-color: {panel_bg};
                border-left: 1px solid {border_color};
            }}
            QLabel {{
                color: {text_color};
                font-weight: 500;
                background: transparent;
            }}
            QPushButton {{
                background-color: {button_bg};
                border: 1px solid {border_color};
                border-radius: 6px;
                color: {text_color};
                padding: 6px 10px;
            }}
            QPushButton:hover {{
                background-color: {button_hover};
                border-color: {accent};
            }}
            QComboBox {{
                background-color: {combo_bg};
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 4px 6px;
                color: {text_color};
            }}
            QComboBox:hover {{
                border-color: {accent};
            }}
            QComboBox QAbstractItemView {{
                background-color: {combo_popup};
                border: 1px solid {border_color};
                selection-background-color: {combo_hover};
                selection-color: {text_color};
            }}
            QListWidget {{
                background-color: {list_bg};
                border: 1px solid {border_color};
                border-radius: 6px;
                color: {text_color};
            }}
            QListWidget::item:selected {{
                background-color: {accent};
                color: white;
            }}
            QLineEdit {{
                background-color: {combo_bg};
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 4px 6px;
                color: {text_color};
            }}
            QLineEdit:focus {{
                border-color: {accent};
            }}
            QCheckBox {{
                color: {text_color};
            }}
        """)
    
    def toggle_settings_panel(self, force_close: bool = False):
        """Slide in/out the settings panel with blurred dim overlay and smooth fade."""
        from PySide6.QtCore import QRect, QTimer, Qt
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from gui.animations import make_anim, ANIM_SLOW, EASE_STD

        self._ensure_overlay_widget()
        panel_width = 260

        if not hasattr(self, "settings_panel"):
            self._init_settings_panel()

        # ============= CLOSE PANEL =============
        if force_close or self.settings_panel.isVisible():
            # --- Fade out overlay smoothly ---
            if self._overlay_widget.isVisible():
                if not isinstance(self._overlay_widget.graphicsEffect(), QGraphicsOpacityEffect):
                    overlay_fade = QGraphicsOpacityEffect(self._overlay_widget)
                    self._overlay_widget.setGraphicsEffect(overlay_fade)
                else:
                    overlay_fade = self._overlay_widget.graphicsEffect()

                fade_anim = make_anim(
                    overlay_fade,
                    b"opacity",
                    overlay_fade.opacity() if overlay_fade.opacity() else 1.0,
                    0.0,
                    dur=ANIM_SLOW,
                    curve=EASE_STD
                )
                fade_anim.start()

                def _hide_overlay():
                    self._overlay_widget.hide()
                    self._overlay_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    overlay_fade.setOpacity(1.0)  # reset for next open

                fade_anim.finished.connect(_hide_overlay)
                self.fade_anim = fade_anim

            # --- Slide out panel ---
            start_rect = QRect(self.width() - panel_width, 0, panel_width, self.height())
            end_rect = QRect(self.width(), 0, panel_width, self.height())
            self.anim = make_anim(self.settings_panel, b"geometry", start_rect, end_rect, dur=ANIM_SLOW, curve=EASE_STD)
            self.anim.finished.connect(lambda: self.settings_panel.setVisible(False))
            self.anim.start()

        # ============= OPEN PANEL =============
        else:
            # --- Prepare overlay ---
            self._overlay_widget.setGeometry(self.rect())
            self._overlay_widget.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self._overlay_widget.raise_()
            self._overlay_widget.show()

            # --- Smooth fade-in overlay ---
            overlay_fade = QGraphicsOpacityEffect(self._overlay_widget)
            self._overlay_widget.setGraphicsEffect(overlay_fade)
            overlay_fade.setOpacity(0.0)

            fade_anim = make_anim(overlay_fade, b"opacity", 0.0, 1.0, dur=ANIM_SLOW, curve=EASE_STD)
            fade_anim.start()
            self.fade_anim = fade_anim

            # --- Slide in panel (delayed until styles fully applied) ---
            def _show_panel_smooth():
                self._update_settings_panel_theme()
                self.settings_panel.setVisible(True)
                self.settings_panel.raise_()
                start_rect = QRect(self.width(), 0, panel_width, self.height())
                end_rect = QRect(self.width() - panel_width, 0, panel_width, self.height())
                self.anim = make_anim(self.settings_panel, b"geometry", start_rect, end_rect, dur=ANIM_SLOW, curve=EASE_STD)
                self.anim.start()

            QTimer.singleShot(80, _show_panel_smooth)
    
    def add_api_key(self):
        """Add a new Gemini API key via GUI only."""
        from PySide6.QtWidgets import QInputDialog
        key, ok = QInputDialog.getText(self, "Add Gemini API Key", "Enter new API key:")
        if ok and key.strip():
            key = key.strip()
            current_keys = self.config.get("gemini_api_keys", [])
            if key not in current_keys:
                current_keys.append(key)
                self.config["gemini_api_keys"] = current_keys
                self.api_key_list.addItem(key)
                self.active_key_combo.addItem(key)
                save_config(self.config)
                logger.info("Added new Gemini API key.")
            else:
                logger.info("Duplicate Gemini key ignored.")

    def remove_api_key(self):
        """Remove selected Gemini API key."""
        for item in self.api_key_list.selectedItems():
            key = item.text()
            self.api_key_list.takeItem(self.api_key_list.row(item))
            if key in self.config.get("gemini_api_keys", []):
                self.config["gemini_api_keys"].remove(key)
            if self.active_key_combo.currentText() == key:
                self.config["gemini_api_key"] = ""
                self.active_key_combo.setCurrentIndex(-1)
            save_config(self.config)
            logger.info("Removed Gemini API key.")


        
    # ---------- unified text card ---------
    def _textbox_with_copy(self):
        """Create textbox with enhanced table-aware copy button."""
        frame = QFrame()
        frame.setObjectName("textCard")
        layout = QVBoxLayout(frame)
        layout.setSpacing(0)

        box = QTextEdit()
        box.setObjectName("textEditBox")
        box.setStyleSheet("background: transparent; border: none; padding: 4px;")
        box.setContextMenuPolicy(Qt.CustomContextMenu)
        box.customContextMenuRequested.connect(lambda _: None)
        layout.addWidget(box)

        # Copy button
        copy_btn = QPushButton(frame)
        copy_btn.setFixedHeight(22)
        copy_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setToolTip("Copy to clipboard (with table grid borders)")

        icon_path = COPY_ICON_DARK if self.current_theme == "dark" else COPY_ICON_LIGHT
        copy_btn.setIcon(QIcon(os.path.abspath(icon_path)))
        copy_btn.setIconSize(QSize(14, 14))
        copy_btn.setText(" Copy")

        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {"rgba(0,0,0,0.04)" if self.current_theme == "light" else "rgba(255,255,255,0.06)"};
                border: none;
                border-radius: 6px;
                color: {"#0F172A" if self.current_theme == "light" else "#E2E8F0"};
                font-weight: 500;
                font-size: 10.5px;
                padding: 2px 5px;
                qproperty-iconSize: 14px;
            }}
            QPushButton:hover {{
                background-color: rgba(62,156,246,0.15);
            }}
        """)

        # ❌ REMOVED absolute positioning

        # ENHANCED COPY ACTION WITH TABLE GRID SUPPORT
        def copy_action():
            from PySide6.QtCore import QMimeData
            from core.postprocess import prepare_content_for_clipboard, extract_text_and_tables
            
            mime = QMimeData()
            
            # Get current content
            html = getattr(self, "_last_full_html", box.toHtml().strip())
            text = box.toPlainText().strip()
            
            if not text:
                logger.info("No content to copy")
                return
            
            # Check if we have tables
            if '<table' in html.lower():
                enhanced_html = prepare_content_for_clipboard(html)
                structure = extract_text_and_tables(html)
                logger.info(f"Copying content with {len(structure['tables'])} table(s) - Table Grid format")
                
                mime.setHtml(enhanced_html)
                mime.setText(text)
                
                logger.info("✅ Table copied with Table Grid style (white background, dark borders)")
                
            else:
                from core.postprocess import prepare_math_for_clipboard
                html = prepare_math_for_clipboard(html)
                html = html.replace("&lt;math", "<math")
                html = html.replace("&lt;/math&gt;", "</math>")
                html = html.replace("&lt;", "<").replace("&gt;", ">")
                
                mime.setHtml(html)
                mime.setText(text)
            
            QApplication.clipboard().setMimeData(mime)
            
            pos_global = copy_btn.mapToGlobal(copy_btn.rect().center())
            pos_local = self.mapFromGlobal(pos_global)
            self._show_copied(pos_local)
            
            logger.info("✅ Content copied to clipboard with grid formatting")

        copy_btn.clicked.connect(copy_action)

        # Keep references
        if not hasattr(self, "copy_extracted_btn"):
            self.copy_extracted_btn = copy_btn
        elif not hasattr(self, "copy_translated_btn"):
            self.copy_translated_btn = copy_btn

        # NEW → return button separately
        return frame, box, copy_btn

    # ADD this helper method to the PopupWindow class
    def _html_to_rtf(self, html: str) -> str:
        """
        Convert HTML to RTF format for better Word compatibility.
        This is a simplified converter for tables.
        """
        from bs4 import BeautifulSoup
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # RTF header
            rtf = r"{\rtf1\ansi\deff0"
            rtf += r"{\fonttbl{\f0\fnil\fcharset0 Calibri;}}"
            rtf += r"\viewkind4\uc1\pard\f0\fs22 "
            
            # Process tables
            for table in soup.find_all('table'):
                rtf += r"\par\trowd\trgaph70"
                
                # Get column count from first row
                first_row = table.find('tr')
                if first_row:
                    col_count = len(first_row.find_all(['td', 'th']))
                    
                    # Define cell widths
                    cell_width = 2000  # Twips
                    for i in range(col_count):
                        rtf += f"\\cellx{(i+1) * cell_width}"
                    
                    # Process rows
                    for row in table.find_all('tr'):
                        for cell in row.find_all(['td', 'th']):
                            cell_text = cell.get_text(strip=True)
                            rtf += f" {cell_text}\\cell"
                        rtf += "\\row\\trowd\\trgaph70"
                        for i in range(col_count):
                            rtf += f"\\cellx{(i+1) * cell_width}"
            
            # Process text outside tables
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                if text:
                    rtf += f"\\par {text}"
            
            rtf += r"\par}"
            
            return rtf
            
        except Exception as e:
            logger.warning(f"RTF conversion failed: {e}")
            return ""
    
    # ADD this helper method to the PopupWindow class
    def _html_to_rtf(self, html: str) -> str:
        """
        Convert HTML to RTF format for better Word compatibility.
        This is a simplified converter for tables.
        """
        from bs4 import BeautifulSoup
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # RTF header
            rtf = r"{\rtf1\ansi\deff0"
            rtf += r"{\fonttbl{\f0\fnil\fcharset0 Calibri;}}"
            rtf += r"\viewkind4\uc1\pard\f0\fs22 "
            
            # Process tables
            for table in soup.find_all('table'):
                rtf += r"\par\trowd\trgaph70"
                
                # Get column count from first row
                first_row = table.find('tr')
                if first_row:
                    col_count = len(first_row.find_all(['td', 'th']))
                    
                    # Define cell widths
                    cell_width = 2000  # Twips
                    for i in range(col_count):
                        rtf += f"\\cellx{(i+1) * cell_width}"
                    
                    # Process rows
                    for row in table.find_all('tr'):
                        for cell in row.find_all(['td', 'th']):
                            cell_text = cell.get_text(strip=True)
                            rtf += f" {cell_text}\\cell"
                        rtf += "\\row\\trowd\\trgaph70"
                        for i in range(col_count):
                            rtf += f"\\cellx{(i+1) * cell_width}"
            
            # Process text outside tables
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                if text:
                    rtf += f"\\par {text}"
            
            rtf += r"\par}"
            
            return rtf
            
        except Exception as e:
            logger.warning(f"RTF conversion failed: {e}")
            return ""
        
    def copy_action():
        from PySide6.QtCore import QMimeData
        from core.postprocess import prepare_content_for_clipboard, extract_text_and_tables
        
        mime = QMimeData()
        
        # Get ORIGINAL HTML (without theme styling)
        original_html = getattr(self, "_last_full_html", "")
        
        # Fallback to box HTML if no stored version
        if not original_html:
            original_html = box.toHtml().strip()
        
        text = box.toPlainText().strip()
        
        if not text:
            logger.info("No content to copy")
            return
        
        # Check if we have tables
        if '<table' in original_html.lower():
            # Convert to Table Grid format (pure white, dark borders)
            # This REMOVES all theme colors and applies Word-compatible styling
            enhanced_html = prepare_content_for_clipboard(original_html)
            
            # Extract structure for logging
            structure = extract_text_and_tables(original_html)
            logger.info(f"📋 Copying {len(structure['tables'])} table(s) in Table Grid format")
            
            # Set clipboard data
            mime.setHtml(enhanced_html)
            mime.setText(text)
            
            logger.info("✅ Table copied: White background, dark borders, no theme colors")
            
        else:
            # Plain text or text with math
            from core.postprocess import prepare_math_for_clipboard
            html = prepare_math_for_clipboard(original_html)
            
            html = html.replace("&lt;math", "<math")
            html = html.replace("&lt;/math&gt;", "</math>")
            html = html.replace("&lt;", "<").replace("&gt;", ">")
            
            mime.setHtml(html)
            mime.setText(text)
        
        # Copy to clipboard
        QApplication.clipboard().setMimeData(mime)
        
        # Visual feedback
        pos_global = copy_btn.mapToGlobal(copy_btn.rect().center())
        pos_local = self.mapFromGlobal(pos_global)
        self._show_copied(pos_local)

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("sectionLabel")
        return lbl

    def _section_row(self, text, copy_btn):
        row = QHBoxLayout()
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        
        row.addWidget(label)
        row.addStretch()
        row.addWidget(copy_btn)

        return row

    def _with_card(self, widget):
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(widget)
        frame.setObjectName("textCard")
        return frame
    
    def _ensure_fade_overlay(self):
        """Create a reusable overlay for theme transition."""
        if hasattr(self, "_fade_overlay"):
            return
        from PySide6.QtWidgets import QWidget
        self._fade_overlay = QWidget(self)
        self._fade_overlay.setObjectName("fadeOverlay")
        self._fade_overlay.setStyleSheet("background-color: black;")
        self._fade_overlay.setAutoFillBackground(True)
        self._fade_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._fade_overlay.hide()
        
    def _animate_icon_hover(self, button, entering: bool):
        """Subtle hover animation for buttons (opacity fade)."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        if not hasattr(button, "_opacity_effect"):
            effect = QGraphicsOpacityEffect(button)
            button.setGraphicsEffect(effect)
            button._opacity_effect = effect
        else:
            effect = button._opacity_effect

        anim = make_anim(
            effect,
            b"opacity",
            1.0 if not entering else 0.8,
            0.8 if not entering else 1.0,
            dur=ANIM_NORMAL,
            curve=EASE_SOFT
        )
        anim.start()
        button._hover_anim = anim

    # ---------- theme ----------
    def _apply_theme(self, theme: str):
        from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer
        from PySide6.QtGui import QColor, QPalette, QIcon
        import os

        # ========================================
        # 🎨 ENHANCED COLOR PALETTES
        # ========================================
        
        if theme == "dark":
            # 🌙 Enhanced Dark Theme - Modern depth and contrast
            bg = "#12182C"              
            darker = "#060912"         
            accent = "#3B82F6"          
            text = "#F1F5F9"            
            muted = "#94A3B8"           
            primary_btn = "#3E9CF6"      
            primary_hover = "#60ADF9"    
            primary_pressed = "#2E8AE0"  
            translate_btn = "#3E9CF6"    
            translate_hover = "#60ADF9"  
            translate_pressed = "#2E8AE0" 
            box_bg = "#1E293B"           
            box_border = "#334155"       
            copy_icon_path = COPY_ICON_LIGHT
            copy_text_color = "#F1F5F9"
            fade_color = "#000000"
            
        else:
            # ☀️ Refined Light Theme - Subtle lavender with neutral balance
            bg = "#EFE6FE"             
            darker = "#E5E7EB"        
            accent = "#7C3AED"         
            text = "#111827"           
            muted = "#6B7280"          
            primary_btn = "#7C3AED"     
            primary_hover = "#6D28D9"   
            primary_pressed = "#5B21B6" 
            translate_btn = "#7C3AED"   
            translate_hover = "#6D28D9" 
            translate_pressed = "#5B21B6"
            box_bg = "#F7F4FF"          
            box_border = "#DCD2F8"      
            copy_icon_path = COPY_ICON_DARK
            copy_text_color = "#111827"
            fade_color = "#F9FAFB"

        # --- Save theme state ---
        self.current_theme = theme
        self.config["theme"] = theme
        save_config(self.config)

        # ✅ Update loader GIFs for new theme
        if hasattr(self, 'loader_extracted'):
            self._update_loader_theme()  # Critical: refresh loader visuals

        # --- Palette sync for full window ---
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(bg))
        palette.setColor(QPalette.Base, QColor(bg))
        palette.setColor(QPalette.WindowText, QColor(text))
        self.setPalette(palette)

        # --- Create or update overlay ---
        if not hasattr(self, "_fade_overlay"):
            self._fade_overlay = QWidget(self)
            self._fade_overlay.setAutoFillBackground(True)
            self._fade_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._fade_overlay.hide()

        self._fade_overlay.setGeometry(self.rect())
        self._fade_overlay.setStyleSheet(f"background-color: {fade_color};")
        self._fade_overlay.show()
        self._fade_overlay.raise_()

        # --- Overlay opacity effect ---
        fade_effect = QGraphicsOpacityEffect(self._fade_overlay)
        self._fade_overlay.setGraphicsEffect(fade_effect)

        # --- Smooth fade animation ---
        fade_anim = QPropertyAnimation(fade_effect, b"opacity")
        fade_anim.setDuration(650)                     # smoother, longer fade
        fade_anim.setEasingCurve(QEasingCurve.InOutQuad)  # softer easing
        fade_anim.setStartValue(1.0)
        fade_anim.setEndValue(0.0)

        # --- Apply enhanced stylesheet ---
        self.setUpdatesEnabled(False)
        # --- Header color ---
        if theme == "dark":
            header_bg = "#1E293B"    # subtle slate-blue for dark mode
            header_border = "#334155"
        else:
            header_bg = "#F5F3FF"    # soft lavender tint for light mode
            header_border = "#E0D7FB"
        self.setStyleSheet(f"""
            QWidget {{
                background: {bg};
                color: {text};
                font-family: "Segoe UI", "Nirmala UI";
                font-size: 11.5px;
            }}
            QPushButton {{
                background: {box_bg};
                border: 1px solid {box_border};
                border-radius: 6px;
                color: {text};
                padding: 5px 10px;
            }}
            QPushButton:hover {{
                background: {darker if theme == "dark" else "#F3F4F6"};
                border-color: {accent};
            }}
            QPushButton#captureButton {{
                background: {primary_btn};
                color: white;
                border: none;
                font-weight: 600;
                padding: 6px 12px;
                border-radius: 6px;
            }}
            QPushButton#captureButton:hover {{
                background: {primary_hover};
            }}
            QPushButton#captureButton:pressed {{
                background: {primary_pressed};
            }}
            QPushButton#translateButton {{
                background: {translate_btn};
                color: white;
                border: none;
                font-weight: 600;
                padding: 6px 12px;
                border-radius: 6px;
            }}
            QPushButton#translateButton:hover {{
                background: {translate_hover};
            }}
            QPushButton#translateButton:pressed {{
                background: {translate_pressed};
            }}
            QComboBox {{
                background: {box_bg};
                border: 1px solid {box_border};
                border-radius: 6px;
                padding: 4px 8px;
                color: {text};
            }}
            QComboBox:hover {{
                border-color: {accent};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 8px;
            }}
            QTextEdit {{
                background: transparent;
                border: none;
                padding: 6px;
                color: {text};
            }}
            QFrame#textCard {{
                background: {box_bg};
                border: 1px solid {box_border};
                border-radius: 6px;
            }}
            QWidget#headerBar {{
                background: {header_bg};
                border-bottom: 1px solid {header_border};
                padding: 6px 10px;
                border-top-left-radius: 10px;      /* ✅ rounded top-left */
                border-top-right-radius: 10px;     /* ✅ rounded top-right */
            }}
            QProgressBar {{
                background: {darker};
                border-radius: 4px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {accent};
                border-radius: 4px;
            }}
            QLabel#sectionLabel {{
                color: {muted};
                font-weight: 600;
                margin-top: 6px;
            }}
            QLabel#status {{
                color: {muted};
            }}
            QMenu {{
                background: {"#1E293B" if theme == "dark" else "#FFFFFF"};
                border: 1px solid {box_border};
                color: {text};
                selection-background-color: {accent};
                selection-color: white;
                padding: 6px;
                border-radius: 6px;
            }}
            QMenu::separator {{
                height: 1px;
                background: {box_border};
                margin: 4px 8px;
            }}
            QMenu::item {{
                padding: 6px 12px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background: {accent};
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: {(
                    "#FFFFFF" if theme == "light" else "#1A2235"
                )};  /* matches main bg tone, slightly lighter */
                width: 7px;
                border-radius: 4px;
                margin: 0px;
            }}

            QScrollBar::handle:vertical {{
                background: {(
                    "#D8C9F6" if theme == "light" else "#4A5B77"
                )};  /* lightened tone of accent/darker for both themes */
                border-radius: 4px;
                min-height: 24px;
            }}

            QScrollBar::handle:vertical:hover {{
                background: {(
                    "#BFAAF2" if theme == "light" else "#5A6C8D"
                )};  /* slightly brighter on hover */
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        if theme == "light":
            self.setStyleSheet(self.styleSheet() + """
                QFrame#previewBox {
                    background: #F7F4FF;
                }
            """)
        self.setUpdatesEnabled(True)
        self.repaint()
        
        if hasattr(self, "preview_widget"):
            try:
                if theme == "light":
                    # Light theme → full white preview background
                    self.preview_widget.view.setStyleSheet("background: #F7F4FF; border: none;")
                    self.preview_box.setStyleSheet("background: transparent; border: none;")
                else:
                    # Dark theme → restore default dark tone
                    self.preview_widget.view.setStyleSheet("background: #1E293B; border: none;")
                    self.preview_box.setStyleSheet("background: transparent; border: none;")

                # Ensure zoom control bar remains readable in both themes
                for child in self.preview_widget.findChildren(QWidget):
                    if child.objectName() == "zoomControlBar":
                        if theme == "light":
                            child.setStyleSheet("""
                                QWidget#zoomControlBar {
                                    background: rgba(255,255,255,0.08);
                                    border: 1px solid rgba(0,0,0,0.1);
                                    border-radius: 4px;
                                }
                            """)
                        else:
                            child.setStyleSheet("""
                                QWidget#zoomControlBar {
                                    background: rgba(255,255,255,0.06);
                                    border: 1px solid rgba(255,255,255,0.1);
                                    border-radius: 4px;
                                }
                            """)
            except Exception as e:
                print("⚠️ Preview background update failed:", e)
        
        # --- Preserve user geometry during theme switch ---
        prev_size = self.size()
        self.setMinimumSize(440, 560)  # keep min constraint only
        self.resize(prev_size)


        # Update zoomable preview theme
        if hasattr(self, 'preview_widget'):
            self.preview_widget._apply_control_styles()
            self.preview_widget.update_icons_for_theme(theme)
        
        handle_color = "#94A3B8" if theme == "dark" else "#6B7280"
        handle_hover = "#CBD5E1" if theme == "dark" else "#4B5563"
        
        # Apply to all resize handles
        for widget in self.findChildren(ResizeHandle):
            widget.setStyleSheet(f"""
                ResizeHandle {{
                    background: transparent;
                }}
                ResizeHandle:hover {{
                    background: {handle_hover}20;
                }}
            """)
        self._apply_theme_to_text_boxes()

        # --- Cleanup after fade ---
        def cleanup_fade():
            self._fade_overlay.hide()
            fade_effect.deleteLater()
            
        if hasattr(self, "_last_user_size"):
            self.resize(self._last_user_size)

        fade_anim.finished.connect(cleanup_fade)
        fade_anim.start()
        self._fade_anim = fade_anim

        # --- Copy icon + text update ---
        def update_copy_button(button):
            if not button:
                return
            eff = QGraphicsOpacityEffect(button)
            button.setGraphicsEffect(eff)
            fade_out = QPropertyAnimation(eff, b"opacity")
            fade_out.setDuration(200)
            fade_out.setStartValue(1.0)
            fade_out.setEndValue(0.0)
            fade_out.setEasingCurve(QEasingCurve.InOutCubic)

            def apply_new_icon():
                button.setIcon(QIcon(os.path.abspath(copy_icon_path)))
                button.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {"rgba(0,0,0,0.04)" if theme == "light" else "rgba(255,255,255,0.06)"};
                        border: none;
                        border-radius: 6px;
                        color: {copy_text_color};
                        font-weight: 500;
                        font-size: 10.5px;
                        padding: 2px 6px;
                        qproperty-iconSize: 14px;
                    }}
                    QPushButton:hover {{
                        background-color: {("rgba(124,58,237,0.10)" if theme == "light" else "rgba(59,130,246,0.15)")};
                    }}
                """)
                fade_in = QPropertyAnimation(eff, b"opacity")
                fade_in.setDuration(220)
                fade_in.setStartValue(0.0)
                fade_in.setEndValue(1.0)
                fade_in.setEasingCurve(QEasingCurve.OutCubic)
                fade_in.start()
                button._fade_in = fade_in

            fade_out.finished.connect(apply_new_icon)
            fade_out.start()
            button._fade_out = fade_out

        # Apply to copy buttons
        QTimer.singleShot(150, lambda: (
            hasattr(self, "copy_extracted_btn") and update_copy_button(self.copy_extracted_btn)
        ))
        QTimer.singleShot(180, lambda: (
            hasattr(self, "copy_translated_btn") and update_copy_button(self.copy_translated_btn)
        ))

        # --- Bounce animation ---
        def add_bounce(button):
            if not button:
                return
            anim = QPropertyAnimation(button, b"geometry")
            rect = button.geometry()
            anim.setDuration(160)
            anim.setEasingCurve(QEasingCurve.OutBack)
            anim.setStartValue(rect)
            anim.setKeyValueAt(0.5, rect.adjusted(-1, -1, 1, 1))
            anim.setEndValue(rect)
            anim.start()
            button._bounce_anim = anim

        for name in ("copy_extracted_btn", "copy_translated_btn", "capture_btn", "translate_btn"):
            btn = getattr(self, name, None)
            if btn and not hasattr(btn, "_bounce_connected"):
                btn.clicked.connect(lambda _, b=btn: add_bounce(b))
                btn._bounce_connected = True

                # --- Update header icons dynamically based on theme ---
        dark_camera_icon = os.path.join(BASE_DIR, "..", "assets", "icons", "capture_light.png")
        light_camera_icon = os.path.join(BASE_DIR, "..", "assets", "icons", "capture_dark.png")
        dark_menu_icon = os.path.join(BASE_DIR, "..", "assets", "icons", "menu_light.png")
        light_menu_icon = os.path.join(BASE_DIR, "..", "assets", "icons", "menu_dark.png")

        # Apply the appropriate icons
        if hasattr(self, "capture_btn") and hasattr(self, "menu_btn"):
            if theme == "dark":
                self.capture_btn.setIcon(QIcon(dark_camera_icon))
                self.menu_btn.setIcon(QIcon(dark_menu_icon))
            else:
                self.capture_btn.setIcon(QIcon(light_camera_icon))
                self.menu_btn.setIcon(QIcon(light_menu_icon))

            self.capture_btn.setIconSize(QSize(20, 20))
            self.menu_btn.setIconSize(QSize(22, 22))

        # Re-render extracted HTML so colors update with theme
        if hasattr(self, "_last_full_html") and self._last_full_html:
            self.extracted_box.setHtml(self._apply_content_styling(self._last_full_html))

        # ===========================
        # 🎨 Auto theme for Mode Dropdown
        # ===========================
        if hasattr(self, "mode_dropdown"):

            if theme == "dark":
                dd_bg = "#1E293B"
                dd_text = "#E2E8F0"
                dd_border = "#334155"
                dd_hover = "#3B82F6"
                popup_bg = "#0F172A"
                popup_sel = "#3B82F6"
            else:
                dd_bg = "#FFFFFF"
                dd_text = "#1E1032"
                dd_border = "#D8C9F6"
                dd_hover = "#7C3AED"
                popup_bg = "#FFFFFF"
                popup_sel = "#EDE3FE"

            self.mode_dropdown.setStyleSheet(f"""
                QComboBox {{
                    padding: 4px 10px;
                    border-radius: 6px;
                    background-color: {dd_bg};
                    color: {dd_text};
                    border: 1px solid {dd_border};
                }}
                QComboBox:hover {{
                    border-color: {dd_hover};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 20px;
                    padding-right: 6px;
                }}
                QComboBox QAbstractItemView {{
                    background-color: {popup_bg};
                    color: {dd_text};
                    selection-background-color: {popup_sel};
                    selection-color: {dd_text};
                    border: 1px solid {dd_border};
                    padding: 4px;
                }}
            """)

        # --- Theme state ---
        self.copy_icon_opacity = 0.6 if theme == "dark" else 0.75
    
    def _on_theme_toggled(self, is_dark: bool):
        theme = "dark" if is_dark else "light"
        self._apply_theme(theme)

        # ✅ Reapply styling for side panel if it exists
        if hasattr(self, "settings_panel"):
            self._update_settings_panel_theme()
        # ✅ Update overlay tint dynamically when theme changes
        if hasattr(self, "_overlay_widget"):
            self._ensure_overlay_widget()
        # Update toggle accent dynamically
        for child in self.findChildren(ToggleSwitch):
            if self.current_theme == "dark":
                child._accent = "#3E9CF6"
            else:
                child._accent = "#0078D4"
            child.update()

    # ---------- OCR flow ----------
    def start_capture(self):
        """Show overlay with integrated mode dropdown."""
        self.hide()
        if self.shortcut_override_mode:
            # Shortcuts override overlay mode completely
            mode = self.shortcut_override_mode
            self.overlay.selected_mode = mode
            self.overlay.mode_dropdown.setCurrentText("Text" if mode=="text" else "Table")
            self.overlay.control_bar.hide()       # ❗ hide UI bar when shortcut is used
        else:
            # Normal behavior — show overlay + dropdown
            self.overlay.selected_mode = self.selected_content_mode
            self.overlay.control_bar.show()

        self.overlay.showFullDesktop()

        
        logger.info("Mode selector shown - waiting for user choice")

    # Replace the on_selection_made method in popup.py with this DEBUG version:

    def on_selection_made(self, rect):
        """Handle selection from overlay."""
        self.shortcut_override_mode = None
        print("\n" + "=" * 80)
        print("OVERLAY SELECTION RECEIVED")
        print("=" * 80)
        print(f"QRect object: {rect}")
        print(f"  x={rect.x()}, y={rect.y()}")
        print(f"  width={rect.width()}, height={rect.height()}")
        
        # ✅ GET MODE FROM OVERLAY (not from separate popup)
        if hasattr(self.overlay, 'selected_mode'):
            self.selected_content_mode = self.overlay.selected_mode
            logger.info(f"Using mode from overlay: {self.selected_content_mode}")
        
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.screenAt(rect.center())
        if screen:
            screens = QGuiApplication.screens()
            idx = screens.index(screen)
            geo = screen.geometry()
            dpr = screen.devicePixelRatio()
            print(f"  Qt says this is on: Monitor {idx} ({screen.name()})")
            print(f"  Monitor geometry: ({geo.x()}, {geo.y()}) {geo.width()}x{geo.height()}")
            print(f"  DPR: {dpr}")
        else:
            print(f"  ⚠️  Qt could not determine screen!")
        
        dpr = screen.devicePixelRatio()
        x = int(rect.x() * dpr)
        y = int(rect.y() * dpr)
        w = int(rect.width() * dpr)
        h = int(rect.height() * dpr)

        print(f"\nPassing to capture: ({x}, {y}) {w}x{h}")
        print(f"Mode: {self.selected_content_mode.upper()}")
        print("=" * 80 + "\n")
        
        QTimer.singleShot(120, lambda: self._do_capture_and_ocr(x, y, w, h))

    def _do_capture_and_ocr(self, x, y, w, h):
        """Enhanced capture flow with immediate loader visibility."""
        # Capture image
        image = capture_region(x, y, w, h)
        if not image:
            self.extracted_box.setPlainText("❌ Capture failed.")
            self.showNormal()
            return

        # Clear old content
        self.extracted_box.clear()
        
        # Show window FIRST (required for loader visibility)
        self.showNormal()
        self.raise_()
        self.activateWindow()

        # ✅ Show loader instantly
        self._show_loader(self.loader_extracted, immediate=True)

        # ✅ Allow Qt to render loader before heavy preview processing
        QTimer.singleShot(100, lambda: self._start_ocr_worker(image, x, y, w, h))

    class _PreviewLoaderWorker(QObject):
        """Small worker to load preview image off the UI thread."""
        finished = Signal(object)

        def __init__(self, image):
            super().__init__()
            self.image = image

        def run(self):
            try:
                # Convert PIL image → QPixmap safely in background
                from PySide6.QtGui import QImage, QPixmap
                import numpy as np
                img = self.image.convert("RGBA")
                arr = np.array(img)
                h, w, ch = arr.shape
                qimg = QImage(arr.data, w, h, ch * w, QImage.Format_RGBA8888)
                pixmap = QPixmap.fromImage(qimg.copy())  # ensure data is owned by Qt
                self.finished.emit(pixmap)
            except Exception as e:
                import logging
                logging.warning(f"Preview thread failed: {e}")
                self.finished.emit(None)

    def _start_ocr_worker(self, image, x, y, w, h):
        """Start OCR processing (with async preview load)."""
        
        # 1) Start preview thread
        self._preview_thread = QThread()
        self._preview_worker = self._PreviewLoaderWorker(image)
        self._preview_worker.moveToThread(self._preview_thread)
        self._preview_thread.started.connect(self._preview_worker.run)
        self._preview_worker.finished.connect(self._on_preview_loaded)
        self._preview_worker.finished.connect(self._preview_thread.quit)
        self._preview_thread.finished.connect(self._preview_worker.deleteLater)
        self._preview_thread.finished.connect(self._preview_thread.deleteLater)
        self._preview_thread.start()

        # 2) Determine layout type from selected mode
        if self.selected_content_mode == "text":
            layout_type = "text"
            override_model = False
        elif self.selected_content_mode == "table":
            layout_type = "table"
            override_model = True  # Use Gemini Pro for tables
        else:
            layout_type = "text"
            override_model = False

        layout_conf = 1.0

        # 3) Save temp image
        import tempfile
        temp_fd, temp_path = tempfile.mkstemp(suffix='.png')
        os.close(temp_fd)
        image.save(temp_path)

        # 4) Create OCR worker with all required parameters
        self.thread = QThread()
        self.worker = OCRWorker(
            temp_path,
            self.config,
            do_translate=False,  # Translation is separate
            dest_lang="en"
        )
        
        # Set layout detection parameters
        self.worker.layout_type = layout_type
        self.worker.layout_confidence = layout_conf
        self.worker.override_table_model = override_model

        # 5) Connect signals and start
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_ocr_done)
        self.worker.failed.connect(self._on_ocr_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        logger.info(f"Started OCR worker: mode={layout_type}, override={override_model}")
        
    def _on_preview_loaded(self, pixmap):
        """Receive pixmap from background worker and display it correctly."""
        if pixmap is None:
            return
        try:
            # Your ZoomablePreviewWidget expects a QPixmap
            if hasattr(self.preview_widget, "set_image"):
                self.preview_widget.set_image(pixmap)
            else:
                # Fallback if the widget still uses PIL-based loader
                from PIL import ImageQt
                pil_img = ImageQt.fromqpixmap(pixmap)
                self.preview_widget.set_image_from_pil(pil_img)
            logger.info("✅ Preview image displayed successfully")
        except Exception as e:
            logger.warning(f"Preview display failed: {e}")


    def _on_ocr_done(self, text, translated):
        """Handle OCR completion - hide loader BEFORE showing text."""
        # Handle dict results from Gemini (math mode with images)
        if isinstance(text, dict):
            # Extract text component
            actual_text = text.get("text", "")
            # Store additional data if needed
            if "math_images" in text:
                self._math_images = text["math_images"]
            if "math_omml" in text:
                self._math_omml = text["math_omml"]
            text = actual_text
        
        # Hide loader first (no delay)
        self._hide_loader(self.loader_extracted, delay_ms=0)
        
        # Wait for hide animation, then show text
        QTimer.singleShot(150, lambda: self._display_ocr_result(text, translated))
        
    def _display_ocr_result(self, text, translated):
        """Display OCR results after loader is hidden."""
        try:
            if not text:
                self.extracted_box.setPlainText("No text extracted.")
                return

            # Render formatted content
            self._render_formatted_content(text)

            # Show translation if available
            if translated and translated.strip():
                self.translated_box.setPlainText(translated)
                self.translated_label.setVisible(True)
                self.translated_resizable.setVisible(True)

            self.status_label.setText("✅ OCR Complete")
            QTimer.singleShot(2000, lambda: self.status_label.setVisible(False))

        except Exception as e:
            logger.exception(f"Display failed: {e}")
            self.extracted_box.setPlainText(text)

    def _on_ocr_failed(self, msg):
        """Handle OCR failure."""
        self._hide_loader(self.loader_extracted)
        self.status_label.setText(f"OCR failed: {msg}")
        self.status_label.setVisible(True)

    # =========================================================================
    # TRANSLATION FLOW WITH LOADER
    # =========================================================================

    def run_translation(self):
        """Enhanced translation with immediate loader."""
        text = self.extracted_box.toPlainText().strip()
        if not text:
            self.status_label.setText("No text to translate.")
            self.status_label.setVisible(True)
            return

        dest = self.trans_codes[self.trans_lang.currentText()]

        # Clear old translation
        self.translated_box.clear()
        
        # Make translation box visible
        self.translated_label.setVisible(True)
        self.translated_resizable.setVisible(True)

        # ✅ Show loader IMMEDIATELY
        self._show_loader(self.loader_translated, immediate=True)

        # Start translation thread
        self._tran_thread = QThread()
        self._tran_worker = TranslatorThread(text, dest)
        self._tran_worker.moveToThread(self._tran_thread)
        self._tran_thread.started.connect(self._tran_worker.run)
        self._tran_worker.finished.connect(self._on_translate_done)
        self._tran_worker.failed.connect(self._on_translate_failed)
        self._tran_worker.finished.connect(self._tran_thread.quit)
        self._tran_worker.failed.connect(self._tran_thread.quit)
        self._tran_thread.finished.connect(self._tran_worker.deleteLater)
        self._tran_thread.finished.connect(self._tran_thread.deleteLater)
        self._tran_thread.start()

    def _on_translate_done(self, translated):
        """Handle translation completion - hide loader BEFORE showing text."""
        # Hide loader
        self._hide_loader(self.loader_translated, delay_ms=0)
        self.tr_label.setVisible(True)
        self.copy_translated_btn.setVisible(True)
        self.translated_frame.setVisible(True)
        self.translated_resizable.setVisible(True)

        # Wait for hide, then show text
        QTimer.singleShot(150, lambda: self._display_translation(translated))

    def _display_translation(self, translated):
        """Display translated text after loader is hidden."""
        self.translated_box.setPlainText(translated or "")

        from PySide6.QtWidgets import QGraphicsOpacityEffect

        effect = QGraphicsOpacityEffect(self.translated_resizable)
        self.translated_resizable.setGraphicsEffect(effect)
        self.tr_label.setVisible(True)
        self.copy_translated_btn.setVisible(True)
        self.translated_frame.setVisible(True)
        self.translated_resizable.setVisible(True)

        anim = make_anim(effect, b"opacity", 0.0, 1.0, dur=ANIM_NORMAL, curve=EASE_SOFT)
        anim.start()
        self._translate_fade = anim

    def _on_translate_failed(self, err):
        """Handle translation failure."""
        self._hide_loader(self.loader_translated)
        self.status_label.setText("Translation failed.")
        self.status_label.setVisible(True)
        logger.error(err)

    def _safe_render_ocr_result(self, text, translated):
        """Render OCR results after loader fade-out (delayed from _on_ocr_done)."""
        try:
            if not text:
                self.extracted_box.setPlainText("No text extracted.")
                return

            # Render formatted content
            self._render_formatted_content(text)

            # Show translation if available
            if translated and translated.strip():
                self.translated_box.setPlainText(translated)
                self.translated_label.setVisible(True)
                self.translated_frame.setVisible(True)

            self.status_label.setText("✅ OCR Complete")

            # Auto-hide status after 2 seconds
            QTimer.singleShot(2000, lambda: self.status_label.setVisible(False))

        except Exception as e:
            import traceback
            logger.exception(f"Failed to render OCR result: {e}")
            # Fallback to plain text
            self.extracted_box.setPlainText(text)
            self.status_label.setText("⚠️ Render error, showing raw text")
            
    def _render_formatted_content(self, text: str):
        """Render with theme-aware display but store raw HTML for copying."""
        from core.postprocess import process_ocr_text_with_math
        
        if not text:
            self.extracted_box.setPlainText("")
            return
        
        # Handle dict results
        if isinstance(text, dict):
            text = text.get("text", "")
        
        # Process math formulas
        text = process_ocr_text_with_math(text, for_display=True)
        
        # Check content type
        has_html = any(tag in text.lower() for tag in ['<table', '<ul>', '<ol>', '<li>', '<math'])
        
        if has_html:
            # Apply theme styling FOR DISPLAY ONLY
            styled_html = self._apply_content_styling(text)
            self.extracted_box.setHtml(styled_html)
            
            # Store RAW HTML (without theme) for clipboard
            self._last_full_html = text  # ← CRITICAL: Store original, not styled_html
            
            logger.info("✅ Rendered content with visible table borders")
        else:
            # Plain text path
            formatted_text = self._smart_format_text(text)
            html_content = self._plain_text_to_html(formatted_text)
            self.extracted_box.setHtml(html_content)
            self._last_full_html = html_content
            
            logger.info("Rendered plain text with formatting")
            
    def _create_math_placeholder(self, mathml: str) -> str:
        """
        Create a visual placeholder for MathML in the app.
        The actual MathML is preserved for copying.
        """
        # Try to extract a simple representation
        # Remove XML tags for display
        text_only = re.sub(r'<[^>]+>', '', mathml)
        text_only = text_only.strip()
        
        # Limit length for display
        if len(text_only) > 50:
            text_only = text_only[:47] + "..."
        
        # Return styled placeholder
        theme_color = "#3E9CF6" if self.current_theme == "dark" else "#0078D4"
        return f'<span style="background-color: {theme_color}20; color: {theme_color}; padding: 2px 6px; border-radius: 4px; font-family: Cambria Math; font-style: italic;">{text_only or "📐 Math Formula"}</span>'

    def _apply_theme_to_text_boxes(self):
        """Apply theme colors to extracted and translated QTextEdit boxes."""
        if self.current_theme == "dark":
            bg = "#1E293B"
            fg = "#F1F5F9"
            border = "#334155"
            selection_bg = "#3B82F6"
        else:
            bg = "#FFFFFF"
            fg = "#1E1032"
            border = "#D8C9F6"
            selection_bg = "#C3B5F7"

        qss = f"""
            QTextEdit {{
                background-color: {bg};
                color: {fg};
                border: none;
                padding: 6px;
                padding-right: 40px;   /* 👈 prevents text overlapping copy button */
                selection-background-color: {selection_bg};
            }}
        """
        # Apply to both text boxes
        if hasattr(self, "extracted_box"):
            self.extracted_box.setStyleSheet(qss)

        if hasattr(self, "translated_box"):
            self.translated_box.setStyleSheet(qss)

        if hasattr(self, 'mode_popup'):
            self.mode_popup.update_theme(theme)
            logger.debug(f"Mode selector theme updated to: {theme}")
    
    def _apply_content_styling(self, html_content: str) -> str:
        """
        Add CSS styling to HTML content for better rendering IN THE APP.
        
        Features:
        - Proper table styling with VISIBLE BORDERS
        - List formatting
        - Hindi font support
        - Consistent spacing
        - Theme-aware colors for APP DISPLAY only
        """
        # Determine theme colors FOR APP DISPLAY
        if self.current_theme == "dark":
            bg_color = "#1E293B"
            text_color = "#E2E8F0"
            border_color = "#64748B"  # Visible gray border
            header_bg = "#334155"
            row_hover = "#293548"
        else:
            bg_color = "#FFFFFF"
            text_color = "#0F172A"
            border_color = "#94A3B8"  # Visible gray border
            header_bg = "#F1F5F9"
            row_hover = "#F8FAFC"
        
        # Build styled HTML with embedded CSS FOR APP DISPLAY
        styled = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Noto Sans Devanagari', 'Segoe UI', 'Nirmala UI', Arial, sans-serif;
                    font-size: 11.5px;
                    line-height: 1.6;
                    color: {text_color};
                    background: {bg_color};
                    margin: 0;
                    padding: 8px 90px 8px 8px;   /* top | right | bottom | left */
                }}
                
                /* Table Styling - VISIBLE BORDERS IN APP */
               table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 12px 0;
                    border: 1px solid {border_color};    /* thinner outer border */
                    background: {bg_color};
                }}

                th, td {{
                    border: 0.7px solid {border_color};  /* thinner cell borders */
                    padding: 8px 10px;
                    text-align: left;
                    vertical-align: top;
                }}
                
                th {{
                    background-color: {header_bg};
                    font-weight: 600;
                    font-size: 12px;
                }}
                
                tr:nth-child(even) {{
                    background-color: {row_hover};
                }}
                
                tr:hover {{
                    background-color: {row_hover};
                }}
                
                /* List Styling */
                ul, ol {{
                    margin: 8px 0;
                    padding-left: 20px;
                }}
                
                ul[style*="list-style-type: none"] {{
                    padding-left: 0;
                }}
                
                li {{
                    margin: 4px 0;
                    line-height: 1.7;
                }}
                
                /* Custom bullet styling */
                .bullet-item {{
                    display: block;
                    margin: 6px 0;
                    padding-left: 0;
                }}
                
                /* Spacing */
                p {{
                    margin: 8px 0;
                }}
                
                /* Preserve whitespace for formatted text */
                pre {{
                    font-family: 'Noto Sans Devanagari', 'Segoe UI', 'Nirmala UI', monospace;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                    background: transparent;
                    border: none;
                    margin: 0;
                    padding: 0;
                }}
            </style>
        </head>
        <body>
            <div style="width: calc(100% - 110px); padding-right: 20px; box-sizing: border-box;">
                {html_content}
            </div>
        </body>
        </html>
        """
        
        return styled


    def _render_formatted_content(self, text: str):
        """
        Render extracted content with proper formatting and math support.
        
        Handles:
        - LaTeX → MathML conversion
        - HTML content (tables, lists)
        - Plain text with bullet points
        - Mathematical formulas (inline and display)
        - Tables with VISIBLE BORDERS in app
        """
        from core.postprocess import process_ocr_text_with_math, prepare_math_for_clipboard
        
        if not text:
            self.extracted_box.setPlainText("")
            return
        
        # Handle dict results from math mode (with images/OMML)
        if isinstance(text, dict):
            text = text.get("text", "")
        
        # Step 1: Process math formulas
        text = process_ocr_text_with_math(text, for_display=True)
        
        # Step 2: Check content type
        has_html = any(tag in text.lower() for tag in ['<table', '<ul>', '<ol>', '<li>', '<math'])
        
        if has_html:
            # Render as HTML with math support
            # Apply theme-specific styling for APP DISPLAY
            styled_html = self._apply_content_styling(text)
            
            # For display in app: Show with theme colors
            display_html = styled_html
            
            self.extracted_box.setHtml(display_html)
            
            # Store ORIGINAL HTML for clipboard (will be converted to Table Grid on copy)
            self._last_full_html = text  # Store raw HTML without theme styling
            
            logger.info("✅ Rendered content with visible table borders")
        else:
            # Plain text path
            formatted_text = self._smart_format_text(text)
            html_content = self._plain_text_to_html(formatted_text)
            self.extracted_box.setHtml(html_content)
            self._last_full_html = html_content
            
            logger.info("Rendered plain text with formatting")

    def _plain_text_to_html(self, text: str) -> str:
        """
        Convert plain text with bullets/numbers to compact, formatted HTML.
        Preserves:
        - Bullet symbols (◆, •, ○, etc.)
        - Numbered lists (1., 2), etc.)
        - Line breaks
        - Minimal spacing for clean rendering
        """
        import re

        lines = text.split("\n")
        html_lines = []
        in_ul = False
        in_ol = False

        bullet_symbols = ['◆', '•', '○', '▸', '◾', '▪', '–', '—', '●', '■', '-', '*']

        for line in lines:
            stripped = line.strip()

            # Handle blank lines
            if not stripped:
                if in_ul:
                    html_lines.append("</ul>")
                    in_ul = False
                if in_ol:
                    html_lines.append("</ol>")
                    in_ol = False
                continue

            has_bullet = any(stripped.startswith(symbol) for symbol in bullet_symbols)
            has_number = re.match(r"^\d+[\.\)]", stripped)

            # --- Bulleted list ---
            if has_bullet:
                # Close numbered list if open
                if in_ol:
                    html_lines.append("</ol>")
                    in_ol = False
                # Open bullet list if needed
                if not in_ul:
                    html_lines.append(
                        '<ul style="list-style-position: outside; margin: 2px 0; padding-left: 16px;">'
                    )
                    in_ul = True

                cleaned = re.sub(r"^[•◆○▸◾▪–—●■\-\*]+\s*", "", stripped)
                escaped = cleaned.replace("<", "&lt;").replace(">", "&gt;")
                html_lines.append(f'<li style="margin: 0; padding: 0;">{escaped}</li>')
                continue

            # --- Numbered list ---
            elif has_number:
                # Close bullet list if open
                if in_ul:
                    html_lines.append("</ul>")
                    in_ul = False
                # Open ordered list if needed
                if not in_ol:
                    html_lines.append(
                        '<ol style="list-style-position: outside; margin: 2px 0; padding-left: 20px;">'
                    )
                    in_ol = True

                cleaned = re.sub(r"^\d+[\.\)]\s*", "", stripped)
                escaped = cleaned.replace("<", "&lt;").replace(">", "&gt;")
                html_lines.append(f'<li style="margin: 0; padding: 0;">{escaped}</li>')
                continue

            # --- Regular text line ---
            else:
                # Close any active lists
                if in_ul:
                    html_lines.append("</ul>")
                    in_ul = False
                if in_ol:
                    html_lines.append("</ol>")
                    in_ol = False

                escaped = stripped.replace("<", "&lt;").replace(">", "&gt;")
                html_lines.append(f'<div style="margin: 2px 0;">{escaped}</div>')

        # Close open lists
        if in_ul:
            html_lines.append("</ul>")
        if in_ol:
            html_lines.append("</ol>")

        html = "\n".join(html_lines)
        html = re.sub(r"\s+\n", "\n", html)
        html = re.sub(r"\n{2,}", "\n", html).strip()
        html = html.replace("<math>", "<span style='font-family: Cambria Math;'>").replace("</math>", "</span>")

        return self._apply_content_styling(html)

    def _smart_format_text(self, raw_text: str) -> str:
        """
        Preserve original content but add line breaks only when needed.
        - Keeps all existing newlines and spacing.
        - Adds missing line breaks before bullets, numbered lists, or new sections.
        - Never merges or rewrites text content.
        - Avoids breaking table-like data.
        """
        import re

        # Keep HTML untouched
        if any(tag in raw_text.lower() for tag in ["<table", "<tr", "<td", "<ul", "<ol", "<li>"]):
            return raw_text

        text = raw_text.strip()

        # Normalize multiple spaces but preserve newlines
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\r", "", text)

        # Split into lines (keep logical structure)
        lines = text.split("\n")
        formatted_lines = []
        bullet_symbols = ["•", "-", "●", "▪", "–", "—", "*", "◦", "‣", "◆", "►"]

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Keep empty lines as-is
            if not stripped:
                formatted_lines.append("")
                continue

            # Detect bullet/numbered line
            if re.match(rf"^\s*({'|'.join(re.escape(b) for b in bullet_symbols)})\s+", stripped) or \
               re.match(r"^\s*\d+[\.\)]\s+", stripped):
                # Add a line break before if previous line was text
                if i > 0 and lines[i - 1].strip():
                    formatted_lines.append("")
                formatted_lines.append(stripped)
                continue

            # Detect probable section headers or large jumps in capitalization
            if i > 0 and stripped and lines[i - 1].strip() and (
                stripped[0].isupper() and not lines[i - 1].strip().endswith((".", "?", "!", ":", ";"))
            ):
                formatted_lines.append("")  # soft break between sections

            # Keep tables or pipe data intact
            if "|" in stripped or "\t" in stripped:
                formatted_lines.append(stripped)
                continue

            formatted_lines.append(stripped)

        # Collapse more than 2 consecutive empty lines → keep max 1
        result = re.sub(r"\n{3,}", "\n\n", "\n".join(formatted_lines))

        return result.strip()

    # ---------- Tray ----------
    def _setup_tray(self):
        from utils.autostart import is_auto_start_enabled, enable_auto_start, disable_auto_start

        self.tray = QSystemTrayIcon(get_app_icon(), self)
        self.tray.setToolTip("OCR Capture Tool")

        # --- Tray Menu ---
        menu = QMenu()

        show_action = QAction("Show Popup", self)
        capture_action = QAction("Capture", self)

        # ✅ Dynamic autostart toggle
        def refresh_autostart_action():
            menu.removeAction(self.auto_action) if hasattr(self, "auto_action") else None

            if is_auto_start_enabled():
                self.auto_action = QAction("Disable Autostart", self)
                self.auto_action.triggered.connect(lambda: (disable_auto_start("OCRApp"), refresh_autostart_action()))
            else:
                self.auto_action = QAction("Enable Autostart", self)
                self.auto_action.triggered.connect(lambda: (enable_auto_start(), refresh_autostart_action()))

            # Insert just before the separator or end
            menu.insertAction(self.quit_action, self.auto_action)

        quit_action = QAction("Quit", self)

        show_action.triggered.connect(self.showNormal)
        capture_action.triggered.connect(self.start_capture)
        quit_action.triggered.connect(QApplication.quit)

        menu.addAction(show_action)
        menu.addAction(capture_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        # initialize toggle dynamically
        self.quit_action = quit_action  # store reference for insertion
        refresh_autostart_action()

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_click)
        self.tray.show()

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_click)
        self.tray.show()

    def _on_tray_click(self, reason):
        import time
        from PySide6.QtWidgets import QSystemTrayIcon

        # Ignore tray activations triggered right after menu close
        if time.time() < self._ignore_tray_click_until:
            return

        if self._tray_menu_open:
            return

        if reason == QSystemTrayIcon.Trigger:
            self._show_left_click_menu()



    def closeEvent(self, e):
        e.ignore()
        self.hide()
            
    # Replace both resizeEvent definitions in popup.py with this unified method
    def resizeEvent(self, event):
        super().resizeEvent(event)

        # Save last size to restore after e.g. theme transitions
        self._last_user_size = self.size()

        # Debounced save of window size (to avoid thrashing disk)
        if not hasattr(self, '_resize_save_timer'):
            self._resize_save_timer = QTimer(self)
            self._resize_save_timer.setSingleShot(True)
            self._resize_save_timer.timeout.connect(lambda: LayoutManager.save_window_size(self.width(), self.height()))
        self._resize_save_timer.stop()
        self._resize_save_timer.start(800)  # save after 800ms of no resizing

        # Keep the settings panel anchored to the right and overlays in sync
        try:
            if hasattr(self, "settings_panel") and self.settings_panel.isVisible():
                self.settings_panel.setGeometry(
                    max(self.width() - self.settings_panel.width(), 180),
                    0,
                    self.settings_panel.width(),
                    self.height()
                )
            if hasattr(self, "_overlay_widget"):
                self._overlay_widget.setGeometry(self.rect())
            if hasattr(self, "_fade_overlay"):
                self._fade_overlay.setGeometry(self.rect())
        except Exception:
            # Guard to avoid resize failures crashing the window
            logger.exception("Error during resizeEvent geometry sync")

    # ---------- Config ----------
    def _restore_last_langs(self):
        """Preserve only translation language since OCR lang dropdown is removed."""
        # Default OCR mode is dual English + Hindi (eng+hin)
        self.last_ocr_lang = "eng+hin"

        lt = self.config.get("last_translate_lang", "hi")
        for k, v in self.trans_codes.items():
            if v == lt:
                self.trans_lang.setCurrentText(k)

    def _save_langs(self):
        """Save only translation language since OCR dropdown is removed."""
        self.config["last_ocr_lang"] = "eng+hin"
        self.config["last_translate_lang"] = self.trans_codes[self.trans_lang.currentText()]
        save_config(self.config)

    def _deferred_save_config(self, delay_ms=200):
        # debounce writes so many save_config calls in init don't thrash disk
        try:
            if hasattr(self, "_save_timer") and getattr(self, "_save_timer", None):
                self._save_timer.stop()
        except Exception:
            pass
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(lambda: save_config(self.config))
        self._save_timer.start(delay_ms)

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for zoom."""
        # Ctrl+0: Reset window zoom
        if event.key() == Qt.Key_0 and event.modifiers() & Qt.ControlModifier:
            self.window_zoom_controller.reset_zoom()
            event.accept()
            return
        
        # Ctrl++: Zoom in window
        if event.key() in (Qt.Key_Plus, Qt.Key_Equal) and event.modifiers() & Qt.ControlModifier:
            self.window_zoom_controller.zoom_in()
            event.accept()
            return
        
        # Ctrl+-: Zoom out window
        if event.key() == Qt.Key_Minus and event.modifiers() & Qt.ControlModifier:
            self.window_zoom_controller.zoom_out()
            event.accept()
            return
        
        super().keyPressEvent(event)
        
    # ===============================================================
    # IN-APP BACKGROUND HOTKEY LISTENER (works in tray mode)
    # ===============================================================
    def _start_hotkey_listener(self):
        import keyboard
        import threading

        if hasattr(self, "_hotkey_thread"):
            return

        def listener():
            buffer = []

            while True:
                event = keyboard.read_event()

                if event.event_type != "down":
                    continue

                key = event.name.lower()

                # Handle Alt separately
                if key == "alt":
                    buffer = []
                    continue

                buffer.append(key)

                if len(buffer) > 3:
                    buffer = []

                # ----- LOAD USER SHORTCUTS -----
                shortcut_text  = self.config.get("shortcut_text",  "alt+t+1").split("+")
                shortcut_table = self.config.get("shortcut_table", "alt+t+2").split("+")
                shortcut_popup = self.config.get("shortcut_popup", "alt+t+p").split("+")

                # ----- MATCH USER SHORTCUTS -----
                if buffer == shortcut_text:
                    buffer = []
                    self.trigger_text.emit()

                if buffer == shortcut_table:
                    buffer = []
                    self.trigger_table.emit()

                if buffer == shortcut_popup:
                    buffer = []
                    self.trigger_popup.emit()

        self._hotkey_thread = threading.Thread(target=listener, daemon=True)
        self._hotkey_thread.start()

    
    def _start_capture_mode(self, mode: str):
        self.shortcut_override_mode = mode
        self.selected_content_mode = mode   # ensure both are set
        self._set_capture_mode(mode)
        self.start_capture()

def run_app():
    from PySide6.QtCore import Qt, QCoreApplication, QTimer
    from PySide6.QtWidgets import QApplication

    # Initialize app
    app = QApplication([])

    # =====================================================
    # 🧠 SAFE CPU-ONLY SETTINGS (DO NOT BREAK MULTI-MONITOR)
    # =====================================================

    # ❗ Keep these (safe)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QCoreApplication.setAttribute(Qt.AA_SynthesizeTouchForUnhandledMouseEvents, True)

    # ❗ REMOVE all software OpenGL / raster forcing / DPI override
    # They BREAK mouse events on secondary monitors.
    # (Do NOT re-add the removed lines.)

    # =====================================================
    # 🎞 Smooth Animation Timing (fine to keep)
    # =====================================================
    QTimer.singleShot(0, lambda: app.setAnimationInterval(8))

    # =====================================================
    # 🪄 Start Window
    # =====================================================
    from gui.popup import PopupWindow
    window = PopupWindow()
    window.show()

    # =====================================================
    # 🚀 Run Loop
    # =====================================================
    app.exec()

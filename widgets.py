from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, Property, QSize, QPropertyAnimation
from PySide6.QtGui import QPainter, QColor, QPen

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

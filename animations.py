# gui/animations.py
from PySide6.QtCore import QEasingCurve, QPropertyAnimation

# --- Standard animation constants ---
ANIM_FAST = 180       # quick feedback (hover, small fades)
ANIM_NORMAL = 250     # standard UI transitions
ANIM_SLOW = 350       # longer transitions (overlays, panels)

EASE_STD = QEasingCurve.InOutCubic     # universal easing
EASE_SOFT = QEasingCurve.InOutQuad     # gentle fade
EASE_BOUNCE = QEasingCurve.OutBack     # subtle bounce for buttons

# --- Reusable animation helper ---
def make_anim(target, prop: bytes, start, end, dur=ANIM_NORMAL, curve=EASE_STD):
    anim = QPropertyAnimation(target, prop)
    anim.setDuration(dur)
    anim.setEasingCurve(curve)
    anim.setStartValue(start)
    anim.setEndValue(end)
    return anim

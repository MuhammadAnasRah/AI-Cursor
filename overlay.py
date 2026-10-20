"""Transparent, click-through, always-on-top overlay.

Draws the AI cursor glyph trailing the real pointer, and the answer bubble.
"""

import ctypes

import win32api
import win32con
import win32gui
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

TICK_MS = 16          # ~60 Hz
TRAIL = 0.18          # lerp factor; lower = laggier, more visibly "following"
GLYPH_R = 11

BUBBLE_W = 380
BUBBLE_PAD = 14
BUBBLE_GAP = 26       # distance from pointer to bubble
FADE_AFTER_MS = 6000
FADE_MS = 700

BG = QColor(18, 18, 22, 238)
FG = QColor(240, 240, 245)
ACCENT = QColor(255, 90, 140)
DIM = QColor(150, 150, 165)


class Overlay(QWidget):
    # Signals so worker threads can safely push updates into the Qt thread.
    chunk_arrived = Signal(str)
    stream_started = Signal(str)
    stream_finished = Signal()
    stream_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Cover the entire virtual desktop, all monitors included.
        vx = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        vy = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        vw = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
        vh = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
        self._origin = (vx, vy)
        self.setGeometry(vx, vy, vw, vh)

        self._glyph = QPointF(0, 0)
        self._target = QPointF(0, 0)
        self._text = ""
        self._label = ""
        self._busy = False
        self._opacity = 1.0
        self._anchor = None       # pointer pos frozen when a query starts

        self._font = QFont("Segoe UI", 10)
        self._label_font = QFont("Segoe UI", 8)
        self._label_font.setBold(True)

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start(TICK_MS)

        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._start_fade)

        self._fade_anim = QTimer(self)
        self._fade_anim.timeout.connect(self._step_fade)

        self.chunk_arrived.connect(self._on_chunk)
        self.stream_started.connect(self._on_start)
        self.stream_finished.connect(self._on_finish)
        self.stream_failed.connect(self._on_fail)

    # --- window setup -----------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._make_click_through()

    def _make_click_through(self):
        """Belt and braces: Qt's flag plus the raw Win32 extended style."""
        hwnd = int(self.winId())
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(
            hwnd,
            win32con.GWL_EXSTYLE,
            style
            | win32con.WS_EX_LAYERED
            | win32con.WS_EX_TRANSPARENT
            | win32con.WS_EX_TOOLWINDOW
            | win32con.WS_EX_NOACTIVATE,
        )

    # --- state changes from the worker thread -----------------------------

    def _on_start(self, app_name):
        self._anchor = QPointF(*win32api.GetCursorPos())
        self._text = ""
        self._label = app_name
        self._busy = True
        self._opacity = 1.0
        self._fade_timer.stop()
        self._fade_anim.stop()

    def _on_chunk(self, piece):
        self._text += piece

    def _on_finish(self):
        self._busy = False
        self._fade_timer.start(FADE_AFTER_MS)

    def _on_fail(self, message):
        self._busy = False
        self._text = message
        self._fade_timer.start(FADE_AFTER_MS)

    def _start_fade(self):
        self._fade_anim.start(TICK_MS)

    def _step_fade(self):
        self._opacity -= TICK_MS / FADE_MS
        if self._opacity <= 0:
            self._opacity = 0.0
            self._fade_anim.stop()
            self._text = ""
            self._anchor = None

    # --- per-frame --------------------------------------------------------

    def _on_tick(self):
        x, y = win32api.GetCursorPos()
        self._target = QPointF(x - self._origin[0], y - self._origin[1])
        d = self._target - self._glyph
        self._glyph += QPointF(d.x() * TRAIL, d.y() * TRAIL)
        self.update()

    # --- painting ---------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter()
        if not p.begin(self):
            return
        try:
            p.setRenderHint(QPainter.Antialiasing)
            self._paint_glyph(p)
            if self._text or self._busy:
                p.setOpacity(self._opacity)
                self._paint_bubble(p)
        finally:
            # Must end explicitly. Leaving it to garbage collection makes the
            # painter outlive the frame and Qt complains on every repaint.
            p.end()

    def _paint_glyph(self, p):
        c = self._glyph
        ring = QColor(ACCENT)
        ring.setAlpha(200 if self._busy else 120)
        p.setPen(QPen(ring, 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, GLYPH_R, GLYPH_R)

        core = QColor(ACCENT)
        core.setAlpha(230 if self._busy else 150)
        p.setPen(Qt.NoPen)
        p.setBrush(core)
        p.drawEllipse(c, 3.0, 3.0)

    def _paint_bubble(self, p):
        anchor = self._anchor or self._target
        body = self._text if self._text else "Reading the screen…"

        fm = QFontMetrics(self._font)
        inner_w = BUBBLE_W - BUBBLE_PAD * 2
        text_rect = fm.boundingRect(
            QRectF(0, 0, inner_w, 10000).toRect(),
            int(Qt.TextWordWrap),
            body,
        )
        label_h = 16 if self._label else 0
        h = text_rect.height() + BUBBLE_PAD * 2 + label_h

        # Place to the lower-right of the pointer, flipping near screen edges.
        x = anchor.x() + BUBBLE_GAP
        y = anchor.y() + BUBBLE_GAP
        if x + BUBBLE_W > self.width() - 8:
            x = anchor.x() - BUBBLE_GAP - BUBBLE_W
        if y + h > self.height() - 8:
            y = anchor.y() - BUBBLE_GAP - h
        x = max(8, min(x, self.width() - BUBBLE_W - 8))
        y = max(8, min(y, self.height() - h - 8))

        rect = QRectF(x, y, BUBBLE_W, h)

        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.setBrush(BG)
        p.drawPath(path)

        cursor_y = y + BUBBLE_PAD
        if self._label:
            p.setFont(self._label_font)
            p.setPen(DIM)
            p.drawText(
                QRectF(x + BUBBLE_PAD, cursor_y, inner_w, 14),
                int(Qt.AlignLeft | Qt.AlignVCenter),
                self._label.upper(),
            )
            cursor_y += label_h

        p.setFont(self._font)
        p.setPen(FG if self._text else DIM)
        p.drawText(
            QRectF(x + BUBBLE_PAD, cursor_y, inner_w, text_rect.height()),
            int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop),
            body,
        )


def set_dpi_aware():
    """Must run before any window exists, or coords drift on scaled displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


if __name__ == "__main__":
    # Standalone check: just the glyph. Confirm you can click through it.
    import sys

    from PySide6.QtWidgets import QApplication

    set_dpi_aware()
    app = QApplication(sys.argv)
    w = Overlay()
    w.show()
    w._text = "Overlay is running. Click through me to check I am not stealing input. Ctrl+C in the terminal to quit."
    w._label = "test"
    print("Overlay up. Ctrl+C here to quit.")
    sys.exit(app.exec())

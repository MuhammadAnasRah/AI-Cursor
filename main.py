"""AI Cursor — prototype entry point.

Hold Ctrl+Shift+Space while hovering anything on screen to get an explanation.
Press Ctrl+Shift+Q to quit.
"""

import os
import sys
import threading

import keyboard
from PySide6.QtWidgets import QApplication

import brain
import capture
import overlay

HOTKEY = "ctrl+shift+space"
QUIT_KEY = "ctrl+shift+q"

_lock = threading.Lock()
_running = False


def _query(win: overlay.Overlay):
    """Runs on a worker thread. Never touch Qt widgets directly from here."""
    global _running
    try:
        crop_b64, full_b64, meta = capture.grab()
        win.stream_started.emit(meta.get("app", ""))

        got_any = False
        for piece in brain.explain(crop_b64, full_b64, meta):
            got_any = True
            win.chunk_arrived.emit(piece)

        if not got_any:
            win.stream_failed.emit("The model returned nothing. Try again.")
        else:
            win.stream_finished.emit()

    except Exception as exc:
        win.stream_failed.emit(f"Error: {exc}")
    finally:
        with _lock:
            _running = False


def _on_hotkey(win):
    global _running
    with _lock:
        if _running:
            return          # ignore repeats while a query is in flight
        _running = True
    threading.Thread(target=_query, args=(win,), daemon=True).start()


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Set it and run again.")
        return 1

    overlay.set_dpi_aware()
    app = QApplication(sys.argv)

    win = overlay.Overlay()
    win.show()

    try:
        keyboard.add_hotkey(HOTKEY, lambda: _on_hotkey(win))
        keyboard.add_hotkey(QUIT_KEY, app.quit)
    except Exception as exc:
        print(f"Could not register hotkeys: {exc}")
        print("Run this from a terminal opened as administrator.")
        return 1

    print("AI Cursor running.")
    print(f"  {HOTKEY}  explain what is under the pointer")
    print(f"  {QUIT_KEY}      quit")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

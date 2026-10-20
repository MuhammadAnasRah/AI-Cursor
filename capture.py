"""Screen capture: crop around the cursor, plus a downscaled full view."""

import base64
import io

import mss
import win32api
import win32gui
import win32process
from PIL import Image

# Native-resolution box captured around the pointer.
CROP_W, CROP_H = 520, 320

# Longest edge of the downscaled full-screen context shot.
FULL_MAX_EDGE = 1024


def cursor_pos():
    return win32api.GetCursorPos()


def foreground_app():
    """Process name of whatever window currently has focus, e.g. 'Premiere.exe'."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        handle = win32api.OpenProcess(0x0400 | 0x0010, False, pid)
        try:
            path = win32process.GetModuleFileNameEx(handle, 0)
        finally:
            win32api.CloseHandle(handle)
        return path.split("\\")[-1]
    except Exception:
        return "unknown"


def foreground_title():
    try:
        return win32gui.GetWindowText(win32gui.GetForegroundWindow())
    except Exception:
        return ""


def _to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _monitor_under(sct, x, y):
    """Pick the monitor containing (x, y). monitors[0] is the virtual union."""
    for mon in sct.monitors[1:]:
        if (
            mon["left"] <= x < mon["left"] + mon["width"]
            and mon["top"] <= y < mon["top"] + mon["height"]
        ):
            return mon
    return sct.monitors[1]


def grab():
    """Capture around the current cursor position.

    Returns (crop_b64, full_b64, meta) where meta describes the context.
    """
    x, y = cursor_pos()

    with mss.mss() as sct:
        mon = _monitor_under(sct, x, y)

        # Clamp the crop box so it stays inside the monitor.
        left = max(mon["left"], min(x - CROP_W // 2, mon["left"] + mon["width"] - CROP_W))
        top = max(mon["top"], min(y - CROP_H // 2, mon["top"] + mon["height"] - CROP_H))

        raw_crop = sct.grab(
            {"left": left, "top": top, "width": CROP_W, "height": CROP_H}
        )
        crop = Image.frombytes("RGB", raw_crop.size, raw_crop.bgra, "raw", "BGRX")

        raw_full = sct.grab(mon)
        full = Image.frombytes("RGB", raw_full.size, raw_full.bgra, "raw", "BGRX")

    # Mark the exact pointer location on the crop so the model knows what is
    # being asked about rather than guessing among neighbouring controls.
    crop = _draw_marker(crop, x - left, y - top)

    full.thumbnail((FULL_MAX_EDGE, FULL_MAX_EDGE), Image.LANCZOS)

    meta = {
        "app": foreground_app(),
        "title": foreground_title(),
        "cursor": (x, y),
    }
    return _to_b64(crop), _to_b64(full), meta


def _draw_marker(img: Image.Image, cx: int, cy: int) -> Image.Image:
    """Draw a thin crosshair ring at the pointer location."""
    from PIL import ImageDraw

    img = img.copy()
    d = ImageDraw.Draw(img)
    r = 14
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 0, 90), width=3)
    d.line([cx - r - 8, cy, cx - r - 2, cy], fill=(255, 0, 90), width=3)
    d.line([cx + r + 2, cy, cx + r + 8, cy], fill=(255, 0, 90), width=3)
    d.line([cx, cy - r - 8, cx, cy - r - 2], fill=(255, 0, 90), width=3)
    d.line([cx, cy + r + 2, cx, cy + r + 8], fill=(255, 0, 90), width=3)
    return img


if __name__ == "__main__":
    # Standalone check: run this, then look at the two PNGs it writes.
    import time

    print("Capturing in 3 seconds — put your cursor over something.")
    time.sleep(3)
    c, f, meta = grab()
    open("crop.png", "wb").write(base64.b64decode(c))
    open("full.png", "wb").write(base64.b64decode(f))
    print("Wrote crop.png and full.png")
    print("Meta:", meta)

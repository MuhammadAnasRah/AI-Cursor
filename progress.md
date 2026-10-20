# AI Cursor — Progress

## Status: prototype written, not yet run on hardware

All four modules are complete. Nothing has been executed on a real Windows
machine yet, so treat every "done" below as written-but-unverified until the
test checklist is filled in.

---

## Build steps

| # | Step | Status |
|---|---|---|
| 1 | Transparent click-through overlay with trailing glyph | Written |
| 2 | Screen capture — cursor crop + full context shot | Written |
| 3 | Model call, streaming explanation | Written |
| 4 | Bubble rendering with edge flipping and fade | Written |
| 5 | Hotkey wiring, threading, entry point | Written |

## Files

```
context.md     what this is, architecture, decisions
progress.md    this file
capture.py     mss grabs, crosshair marker, app detection
brain.py       prompt + streaming API call
overlay.py     PySide6 transparent window, glyph, bubble
main.py        hotkey listener, threading, entry point
```

---

## Install

```
pip install PySide6 mss pillow pywin32 keyboard anthropic
```

Then set the API key. In PowerShell:

```
$env:ANTHROPIC_API_KEY = "your-key-here"
```

To make it stick across sessions, use `setx ANTHROPIC_API_KEY "your-key-here"`
and open a new terminal.

---

## Test checklist

Work through these in order. Each module runs standalone, so a failure tells
you exactly which layer is broken.

### 1. Overlay alone
```
python overlay.py
```
- [ ] A pink ring appears and trails the cursor smoothly
- [ ] A test bubble is visible
- [ ] **Clicks pass through** — open Premiere or any app behind it and confirm
      buttons still respond
- [ ] The glyph tracks correctly across all monitors
- [ ] The glyph sits on the pointer, not offset (this is the DPI check)

### 2. Capture alone
```
python capture.py
```
Hover something during the 3 second countdown.
- [ ] `crop.png` is sharp and readable, not blurry
- [ ] The pink crosshair is on the thing you were hovering, not offset
- [ ] `full.png` shows the right monitor
- [ ] Printed meta shows the correct app name

### 3. Model call
```
python brain.py
```
- [ ] An explanation prints to the console
- [ ] It is about the right control
- [ ] It is two sentences, no markdown, no hedging

### 4. Everything
```
python main.py
```
Run from an **administrator** terminal.
- [ ] Hotkey fires while Premiere has focus
- [ ] Bubble appears near the pointer and streams text in
- [ ] Bubble flips inward near screen edges instead of running off
- [ ] Bubble fades after about 6 seconds
- [ ] Repeated hotkey presses during a query are ignored, not queued
- [ ] Ctrl+Shift+Q quits cleanly

---

## Likely problems and fixes

**Crosshair lands off-target on a scaled display.**
DPI awareness failed. Check that `set_dpi_aware()` runs before `QApplication`
is constructed. If it still drifts, print `GetCursorPos()` alongside the
monitor bounds from `mss` and compare.

**Hotkey does nothing while another app has focus.**
Not running as administrator. This is the single most common cause.

**Clicks are being swallowed.**
`WS_EX_TRANSPARENT` did not apply. Confirm `_make_click_through()` ran in
`showEvent`, after the native window handle exists.

**Bubble does not repaint or the glyph stutters.**
Something is blocking the Qt event loop. Verify the capture and API call are
both on the worker thread and that nothing touches widget state directly from
it — updates must go through the signals.

**Model describes the wrong button.**
Two knobs: shrink `CROP_W`/`CROP_H` in `capture.py` so there is less
competing detail, or make the crosshair marker more prominent.

**Model says it cannot tell what the icon is.**
Expected in custom-drawn apps with tiny monochrome icons. This is exactly the
quality question the prototype exists to answer.

---

## Next, once the checklist passes

Roughly in order of value:

1. **Response caching.** Hovering the same spot twice should be free. Key on a
   perceptual hash of the crop.
2. **Dwell trigger.** Fire after the pointer rests for ~800ms, as an option
   alongside the hotkey. Needs caching in place first or it burns tokens.
3. **UI Automation.** `ElementFromPoint` gives ground-truth control names in
   native apps and largely eliminates hallucination there. Deliberately
   deferred — see context.md for why.
4. **Typed follow-up.** Press a key to ask a question against the same
   capture, so "what does this do?" becomes "how do I use it to fix crushed
   blacks?". `brain.explain()` already accepts a `question` argument for this.
5. **Tray icon and settings** — hotkey binding, dwell on/off, app allowlist.
6. **App allowlist.** Only capture in chosen applications. Matters before
   anyone else runs this, given every query ships a desktop screenshot.

---

## Open decisions

- **DPI and monitor setup unconfirmed.** The code sets per-monitor v2
  awareness and picks the monitor under the cursor, which should cover
  scaling and multi-display. Step 1 and 2 of the checklist verify it.
- **Model choice.** Currently `claude-sonnet-4-5` in `brain.py`. If icon
  reading turns out weak, try a larger model and compare on the same crop.
- **Latency.** Around 1–3 seconds. Fine for a hotkey. Revisit before dwell
  mode ships.

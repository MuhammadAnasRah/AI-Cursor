# AI Cursor — Context

## What this is

A Windows overlay app. A small AI cursor glyph trails your real mouse pointer.
When you hold a hotkey while hovering over anything on screen — a button in
Premiere Pro, a panel in Blender, a menu item anywhere — it captures what's
under the cursor, sends it to a vision model, and shows a one-line explanation
in a floating bubble next to the pointer.

The Premiere example is just one case. The point is general: any UI, any app,
"what does this thing do?" answered in place without alt-tabbing to Google.

## Prototype scope

This is a **prototype**, deliberately narrow. It proves the hard parts work
before any polish gets added.

In scope:
- Transparent, click-through, always-on-top overlay
- AI cursor glyph that trails the real pointer with smoothing
- Hotkey trigger: hold `Ctrl+Shift+Space`
- Capture: native-resolution crop around cursor + downscaled full screenshot
- Model call with both images plus the foreground app's process name
- Streaming answer rendered in a bubble that flips near screen edges and fades
- `Esc` to quit

Explicitly out of scope for now:
- **UI Automation** (accessibility tree). It's the biggest accuracy win long
  term, but it doubles the surface area, and Premiere — the main target — is
  custom-drawn and returns almost nothing through UIA. Add it once vision-only
  quality is known.
- Dwell trigger (hover-and-wait). Hotkey first; it's deliberate and doesn't
  burn tokens on every idle pointer.
- Response caching, settings UI, tray icon, typed follow-up questions,
  app allowlist.

## Architecture

Four modules. Each layer is independently testable.

| File | Responsibility |
|---|---|
| `capture.py` | Screen grabs via `mss`. Finds the monitor under the cursor, crops a native-res region, downscales the full shot, base64-encodes both. Also gets the foreground process name via `pywin32`. |
| `brain.py` | Builds the message payload, calls the Anthropic API with streaming, yields text chunks. Holds the system prompt. |
| `overlay.py` | PySide6 frameless transparent window. 60Hz tick reads cursor position, lerps the glyph toward it, paints glyph + bubble. Handles bubble placement and fade. |
| `main.py` | Wires it together. Global hotkey listener on a background thread, dispatches capture → model → overlay, marshalling back to the Qt thread. |

### Data flow on a trigger

1. Hotkey fires on the listener thread.
2. `capture.grab()` returns crop b64, full b64, and app name.
3. A worker thread calls `brain.explain()`, which streams tokens.
4. Each chunk is pushed to the overlay via a Qt signal (thread-safe).
5. Bubble shows text as it arrives, then starts a fade timer once complete.

### Why these choices

- **Click-through** (`WS_EX_TRANSPARENT | WS_EX_LAYERED`) is non-negotiable —
  without it the overlay eats every click and Premiere becomes unusable.
- **Two images.** The wide shot tells the model which app and which mode it's
  looking at. The crop lets it read a 16px monochrome icon. Either alone is
  much worse than both.
- **Crop at native resolution, no downscale.** Small icons are the hard case;
  every pixel matters.
- **DPI awareness set at process start.** Without it, cursor coords and screen
  pixels diverge on any display above 100% scaling and the crop lands off
  target.
- **Threading.** Capture and the network call must never block the Qt event
  loop, or the glyph stutters and the window stops repainting.

## Known constraints

- **Custom-drawn apps** (Premiere, Photoshop, DaVinci, most games) expose
  nothing useful through accessibility APIs. Vision carries the entire load.
- **Latency** is roughly 1–3 seconds per query. Acceptable for an on-demand
  hotkey; would be painful for an aggressive dwell trigger.
- **Privacy.** Every query ships a screenshot of the desktop to an API. Fine
  for personal use. If this ever goes to other people it needs an explicit
  notice and an app allowlist.
- **Administrator.** The `keyboard` library needs elevated privileges to catch
  hotkeys while another application holds focus.

## Environment

- Windows 10/11, Python 3.10+
- `ANTHROPIC_API_KEY` set in the environment
- Run `python main.py` from an elevated terminal

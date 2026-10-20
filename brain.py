"""Builds the prompt and streams an explanation back from the model."""

import os

from anthropic import Anthropic

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 200

SYSTEM = """You explain user interface elements to someone working in a desktop application.

You receive two images:
1. A close crop around the mouse pointer. A pink crosshair ring marks the exact pointer location.
2. A downscaled screenshot of the whole screen, for context about which app and mode the user is in.

Identify the control directly under the crosshair and explain it.

Rules:
- Two sentences maximum. Be specific and concrete.
- Start by naming the control, then say what it does.
- If it has a well known keyboard shortcut in this application, add it at the end in parentheses.
- If the crosshair is not over any distinct control, say what area of the interface it is in and what that area is for.
- Never say "it appears to be" or hedge at length. If you are unsure between two things, name the more likely one and note the alternative in a few words.
- No preamble, no markdown, no bullet points. Plain sentences only."""


_client = None


def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set in the environment.")
        _client = Anthropic(api_key=key)
    return _client


def _image_block(b64):
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": b64},
    }


def explain(crop_b64, full_b64, meta, question=None):
    """Yield chunks of explanation text as they stream in."""
    app = meta.get("app", "unknown")
    title = meta.get("title", "")

    ask = question or "What is the control under the crosshair, and what does it do?"
    prompt = (
        f"Application: {app}\n"
        f"Window title: {title}\n\n"
        f"{ask}"
    )

    content = [
        {"type": "text", "text": "Close crop around the pointer:"},
        _image_block(crop_b64),
        {"type": "text", "text": "Full screen for context:"},
        _image_block(full_b64),
        {"type": "text", "text": prompt},
    ]

    client = _get_client()
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        messages=[{"role": "user", "content": content}],
    ) as stream:
        for chunk in stream.text_stream:
            yield chunk


if __name__ == "__main__":
    # Standalone check: capture, then print the answer to the console.
    import time

    import capture

    print("Capturing in 3 seconds — hover something interesting.")
    time.sleep(3)
    c, f, meta = capture.grab()
    print(f"[{meta['app']}]\n")
    for piece in explain(c, f, meta):
        print(piece, end="", flush=True)
    print()

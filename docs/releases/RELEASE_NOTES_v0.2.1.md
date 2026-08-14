# Codex Token Overlay v0.2.1

## Icon rendering fix

- Replaced the font-dependent icon glyph with a size-aware geometric `C` mark.
- The same icon renderer is now used by the Tk window, system tray and
  multi-resolution Windows ICO, so the mark remains visible at 16px tray size.
- Added an automated small-size icon visibility test.

This remains an **Unofficial / Not affiliated with OpenAI** project. The app
only reads local Codex session JSONL files, never reads `auth.json`, API keys or
`.env`, and does not make network requests at runtime.


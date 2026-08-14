# Codex Token Overlay v0.3.0

## Desktop HUD and tray language update

- Refreshed the Windows floating HUD with a compact/expanded Canvas layout,
  clearer metric hierarchy, scope switching and persistent position handling.
- Added a tray Language submenu with Auto, English and Simplified Chinese.
  The tray labels and checkmarks refresh immediately after a language change.
- Auto language follows the Windows UI language; an explicit choice is saved in
  `%LOCALAPPDATA%\\CodexTokenOverlay\\settings.json` until switched back to Auto.
- Rebuilt the unsigned, single-file Windows x64 executable with the corrected
  multi-resolution icon used by the window, tray and EXE.

## Privacy and compatibility

This is **Unofficial / Not affiliated with OpenAI** software. It only reads
local Codex session JSONL files in read-only mode, never reads `auth.json`, API
keys or `.env`, and makes no network requests while running.

The parser remains compatible with response-item call/output pairs, legacy
begin/end events and future `item_started/item_completed` wrappers. Automatic
session selection follows an eligible root user thread and excludes subagent
and memory-consolidation sessions.

## Windows asset

- `CodexTokenOverlay-v0.3.0-windows-x64.exe`
- `SHA256SUMS.txt`

The executable is not code signed; Windows SmartScreen may show a first-run
warning.

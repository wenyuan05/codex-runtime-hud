# Codex Runtime HUD v0.4.1

This patch release finalizes the session-picker interaction behavior.

## Fixed

- Clicking any area outside the session list now closes the picker consistently, including visible HUD areas and other applications.
- Removed the optional close-on-outside-click setting; this behavior is now always enabled.
- Preserved mouse-release selection handling so selecting a session does not reopen the picker.

## Privacy

**Unofficial / Not affiliated with OpenAI.** The HUD reads local rollout JSONL files only.
It does not read `auth.json`, API keys or `.env`, and makes no runtime network requests.

## Assets

- `CodexRuntimeHUD-v0.4.1-windows-x64.exe`
- `SHA256SUMS.txt`

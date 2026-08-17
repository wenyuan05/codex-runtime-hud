# Codex Runtime HUD v0.4.0

This release adds local multi-session selection for concurrent Codex work.

## Added

- A Sessions button in the floating HUD opens a scrollable local root-thread picker.
- Auto mode follows the latest eligible root user turn; Manual mode locks the selected session.
- Session rows show the session metadata project folder and short thread ID, never prompt text.
- A small isolated incremental-reader pool prevents token, Steps and tool timing state from crossing between sessions.
- The tray menu mirrors the session picker as an alternative entry point.

## Privacy

**Unofficial / Not affiliated with OpenAI.** The HUD reads local rollout JSONL files only.
It does not read `auth.json`, API keys or `.env`, and makes no runtime network requests.

## Assets

- `CodexRuntimeHUD-v0.4.0-windows-x64.exe`
- `SHA256SUMS.txt`

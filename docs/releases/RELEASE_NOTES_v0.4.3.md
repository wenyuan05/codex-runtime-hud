# Codex Runtime HUD v0.4.3

## Changes

- Added **Hide window** to the HUD's native right-click menu.
- Added a persistent global Show/Hide shortcut that works while another application has focus and while the HUD is hidden.
- Added shortcut selectors to both the HUD context menu and the tray menu:
  - `Ctrl+Alt+H` (default)
  - `Ctrl+Shift+H`
  - `Alt+Shift+H`
  - Disabled
- If Windows reports that a shortcut is already registered, the HUD keeps the previous setting and shows a conflict message.
- Added 5h and Weekly remaining-allowance bars with reset countdowns to the expanded HUD. They use the latest local rollout `rate_limits` snapshot and do not make an API request.
- Identify quota windows by `window_minutes`, because Codex may expose Weekly as `primary` when the 5h window is absent.
- Increased the minimum expanded height to keep quota data readable without crowding the runtime metrics.
- Corrected the embedded Windows numeric file/product version to match `0.4.3`.

## Privacy

The shortcut implementation uses the local Windows `RegisterHotKey` API. It does not install a keyboard hook, record keystrokes, or add network access. The selected shortcut is stored in `%LOCALAPPDATA%\CodexRuntimeHUD\settings.json`.

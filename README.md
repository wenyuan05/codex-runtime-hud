# Codex Runtime HUD

[中文说明](README.zh-CN.md)

![Demo](assets/codex-runtime-hud-demo.gif)

> **Unofficial / Not affiliated with OpenAI.**

A Windows always-on-top HUD focused on real-time, single-turn performance for Codex Desktop / Codex CLI. By default it follows local root-user rollout JSONL only; an opt-in high-accuracy quota mode can ask the installed Codex CLI for current account limits.

Next release: **v0.4.5**. Standard Codex 5h and weekly quotas now follow the newest account-wide local snapshot instead of the selected task, and other limit families such as `gpt-reserve` can no longer replace them. An optional higher-accuracy source reads the current `codex` bucket through the local Codex App Server and automatically falls back to rollout aggregation.

## What it monitors

The default view is the current turn, not a historical dashboard. While a turn is running, the HUD surfaces LLM elapsed time, TTFT, tool time, Steps, token speed, input/output tokens, cache hit and context usage. Session cumulative metrics remain available as a secondary comparison view.

## Privacy

- Read-only access to local Codex session files under `~/.codex/sessions` and `~/.codex/archived_sessions`.
- Does **not** read `auth.json`, API keys, `.env` files, prompts outside the rollout file, or credentials.
- Default mode makes no network connections. GitHub, Python and PyInstaller are only used for distribution/building.
- **High-accuracy quotas (opt-in):** the HUD starts the installed [Codex App Server](https://developers.openai.com/codex/app-server) as a local child process and requests `account/rateLimits/read` every 10 seconds. Codex performs the authenticated account request; the HUD does not read, receive or store its credentials. Turning the option off stops that owned child process.
- Settings contain only window coordinates and UI preferences, including the selected global shortcut: `%LOCALAPPDATA%\CodexRuntimeHUD\settings.json`.
  UI preferences include `expanded`, `scope`, `language` (`auto`, `en`, `zh-CN`), `always_on_top`, `toggle_hotkey`, `high_accuracy_quotas` and local session-selection mode. The session picker always closes when clicking outside it. `Auto` follows the Windows UI language; an explicit English/Chinese choice is remembered until changed back to `Auto`.
- Existing settings from `%LOCALAPPDATA%\CodexTokenOverlay\settings.json` are read as a one-way compatibility fallback; new saves use the `CodexRuntimeHUD` folder.

Quota percentages are account-wide. In compatible default mode, the HUD combines the newest standard `limit_id=codex` 5h and weekly observations across eligible local root rollouts, so manually selecting another task does not freeze or replace them. Other limit families are intentionally ignored. When high-accuracy quotas are enabled, the live `rateLimitsByLimitId.codex` windows take precedence independently; if Codex is unavailable, signed out, or a live window is missing, the corresponding rollout value remains visible as the fallback.

### Session status limitations

Session status is inferred only from local rollout lifecycle events. `Active` means the latest root turn has started without a matching `task_complete`, `turn_complete` or abort event and the rollout was written recently. A newer turn supersedes an unmatched older turn, and duplicate rollout files for the same stable thread are merged in the picker. Codex may pause without appending JSONL, so a quiet unfinished turn is shown as **Running (waiting for update)** in blue. If no new write is observed for 24 hours, it is treated as **Idle** to prevent interrupted historical rollouts from appearing active forever. The HUD also cannot know which Desktop tab currently has focus.

## Download

Download the latest portable Windows x64 executable from [Releases](https://github.com/wenyuan05/codex-runtime-hud/releases). The historical v0.3.1 asset keeps its legacy filename; new builds use the `CodexRuntimeHUD` name. The executable is unsigned, so SmartScreen may show a first-run warning.

Verify the download with `SHA256SUMS.txt`:

```powershell
Get-FileHash .\CodexRuntimeHUD.exe -Algorithm SHA256
```

Double-click the EXE. The compact HUD shows a Sessions button, scope, Cache, In and Out; click the body to expand the detailed panel. The expanded view also shows remaining 5h and Weekly allowance plus reset countdowns. A missing quota window is shown as `—`. Click Sessions to open a scrollable local root-session list. `Follow automatically` keeps the stable latest-root behavior; selecting a session locks the HUD to that session until you select Auto again. Session rows use only the local `cwd` project folder plus a short thread ID, never prompt text. The picker always closes when clicking outside it. Click Current/Session to switch scope without expanding. Drag from the background to move it; drag the diagonal handle in the lower-right corner to resize it. Compact and expanded mode sizes are remembered separately. A right-click opens the native menu for Hide window, scope, sessions, Always on top, startup, **High-accuracy quotas (Codex online)**, the global Show/Hide shortcut, language, reset position, copy and Quit. The tray icon provides the same quota and shortcut settings alongside Sessions, Show/Hide, Start with Windows, Language, About and Quit. High-accuracy quotas are disabled by default and require an installed, signed-in Codex CLI. Choose `Ctrl+Alt+H` (default), `Ctrl+Shift+H`, `Alt+Shift+H`, or Disabled. If another application already owns a shortcut, the HUD keeps the previous setting and reports the conflict. Startup is opt-in and uses the current user's registry only. Position and UI preferences persist across launches.

## Run from source

Python 3.10+ with Tk is required:

```powershell
py -3 -m pip install -r requirements-runtime.txt
py -3 codex_runtime_hud.py
py -3 codex_runtime_hud.py --once --debug
py -3 codex_runtime_hud.py --once --file .\examples\sample_rollout.jsonl --lang en
```

Language defaults to the Windows UI language (`zh-*` → Simplified Chinese, otherwise English). Override with `--lang auto`, `--lang zh-CN` or `--lang en`.

## Build

On Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build.ps1
```

The result is `dist\CodexRuntimeHUD.exe` plus `dist\SHA256SUMS.txt`. The same checks run in GitHub Actions.

## Controls and metrics

- Click the body or press Space: expand/collapse.
- Click Sessions: choose an eligible local root thread, or return to automatic following.
- Drag the body: move and persist the HUD position.
- Click Turn/Session: switch current-turn or cumulative-session metrics.
- Middle-click/Ctrl+C: copy visible text. Right-click opens the native settings menu; Escape hides to the tray.
- `Ctrl+Alt+H`: show or hide the HUD globally; change or disable it from Show/Hide shortcut in the context or tray menu.
- High-accuracy quotas: disabled by default; enable from the context or tray menu to refresh the account-level standard Codex bucket through the installed Codex CLI, with automatic rollout fallback.
- 5h/Weekly windows are identified by `window_minutes`, not by `primary`/`secondary` order; both percentage and bar represent the remaining allowance.
- Cache hit is `cached_input_tokens / input_tokens`.
- Current-turn usage prefers exact `raw_response_completed` usage and otherwise uses cumulative deltas. A non-zero cumulative counter regression starts a new accounting epoch so resumed rollouts remain countable across restarts.
- Tool time is an interval union, so overlapping tools are not double-counted.
- Tool events are normalized from response-item call/output pairs, legacy begin/end events, and future `item_started/item_completed` wrappers.
- Automatic selection follows the latest eligible root user thread and excludes subagent/memory-consolidation sessions. A manual selection is locked until switched back to Auto; `--file` overrides both modes.
- Session status is an estimate from persisted events, not a process monitor; blue **Running (waiting for update)** means “the latest turn is unfinished but recently quiet,” not a guarantee that the task is still executing. Unmatched turns with no writes for 24 hours are treated as idle.
- Large rollouts are scanned incrementally for turn metadata, so a newer turn in the middle of a file is not mistaken for stale startup data.
- Token usage remains pending until Codex persists a meaningful `token_count` or response-usage event; an all-zero fill snapshot is not treated as real zero-token usage.

## License

MIT. See [LICENSE](LICENSE).

## Repository layout

- `codex_runtime_hud.py`, `overlay_ui.py`, `app_server_quota.py`, `icon_assets.py`: application source.
- `tests/`: parser, icon and UI-settings unit tests.
- `scripts/`: build, launcher and demo-capture scripts.
- `packaging/`: PyInstaller spec and Windows version metadata.
- `docs/releases/`: versioned release notes.
- `examples/`: safe sample rollout used by tests and CLI smoke tests.

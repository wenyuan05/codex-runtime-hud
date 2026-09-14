# Codex Runtime HUD v0.4.5

## Fixed

- Fixed the 5h quota disappearing and the weekly quota appearing frozen when the selected task starts emitting another limit family such as `base_model_inference / gpt-reserve`.
- Source the standard Codex 5h and weekly windows from the newest account-wide observations across eligible local root rollouts instead of tying them to the task displayed in the HUD.
- Keep the two standard windows independent, so a newer weekly-only snapshot cannot erase the latest 5h observation.
- Include newer quota snapshots from archived root rollouts without adding archived tasks to the picker while current sessions exist.
- Show live account quotas even when no eligible local rollout is available.
- Correct current-turn token totals when the first turn contains multiple cumulative usage snapshots, and keep exact response usage visible in the session view until the next cumulative snapshot arrives.
- Update the active turn's model label when Codex applies new settings or reroutes the model.
- Show the localized error dialog when a configured global shortcut is already occupied.

## Added

- Added an opt-in **High-accuracy quotas (Codex online)** source. It reads the standard account bucket through the installed local Codex App Server every 10 seconds and reacts to quota update notifications.
- Kept rollout aggregation as the default and as an automatic per-window fallback when the optional source is unavailable or incomplete.
- The HUD never reads Codex credentials; the complete owned App Server process tree is stopped when the option is disabled or the HUD exits, including installations launched through `codex.cmd`.

## Validation

- All 40 unit tests pass, including regressions for mixed rate-limit families, current and archived cross-rollout aggregation, App Server camelCase fields, multi-bucket selection, per-window fallback, token accounting, model reroutes, shortcut conflicts and Windows process-tree shutdown.
- The Windows single-file EXE builds successfully, contains both `overlay_ui` and `app_server_quota`, and passes the packaged CLI smoke test.
- Replayed the reported `01a07014` task while another root rollout contained the latest standard Codex allowance; the HUD resolved both current windows even though the selected task only contained a weekly `gpt-reserve` snapshot.
- Compared a live App Server read with the Codex app's account usage result; both selected the same standard 5h/weekly windows and reset timestamps.

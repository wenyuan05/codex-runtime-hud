# Codex Runtime HUD v0.4.5

## Fixed

- Fixed the 5h quota disappearing and the weekly quota appearing frozen when the selected task starts emitting another limit family such as `base_model_inference / gpt-reserve`.
- Source the standard Codex 5h and weekly windows from the newest account-wide observations across eligible local root rollouts instead of tying them to the task displayed in the HUD.
- Keep the two standard windows independent, so a newer weekly-only snapshot cannot erase the latest 5h observation.

## Added

- Added an opt-in **High-accuracy quotas (Codex online)** source. It reads the standard account bucket through the installed local Codex App Server every 10 seconds and reacts to quota update notifications.
- Kept rollout aggregation as the default and as an automatic per-window fallback when the optional source is unavailable or incomplete.
- The HUD never reads Codex credentials; the owned App Server child process is stopped when the option is disabled or the HUD exits.

## Validation

- Added regressions for mixed rate-limit families, cross-rollout quota aggregation, App Server camelCase fields, multi-bucket selection and per-window fallback.
- Replayed the reported `01a07014` task while another root rollout contained the latest standard Codex allowance; the HUD resolved both current windows even though the selected task only contained a weekly `gpt-reserve` snapshot.
- Compared a live App Server read with the Codex app's account usage result; both selected the same standard 5h/weekly windows and reset timestamps.

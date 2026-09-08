# Codex Runtime HUD v0.4.5

## Fixed

- Fixed the 5h quota disappearing and the weekly quota appearing frozen when the selected task starts emitting another limit family such as `base_model_inference / gpt-reserve`.
- Source the standard Codex 5h and weekly windows from the newest account-wide observations across eligible local root rollouts instead of tying them to the task displayed in the HUD.
- Keep the two standard windows independent, so a newer weekly-only snapshot cannot erase the latest 5h observation.

## Validation

- Added regressions for mixed rate-limit families and cross-rollout quota aggregation.
- Replayed the reported `01a07014` task while another root rollout contained the latest standard Codex allowance; the HUD resolved both current windows even though the selected task only contained a weekly `gpt-reserve` snapshot.

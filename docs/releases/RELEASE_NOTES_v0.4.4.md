# Codex Runtime HUD v0.4.4

## Fixed

- Fixed Cache, In, Out, Speed, and Reasoning showing `— / 0 / 0 / — / 0` after a long-lived rollout resumes with a lower non-zero cumulative token counter.
- Convert raw `total_token_usage` snapshots into a logical monotonic total across accounting resets instead of permanently rejecting every later snapshot below the historical maximum.
- Keep an all-zero synthetic/fill `token_count` snapshot in the pending state rather than presenting it as real zero-token usage.

## Validation

- Added regressions for a non-zero cumulative reset and a zero fill snapshot.
- Replayed the reported multi-day MyBlog rollout: the affected turn now resolves to Input `1,375,603`, Cached `1,261,440`, Output `7,063`, and Cache hit `91.7%`, while preserving its 24 Steps and timing metrics.

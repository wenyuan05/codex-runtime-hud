# Codex Token Overlay v0.3.1

## Root-thread selection fix

- Fixed startup selection for large Codex rollout files. The previous
  head/tail metadata sample could miss a newer `task_started` in the middle of
  a long file and show the previous session's unchanged metrics.
- Added a cached incremental metadata reader: the first scan reads only
  lightweight session metadata and later refreshes process appended bytes.
- Handles appended lines, unterminated final lines, file replacement and
  truncation without retaining rollout contents.
- Added regression tests for a large rollout with a middle `task_started` and
  for appended turn metadata.

This is **Unofficial / Not affiliated with OpenAI** software. It only reads
local Codex session JSONL files in read-only mode, never reads `auth.json`, API
keys or `.env`, and makes no network requests while running.

## Windows assets

- `CodexTokenOverlay-v0.3.1-windows-x64.exe`
- `SHA256SUMS.txt`

The executable is not code signed; Windows SmartScreen may show a first-run
warning.

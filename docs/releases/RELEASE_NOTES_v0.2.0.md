# Codex Token Overlay v0.2.0

> **Unofficial / Not affiliated with OpenAI.**

This compatibility release normalizes current Codex Desktop rollout events while retaining legacy and forward-compatible parsing.

Highlights:

- Pairs `response_item` tool calls with their outputs to measure tool time.
- Supports legacy begin/end events and future `item_started/item_completed` tool wrappers.
- Deduplicates repeated response usage and keeps TokenCount as the cumulative fallback.
- Excludes subagent and memory-consolidation sessions from automatic root-thread selection.
- Follows newer root user turns without jumping between ordinary background mtime updates.
- Keeps portable single-file Windows x64 distribution, tray controls, startup opt-in and position memory.

Privacy remains unchanged: read-only local session JSONL, no `auth.json`, API keys, `.env` files or application network access.

Asset: `CodexTokenOverlay-v0.2.0-windows-x64.exe`

The executable is unsigned. Verify it with `SHA256SUMS.txt`; Windows SmartScreen may show a first-run warning.

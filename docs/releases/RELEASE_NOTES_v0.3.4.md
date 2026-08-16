# Codex Runtime HUD v0.3.4

This patch release fixes compact/expanded window positioning at screen edges.

## Fixed

- Remember the compact HUD anchor before expanding.
- Restore the original compact position after collapsing, even when the
  expanded layout was clamped left because the HUD was near the right edge.
- Keep compact position memory independent from temporary expanded-layout
  movement.

The release remains an unofficial Windows x64 desktop overlay:
**Unofficial / Not affiliated with OpenAI**.
It only reads local Codex session JSONL files in read-only mode, does not read
`auth.json`, API keys or `.env`, and does not connect to the network at runtime.

## Assets

- `CodexRuntimeHUD-v0.3.4-windows-x64.exe`
- `SHA256SUMS.txt`

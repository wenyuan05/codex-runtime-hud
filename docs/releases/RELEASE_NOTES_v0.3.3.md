# Codex Runtime HUD v0.3.3

## Faster startup

- The first HUD paint is no longer blocked by the initial rollout-tree scan;
  session discovery starts as soon as Tk enters its event loop.
- The Windows single-file build keeps only the Windows pystray backend and
  excludes the unused NumPy dependency, reducing the local EXE from roughly
  31.8 MB to 20.7 MB and shortening extraction work at launch.
- Metrics, privacy boundaries and rollout parsing remain unchanged.

This is **Unofficial / Not affiliated with OpenAI** software. It only reads
local Codex session JSONL files in read-only mode, never reads `auth.json`, API
keys or `.env`, and makes no network requests while running.

## Windows assets

- `CodexRuntimeHUD-v0.3.3-windows-x64.exe`
- `SHA256SUMS.txt`

The executable is not code signed; Windows SmartScreen may show a first-run
warning.

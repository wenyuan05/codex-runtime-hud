# PyInstaller single-file Windows build. scripts/build.ps1 creates build/codex-token-overlay.ico first.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
hiddenimports = collect_submodules("pystray") + ["overlay_ui"]

a = Analysis([str(root / "codex_hud.py")], pathex=[str(root)], hiddenimports=hiddenimports,
             datas=[], binaries=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="CodexTokenOverlay",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          console=False, disable_windowed_traceback=False,
          icon=str(root / "build" / "codex-token-overlay.ico"),
          version=str(root / "packaging" / "version_info.txt"))

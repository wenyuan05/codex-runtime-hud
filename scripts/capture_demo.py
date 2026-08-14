"""Capture the real Tk HUD into a small README GIF on Windows."""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "demo.gif"
user32 = ctypes.windll.user32


def find_window(title: str) -> int:
    found: list[int] = []
    enum = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value == title:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(enum(callback), 0)
    return found[0] if found else 0


def grab(hwnd: int):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    print("window", hwnd, rect.left, rect.top, rect.right, rect.bottom)
    return ImageGrab.grab(window=hwnd).convert("RGB")


def main() -> int:
    if sys.platform != "win32":
        print("Windows only", file=sys.stderr)
        return 2
    proc = subprocess.Popen([sys.executable, str(ROOT / "codex_hud.py"), "--file", str(ROOT / "sample_rollout.jsonl"), "--lang", "en"])
    try:
        hwnd = 0
        for _ in range(40):
            hwnd = find_window("Codex Token Overlay")
            if hwnd:
                break
            time.sleep(0.1)
        if not hwnd:
            raise RuntimeError("HUD window not found")
        time.sleep(0.5)
        frames = [grab(hwnd)]
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(0x20, 0, 0, 0)  # Space
        user32.keybd_event(0x20, 0, 2, 0)
        time.sleep(0.5)
        frames.append(grab(hwnd))
        width = max(frame.width for frame in frames)
        height = max(frame.height for frame in frames)
        canvas = [Image.new("RGB", (width, height), (27, 27, 29)) for _ in frames]
        canvas[0].paste(frames[0], (0, 0)); canvas[1].paste(frames[1], (0, 0))
        canvas[0].save(OUT, save_all=True, append_images=[canvas[1]], duration=[1200, 1800], loop=0, optimize=True)
        print(OUT)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())

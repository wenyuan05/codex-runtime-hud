"""Capture the real Tk HUD into a small README GIF on Windows."""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "codex-runtime-hud-demo.gif"
user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
TRANSPARENT_RGB = (1, 1, 1)
DEMO_BACKGROUND = (27, 27, 29)


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
    image = ImageGrab.grab(window=hwnd).convert("RGB")
    # ImageGrab(window=...) reads the Tk backing surface and therefore sees
    # the Windows transparent-color key.  Replace that capture-only color so
    # the repository GIF shows the same rounded silhouette users see on the
    # desktop, without leaking the key color into the demo.
    pixels = [DEMO_BACKGROUND if pixel == TRANSPARENT_RGB else pixel for pixel in image.getdata()]
    image.putdata(pixels)
    return image


def grab_scene(hwnd: int, extra_height: int = 0):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom + extra_height)).convert("RGB")
    pixels = [DEMO_BACKGROUND if pixel == TRANSPARENT_RGB else pixel for pixel in image.getdata()]
    image.putdata(pixels)
    return image


def click_window(hwnd: int, x: int, y: int) -> None:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    user32.SetCursorPos(rect.left + int(x), rect.top + int(y))
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def main() -> int:
    if sys.platform != "win32":
        print("Windows only", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="codex-runtime-hud-demo-") as temp:
        demo_home = Path(temp)
        sessions = demo_home / "sessions"
        sessions.mkdir()
        rollout = sessions / "rollout-demo.jsonl"
        meta = {"type": "session_meta", "payload": {"thread_source": "user", "originator": "Codex Desktop", "id": "demo-thread", "cwd": "C:/DemoProject"}}
        sample = (ROOT / "examples" / "sample_rollout.jsonl").read_text(encoding="utf-8")
        rollout.write_text(json.dumps(meta) + "\n" + sample, encoding="utf-8")
        proc = subprocess.Popen([sys.executable, str(ROOT / "codex_runtime_hud.py"), "--codex-home", str(demo_home), "--lang", "en"])
        try:
            hwnd = 0
            for _ in range(40):
                hwnd = find_window("Codex Runtime HUD")
                if hwnd:
                    break
                time.sleep(0.1)
            if not hwnd:
                raise RuntimeError("HUD window not found")
            time.sleep(0.5)
            frames = [grab(hwnd)]
            user32.SetForegroundWindow(hwnd)
            # Compact mode places the scope switch on the right; click the open
            # body area so the demo expands instead of changing scope.
            click_window(hwnd, 110, 20)
            time.sleep(0.5)
            frames.append(grab(hwnd))
            # Show the real session picker, then demonstrate its fixed outside
            # click behavior by clicking the expanded HUD behind/above it.
            click_window(hwnd, 60, 18)
            time.sleep(0.5)
            frames.append(grab_scene(hwnd, extra_height=360))
            click_window(hwnd, 250, 45)
            time.sleep(0.5)
            frames.append(grab(hwnd))
            width = max(frame.width for frame in frames)
            height = max(frame.height for frame in frames)
            canvas = [Image.new("RGB", (width, height), DEMO_BACKGROUND) for _ in frames]
            for target, source in zip(canvas, frames):
                target.paste(source, (0, 0))
            canvas[0].save(OUT, save_all=True, append_images=canvas[1:], duration=[1100, 1300, 1600, 1300], loop=0, optimize=True)
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

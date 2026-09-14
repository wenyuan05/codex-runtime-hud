import ctypes
import os
import subprocess
import sys
import tempfile
import time
import unittest
from ctypes import wintypes
from pathlib import Path

from app_server_quota import CodexAppServerQuotaClient


@unittest.skipUnless(os.name == "nt", "Windows process-tree behavior")
class AppServerQuotaTests(unittest.TestCase):
    @staticmethod
    def process_running(pid: int) -> bool:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x00000102  # WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)

    def test_terminate_stops_launcher_process_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            child_pid_path = base / "child.pid"
            launcher_path = base / "launcher.py"
            launcher_path.write_text(
                "import subprocess, sys\n"
                "from pathlib import Path\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                "Path(sys.argv[1]).write_text(str(child.pid), encoding='utf-8')\n"
                "child.wait()\n",
                encoding="utf-8",
            )
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            launcher = subprocess.Popen(
                [sys.executable, str(launcher_path), str(child_pid_path)],
                creationflags=creationflags,
            )
            child_pid = None
            try:
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and not child_pid_path.exists():
                    time.sleep(0.02)
                self.assertTrue(child_pid_path.exists(), "launcher did not create its child")
                child_pid = int(child_pid_path.read_text(encoding="utf-8"))
                self.assertTrue(self.process_running(child_pid))

                CodexAppServerQuotaClient._terminate(launcher)
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline and self.process_running(child_pid):
                    time.sleep(0.02)
                self.assertFalse(self.process_running(child_pid))
            finally:
                if launcher.poll() is None:
                    subprocess.run(
                        ["taskkill", "/PID", str(launcher.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                        creationflags=creationflags,
                    )
                elif child_pid is not None and self.process_running(child_pid):
                    subprocess.run(
                        ["taskkill", "/PID", str(child_pid), "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                        creationflags=creationflags,
                    )


if __name__ == "__main__":
    unittest.main()

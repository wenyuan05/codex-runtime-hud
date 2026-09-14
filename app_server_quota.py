"""Optional account quota reader backed by the local Codex App Server.

The HUD remains rollout-only by default.  When the user opts in, this module
starts the installed ``codex`` executable as an owned child process and uses
its stable JSONL app-server protocol.  Authentication stays inside Codex; this
module never reads or receives credential files.
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class AppServerQuotaSnapshot:
    result: Optional[dict[str, Any]] = None
    updated_at: Optional[float] = None
    connected: bool = False
    error: str = ""


class CodexAppServerQuotaClient:
    """Read ChatGPT Codex quotas without blocking the Tk event loop."""

    def __init__(
        self,
        poll_interval: float = 10.0,
        request_timeout: float = 20.0,
        retry_delay: float = 15.0,
        client_version: str = "unknown",
    ) -> None:
        self.poll_interval = max(1.0, float(poll_interval))
        self.request_timeout = max(1.0, float(request_timeout))
        self.retry_delay = max(1.0, float(retry_delay))
        self.client_version = str(client_version)
        self._snapshot = AppServerQuotaSnapshot()
        self._snapshot_lock = threading.Lock()
        self._process: Optional[subprocess.Popen[str]] = None
        self._process_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        thread = self._thread
        if thread is not None and thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="codex-overlay-account-quota",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._process_lock:
            process = self._process
        if process is not None:
            self._terminate(process)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        if thread is None or not thread.is_alive():
            self._thread = None
        with self._snapshot_lock:
            self._snapshot = AppServerQuotaSnapshot()

    def snapshot(self) -> AppServerQuotaSnapshot:
        with self._snapshot_lock:
            return self._snapshot

    def _publish(self, result: dict[str, Any]) -> None:
        with self._snapshot_lock:
            self._snapshot = AppServerQuotaSnapshot(
                result=result,
                updated_at=time.time(),
                connected=True,
            )

    def _set_connected(self) -> None:
        with self._snapshot_lock:
            previous = self._snapshot
            self._snapshot = AppServerQuotaSnapshot(
                result=previous.result,
                updated_at=previous.updated_at,
                connected=True,
            )

    def _set_error(self, error: str) -> None:
        with self._snapshot_lock:
            # Drop a failed live value so callers immediately fall back to the
            # compatible rollout source instead of keeping an unbounded stale
            # account snapshot.
            self._snapshot = AppServerQuotaSnapshot(error=error)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._run_connection()
            except Exception as exc:
                if not self._stop.is_set():
                    self._set_error(str(exc))
            if not self._stop.is_set():
                self._stop.wait(self.retry_delay)

    def _run_connection(self) -> None:
        executable = shutil.which("codex")
        if not executable:
            raise RuntimeError("codex executable not found")

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [executable, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        with self._process_lock:
            self._process = process

        messages: queue.Queue[Optional[str]] = queue.Queue()

        def read_stdout() -> None:
            try:
                if process.stdout is not None:
                    for line in process.stdout:
                        messages.put(line)
            finally:
                messages.put(None)

        reader = threading.Thread(
            target=read_stdout,
            daemon=True,
            name="codex-overlay-account-quota-reader",
        )
        reader.start()

        try:
            self._send(process, {
                "method": "initialize",
                "id": 0,
                "params": {
                    "clientInfo": {
                        "name": "codex_runtime_hud",
                        "title": "Codex Runtime HUD",
                        "version": self.client_version,
                    }
                },
            })
            initialized = self._wait_for_response(messages, 0, self.request_timeout)
            if initialized.get("error") is not None:
                raise RuntimeError(self._error_text(initialized["error"]))
            self._send(process, {"method": "initialized", "params": {}})
            self._set_connected()

            request_id = 1
            pending_id: Optional[int] = None
            pending_deadline = 0.0
            next_request = time.monotonic()

            while not self._stop.is_set():
                now = time.monotonic()
                if pending_id is None and now >= next_request:
                    pending_id = request_id
                    request_id += 1
                    pending_deadline = now + self.request_timeout
                    self._send(process, {"method": "account/rateLimits/read", "id": pending_id})

                if pending_id is not None and time.monotonic() >= pending_deadline:
                    raise TimeoutError("account/rateLimits/read timed out")

                try:
                    line = messages.get(timeout=0.25)
                except queue.Empty:
                    if process.poll() is not None:
                        raise RuntimeError(f"codex app-server exited ({process.returncode})")
                    continue
                if line is None:
                    raise RuntimeError(f"codex app-server exited ({process.poll()})")

                message = self._decode(line)
                if message is None:
                    continue
                if pending_id is not None and message.get("id") == pending_id:
                    if message.get("error") is not None:
                        raise RuntimeError(self._error_text(message["error"]))
                    result = message.get("result")
                    if not isinstance(result, dict):
                        raise RuntimeError("account/rateLimits/read returned no result")
                    self._publish(result)
                    pending_id = None
                    next_request = time.monotonic() + self.poll_interval
                    continue

                if message.get("method") == "account/rateLimits/updated":
                    params = message.get("params")
                    if isinstance(params, dict):
                        self._publish(params)
                    # Refresh the full multi-bucket view as soon as possible;
                    # notifications may contain only the compatibility bucket.
                    if pending_id is None:
                        next_request = time.monotonic()
        finally:
            with self._process_lock:
                if self._process is process:
                    self._process = None
            self._terminate(process)

    def _wait_for_response(
        self,
        messages: queue.Queue[Optional[str]],
        response_id: int,
        timeout: float,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while not self._stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("codex app-server initialize timed out")
            try:
                line = messages.get(timeout=min(0.25, remaining))
            except queue.Empty:
                continue
            if line is None:
                raise RuntimeError("codex app-server exited during initialize")
            message = self._decode(line)
            if message is not None and message.get("id") == response_id:
                return message
        raise RuntimeError("codex app-server stopped")

    @staticmethod
    def _decode(line: str) -> Optional[dict[str, Any]]:
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _send(process: subprocess.Popen[str], message: dict[str, Any]) -> None:
        if process.stdin is None:
            raise RuntimeError("codex app-server stdin unavailable")
        process.stdin.write(json.dumps(message, ensure_ascii=True, separators=(",", ":")) + "\n")
        process.stdin.flush()

    @staticmethod
    def _error_text(error: Any) -> str:
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "app-server request failed")
        return str(error or "app-server request failed")

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if sys.platform == "win32":
            try:
                # npm installations commonly expose codex through codex.cmd.
                # Killing only that wrapper can leave its App Server child
                # alive, so terminate the complete owned process tree.
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2.0,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                process.wait(timeout=1.0)
                return
            except Exception:
                pass
        try:
            process.terminate()
            process.wait(timeout=1.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

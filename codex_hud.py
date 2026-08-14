#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex Token Overlay v0.1.0

Read-only floating HUD for Codex Desktop / Codex CLI rollout JSONL files.

v0.3 UI:
- Default scope is the latest/current turn, not the whole session.
- Supports Codex v1 wire names task_started / task_complete.
- Current-turn tokens prefer exact raw_response_completed usage; otherwise
  fall back to cumulative token-count deltas.
- Tool time uses interval union where possible, so overlapping tool calls
  are not double-counted.
- Compact always-on-top window shows only cache hit and input/output tokens.
- Single click expands/collapses full metrics.
- Scope button switches current turn vs session cumulative metrics.

No network access, no API key, no modification of Codex state.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import locale
import math
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# -----------------------------
# Basic helpers
# -----------------------------

def codex_home_default() -> Path:
    override = os.environ.get("CODEX_HOME")
    return Path(override).expanduser() if override else Path.home() / ".codex"


APP_NAME = "CodexTokenOverlay"
APP_VERSION = "0.1.0"


def app_data_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    return Path(root) / APP_NAME


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def load_settings() -> dict[str, Any]:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_settings(data: dict[str, Any]) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def language_from_system() -> str:
    """Return zh-CN for Chinese Windows UI, otherwise en."""
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        # Primary language id 0x04 is Chinese (all Chinese Windows locales).
        if (int(lang_id) & 0x3FF) == 0x04:
            return "zh-CN"
    except (AttributeError, OSError):
        pass
    try:
        name = locale.getlocale()[0] or locale.getdefaultlocale()[0] or ""
    except (ValueError, AttributeError):
        name = ""
    return "zh-CN" if name.lower().startswith("zh") else "en"


def resolve_language(value: str) -> str:
    value = (value or "auto").lower()
    if value in {"zh", "zh-cn", "zh_cn"}:
        return "zh-CN"
    if value in {"en", "en-us", "en_gb", "en-us"}:
        return "en"
    return language_from_system()


TRANSLATIONS = {
    "zh-CN": {
        "title": "Codex Token Overlay",
        "turn": "本轮",
        "session": "累计",
        "cache": "缓存",
        "input": "入",
        "output": "出",
        "not_found": "未找到 Codex rollout",
        "unofficial": "Unofficial / Not affiliated with OpenAI",
        "show": "显示窗口",
        "hide": "隐藏窗口",
        "startup": "开机启动",
        "about": "关于",
        "quit": "退出",
        "copy": "复制当前信息",
        "language": "语言：中文",
        "invalid_rollout": "未找到 rollout JSONL：{home}",
        "tk_missing": "Tkinter 不可用。可先用 --once，或安装带 Tk 的 Python。",
    },
    "en": {
        "title": "Codex Token Overlay",
        "turn": "Turn",
        "session": "Session",
        "cache": "Cache",
        "input": "In",
        "output": "Out",
        "not_found": "No Codex rollout found",
        "unofficial": "Unofficial / Not affiliated with OpenAI",
        "show": "Show window",
        "hide": "Hide window",
        "startup": "Start with Windows",
        "about": "About",
        "quit": "Quit",
        "copy": "Copy visible text",
        "language": "Language: English",
        "invalid_rollout": "No rollout JSONL found: {home}",
        "tk_missing": "Tkinter is unavailable. Use --once or install Python with Tk.",
    },
}


def tr(lang: str, key: str, **kwargs: Any) -> str:
    text = TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)
    return text.format(**kwargs)


def as_num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def parse_ts(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        x = float(value)
        return x / 1000.0 if x > 10_000_000_000 else x
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        try:
            return parse_ts(float(s))
        except ValueError:
            return None


def parse_duration_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        if "secs" in value or "nanos" in value:
            return as_num(value.get("secs")) + as_num(value.get("nanos")) / 1e9
        if "seconds" in value or "nanoseconds" in value:
            return as_num(value.get("seconds")) + as_num(value.get("nanoseconds")) / 1e9
        if "duration_ms" in value:
            return as_num(value.get("duration_ms")) / 1000.0
        if "ms" in value:
            return as_num(value.get("ms")) / 1000.0
    if isinstance(value, str):
        s = value.strip().lower()
        try:
            return float(s)
        except ValueError:
            pass
        total = 0.0
        matched = False
        for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(ms|h|m|s)", s):
            matched = True
            total += float(amount) * {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}[unit]
        return total if matched else None
    return None


def fmt_num(n: float) -> str:
    n = float(n)
    a = abs(n)
    if a >= 100_000_000:
        return f"{n/1_000_000:.1f}M"
    if a >= 1_000_000:
        return f"{n/1_000_000:.2f}M".rstrip("0").rstrip(".")
    if a >= 100_000:
        return f"{n/1_000:.0f}K"
    if a >= 10_000:
        return f"{n/1_000:.1f}K"
    if a >= 1_000:
        return f"{n/1_000:.2f}K".rstrip("0").rstrip(".")
    return str(int(round(n)))


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


# -----------------------------
# Usage / tool / turn models
# -----------------------------

@dataclass
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_obj(cls, obj: Any) -> "Usage":
        if not isinstance(obj, dict):
            return cls()
        return cls(
            input_tokens=as_int(obj.get("input_tokens")),
            cached_input_tokens=as_int(obj.get("cached_input_tokens")),
            cache_write_input_tokens=as_int(obj.get("cache_write_input_tokens")),
            output_tokens=as_int(obj.get("output_tokens")),
            reasoning_output_tokens=as_int(obj.get("reasoning_output_tokens")),
            total_tokens=as_int(obj.get("total_tokens")),
        )

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.cached_input_tokens + other.cached_input_tokens,
            self.cache_write_input_tokens + other.cache_write_input_tokens,
            self.output_tokens + other.output_tokens,
            self.reasoning_output_tokens + other.reasoning_output_tokens,
            self.total_tokens + other.total_tokens,
        )

    def __sub__(self, other: "Usage") -> "Usage":
        # Cumulative counters should be monotonic; clamp each field for replay/
        # compaction edge cases rather than displaying negative numbers.
        return Usage(
            max(0, self.input_tokens - other.input_tokens),
            max(0, self.cached_input_tokens - other.cached_input_tokens),
            max(0, self.cache_write_input_tokens - other.cache_write_input_tokens),
            max(0, self.output_tokens - other.output_tokens),
            max(0, self.reasoning_output_tokens - other.reasoning_output_tokens),
            max(0, self.total_tokens - other.total_tokens),
        )

    @property
    def cache_hit(self) -> Optional[float]:
        if self.input_tokens <= 0:
            return None
        return max(0.0, min(100.0, self.cached_input_tokens / self.input_tokens * 100.0))


@dataclass
class ToolSpan:
    call_id: str
    kind: str = "tool"
    turn_id: Optional[str] = None
    start: Optional[float] = None
    end: Optional[float] = None
    explicit_duration: Optional[float] = None

    def normalized_interval(self) -> Optional[tuple[float, float]]:
        st, en = self.start, self.end
        d = self.explicit_duration
        if st is not None and en is not None:
            return (min(st, en), max(st, en))
        if st is not None and d is not None:
            return (st, st + max(0.0, d))
        if en is not None and d is not None:
            return (en - max(0.0, d), en)
        return None

    @property
    def duration(self) -> Optional[float]:
        iv = self.normalized_interval()
        if iv:
            return max(0.0, iv[1] - iv[0])
        if self.explicit_duration is not None:
            return max(0.0, self.explicit_duration)
        return None


def union_duration(spans: list[ToolSpan]) -> tuple[float, float]:
    """
    Returns (union_seconds, timing_coverage).

    Intervals are merged so concurrently-running tools aren't double-counted.
    Explicit-duration-only spans are added after interval union because their
    placement is unknown.
    """
    intervals: list[tuple[float, float]] = []
    duration_only = 0.0
    timed = 0

    for span in spans:
        iv = span.normalized_interval()
        if iv is not None:
            intervals.append(iv)
            timed += 1
        elif span.explicit_duration is not None:
            duration_only += max(0.0, span.explicit_duration)
            timed += 1

    intervals.sort()
    merged: list[list[float]] = []
    for st, en in intervals:
        if not merged or st > merged[-1][1]:
            merged.append([st, en])
        else:
            merged[-1][1] = max(merged[-1][1], en)

    total = sum(en - st for st, en in merged) + duration_only
    coverage = timed / len(spans) if spans else 1.0
    return max(0.0, total), coverage


@dataclass
class Turn:
    turn_id: str
    seq_start: int
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None
    last_ts: Optional[float] = None
    duration_ms: Optional[float] = None
    ttft_ms: Optional[float] = None
    model: str = ""
    context_window: Optional[int] = None
    usage_baseline: Usage = field(default_factory=Usage)
    usage_latest: Usage = field(default_factory=Usage)
    exact_response_usage: Usage = field(default_factory=Usage)
    exact_response_count: int = 0
    tool_ids: set[str] = field(default_factory=set)
    aborted: bool = False

    def wall_seconds(self, active_file: bool = False) -> float:
        if self.duration_ms is not None and self.duration_ms >= 0:
            return self.duration_ms / 1000.0
        if self.start_ts is None:
            return 0.0
        if self.end_ts is not None:
            return max(0.0, self.end_ts - self.start_ts)
        # Live turn: continue ticking. Old/incomplete rollout: stop at last event.
        end = time.time() if active_file else self.last_ts
        if end is None:
            return 0.0
        return max(0.0, end - self.start_ts)

    def usage(self) -> Usage:
        if self.exact_response_count > 0:
            return self.exact_response_usage
        return self.usage_latest - self.usage_baseline


@dataclass
class ViewMetrics:
    scope: str
    model: str = ""
    rounds: int = 0
    steps: int = 0
    wall_seconds: float = 0.0
    llm_seconds_est: float = 0.0
    tool_seconds: float = 0.0
    ttft_avg_ms: Optional[float] = None
    tokens_per_second_est: Optional[float] = None
    usage: Usage = field(default_factory=Usage)
    active: bool = False
    tool_timing_coverage: float = 1.0
    context_window: Optional[int] = None
    current_context_tokens: Optional[int] = None
    exact_response_count: int = 0

    def status_line(self, include_model: bool = True, lang: str = "zh-CN") -> str:
        parts: list[str] = []
        if include_model and self.model:
            parts.append(self.model)

        if lang == "en":
            parts.append(f"Turn · {self.steps} steps" if self.scope == "turn" else f"Session · {self.rounds} rounds · {self.steps} steps")
        elif self.scope == "turn":
            parts.append(f"本轮 · {self.steps} 步")
        else:
            parts.append(f"会话 {self.rounds} 轮 · {self.steps} 步")

        if self.wall_seconds > 0 or self.tool_seconds > 0:
            parts.append((f"LLM≈{fmt_time(self.llm_seconds_est)} · Tools {fmt_time(self.tool_seconds)}") if lang == "en" else f"LLM≈{fmt_time(self.llm_seconds_est)} · 工具 {fmt_time(self.tool_seconds)}")

        perf: list[str] = []
        if self.ttft_avg_ms is not None:
            if lang == "en":
                perf.append(f"TTFT {fmt_time(self.ttft_avg_ms / 1000.0)}" if self.scope == "turn" else f"Avg TTFT {fmt_time(self.ttft_avg_ms / 1000.0)}")
            else:
                perf.append(f"首 token {fmt_time(self.ttft_avg_ms / 1000.0)}" if self.scope == "turn" else f"首 token 平均 {fmt_time(self.ttft_avg_ms / 1000.0)}")
        if self.tokens_per_second_est is not None and math.isfinite(self.tokens_per_second_est):
            perf.append(f"≈{self.tokens_per_second_est:.0f} tok/s")
        if perf:
            parts.append(" · ".join(perf))

        hit = self.usage.cache_hit
        if hit is not None:
            parts.append(f"Cache hit {hit:.0f}%" if lang == "en" else f"缓存命中 {hit:.0f}%")

        parts.append(
            (f"Input {fmt_num(self.usage.input_tokens)} tok · Output {fmt_num(self.usage.output_tokens)} tok" if lang == "en" else f"输入 {fmt_num(self.usage.input_tokens)} tok · 输出 {fmt_num(self.usage.output_tokens)} tok")
        )
        return "   |   ".join(parts)


# -----------------------------
# Rollout parser
# -----------------------------

class RolloutParser:
    TOOL_BEGIN_TYPES = {
        "exec_command_begin": "exec",
        "mcp_tool_call_begin": "mcp",
        "patch_apply_begin": "patch",
        "apply_patch_begin": "patch",
        "web_search_begin": "web",
        "image_generation_begin": "image",
        "dynamic_tool_call_begin": "dynamic",
        "tool_call_begin": "tool",
        "collab_agent_spawn_begin": "agent_spawn",
        "collab_agent_interaction_begin": "agent_interaction",
        "collab_waiting_begin": "agent_wait",
        "collab_close_begin": "agent_close",
        "collab_resume_begin": "agent_resume",
    }
    TOOL_END_TYPES = {
        "exec_command_end": "exec",
        "mcp_tool_call_end": "mcp",
        "patch_apply_end": "patch",
        "apply_patch_end": "patch",
        "web_search_end": "web",
        "image_generation_end": "image",
        "dynamic_tool_call_end": "dynamic",
        "tool_call_end": "tool",
        "collab_agent_spawn_end": "agent_spawn",
        "collab_agent_interaction_end": "agent_interaction",
        "collab_waiting_end": "agent_wait",
        "collab_close_end": "agent_close",
        "collab_resume_end": "agent_resume",
    }
    RESPONSE_TOOL_TYPES = {
        "function_call",
        "custom_tool_call",
        "local_shell_call",
        "shell_call",
        "mcp_tool_call",
        "web_search_call",
        "computer_call",
        "tool_call",
    }

    TURN_START_TYPES = {"task_started", "turn_started"}
    TURN_END_TYPES = {"task_complete", "turn_complete", "turn_completed"}
    TURN_ABORT_TYPES = {"turn_aborted", "task_aborted"}

    def __init__(self) -> None:
        self.seq = 0
        self.parse_errors = 0
        self.last_event_ts: Optional[float] = None
        self.model = ""
        self.context_window: Optional[int] = None

        self.current_total_usage = Usage()
        self.latest_total_usage = Usage()
        self.current_context_tokens: Optional[int] = None

        self.turns: list[Turn] = []
        self.turn_by_id: dict[str, Turn] = {}
        self.active_turn: Optional[Turn] = None

        self.tools: dict[str, ToolSpan] = {}

    @staticmethod
    def unwrap(obj: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        typ = str(obj.get("type", "") or "").lower()
        payload = obj.get("payload")
        if isinstance(payload, dict):
            if typ in {"event_msg", "event", "eventmsg"}:
                return str(payload.get("type", "") or "").lower(), payload
            if typ:
                return typ, payload
        item = obj.get("item")
        if isinstance(item, dict):
            it = str(item.get("type", "") or "").lower()
            if it:
                return it, item
        return typ, obj

    @staticmethod
    def outer_ts(obj: dict[str, Any]) -> Optional[float]:
        for key in ("timestamp", "ts", "time", "created_at"):
            t = parse_ts(obj.get(key))
            if t is not None:
                return t
        return None

    def ensure_turn(self, turn_id: Optional[str], ts: Optional[float], fallback_prefix: str = "turn") -> Turn:
        tid = str(turn_id or f"{fallback_prefix}:{self.seq}")
        turn = self.turn_by_id.get(tid)
        if turn is None:
            turn = Turn(
                turn_id=tid,
                seq_start=self.seq,
                start_ts=ts,
                last_ts=ts,
                model=self.model,
                context_window=self.context_window,
                usage_baseline=self.current_total_usage,
                usage_latest=self.current_total_usage,
            )
            self.turn_by_id[tid] = turn
            self.turns.append(turn)
        else:
            if turn.start_ts is None and ts is not None:
                turn.start_ts = ts
            if ts is not None:
                turn.last_ts = ts
        return turn

    def current_or_last_turn(self) -> Optional[Turn]:
        return self.active_turn or (self.turns[-1] if self.turns else None)

    @staticmethod
    def call_id(payload: dict[str, Any], fallback: str) -> str:
        for key in ("call_id", "tool_call_id", "id", "item_id"):
            v = payload.get(key)
            if v is not None and str(v):
                return str(v)
        return fallback

    def extract_model(self, typ: str, payload: dict[str, Any]) -> None:
        candidates: list[Any] = []
        if typ in {"turn_context", "session_meta"}:
            candidates.append(payload.get("model"))
        if typ == "thread_settings_applied":
            settings = payload.get("thread_settings")
            if isinstance(settings, dict):
                candidates.append(settings.get("model"))
        if typ in {"thread_settings", "thread_settings_snapshot"}:
            candidates.append(payload.get("model"))
        if typ == "model_reroute":
            candidates.append(payload.get("to_model"))
        for v in candidates:
            if isinstance(v, str) and v.strip():
                self.model = v.strip()
                if self.active_turn and not self.active_turn.model:
                    self.active_turn.model = self.model

    def start_turn(self, payload: dict[str, Any], ts: Optional[float]) -> None:
        tid = str(payload.get("turn_id", "") or f"turn:{self.seq}")
        st = parse_ts(payload.get("started_at")) or ts
        turn = self.ensure_turn(tid, st)
        # A real start event is authoritative for the baseline.
        turn.usage_baseline = self.current_total_usage
        turn.usage_latest = self.current_total_usage
        turn.start_ts = st or turn.start_ts
        turn.last_ts = ts or st or turn.last_ts
        turn.context_window = as_int(payload.get("model_context_window")) or self.context_window
        turn.model = self.model or turn.model
        self.active_turn = turn

    def complete_turn(self, payload: dict[str, Any], ts: Optional[float]) -> None:
        tid = str(payload.get("turn_id", "") or "")
        turn = self.turn_by_id.get(tid) if tid else self.current_or_last_turn()
        if turn is None:
            turn = self.ensure_turn(tid or None, parse_ts(payload.get("started_at")) or ts)
        if turn.start_ts is None:
            turn.start_ts = parse_ts(payload.get("started_at"))
        turn.end_ts = parse_ts(payload.get("completed_at")) or ts or turn.last_ts
        if payload.get("duration_ms") is not None:
            turn.duration_ms = max(0.0, as_num(payload.get("duration_ms")))
        if payload.get("time_to_first_token_ms") is not None:
            turn.ttft_ms = max(0.0, as_num(payload.get("time_to_first_token_ms")))
        turn.last_ts = ts or turn.end_ts or turn.last_ts
        turn.usage_latest = self.current_total_usage
        if self.active_turn is turn:
            self.active_turn = None

    def abort_turn(self, payload: dict[str, Any], ts: Optional[float]) -> None:
        tid = str(payload.get("turn_id", "") or "")
        turn = self.turn_by_id.get(tid) if tid else self.current_or_last_turn()
        if turn:
            turn.aborted = True
            turn.end_ts = ts or turn.last_ts
            turn.usage_latest = self.current_total_usage
            if self.active_turn is turn:
                self.active_turn = None

    def token_count(self, payload: dict[str, Any]) -> None:
        info = payload.get("info")
        if not isinstance(info, dict):
            return
        total = Usage.from_obj(info.get("total_token_usage"))
        # TokenUsageInfo is cumulative. A zero object can appear in synthetic/fill paths;
        # only move the main snapshot forward when it looks non-decreasing.
        if total.total_tokens >= self.latest_total_usage.total_tokens:
            self.latest_total_usage = total
            self.current_total_usage = total

        last = Usage.from_obj(info.get("last_token_usage"))
        if last.input_tokens > 0:
            self.current_context_tokens = last.input_tokens

        cw = as_int(info.get("model_context_window"))
        if cw > 0:
            self.context_window = cw

        turn = self.current_or_last_turn()
        if turn is not None:
            turn.usage_latest = self.current_total_usage
            if cw > 0:
                turn.context_window = cw

    def raw_response_completed(self, payload: dict[str, Any]) -> None:
        usage = Usage.from_obj(payload.get("token_usage"))
        if usage.total_tokens <= 0 and usage.input_tokens <= 0 and usage.output_tokens <= 0:
            return
        turn = self.current_or_last_turn()
        if turn is not None:
            turn.exact_response_usage = turn.exact_response_usage + usage
            turn.exact_response_count += 1

    def begin_tool(self, typ: str, payload: dict[str, Any], ts: Optional[float]) -> None:
        cid = self.call_id(payload, f"{typ}:{self.seq}")
        tid = payload.get("turn_id")
        turn = self.turn_by_id.get(str(tid)) if tid else self.current_or_last_turn()
        if turn is None:
            turn = self.ensure_turn(None, ts, "implicit")
            self.active_turn = turn

        span = self.tools.get(cid)
        if span is None:
            span = ToolSpan(cid, self.TOOL_BEGIN_TYPES.get(typ, "tool"), turn.turn_id)
            self.tools[cid] = span
        span.turn_id = span.turn_id or turn.turn_id
        st_ms = payload.get("started_at_ms")
        st = parse_ts(as_num(st_ms)) if st_ms not in (None, 0, "0") else ts
        if span.start is None:
            span.start = st
        turn.tool_ids.add(cid)

    def end_tool(self, typ: str, payload: dict[str, Any], ts: Optional[float]) -> None:
        cid = self.call_id(payload, f"{typ}:{self.seq}")
        tid = payload.get("turn_id")
        turn = self.turn_by_id.get(str(tid)) if tid else self.current_or_last_turn()
        if turn is None:
            turn = self.ensure_turn(None, ts, "implicit")

        span = self.tools.get(cid)
        if span is None:
            span = ToolSpan(cid, self.TOOL_END_TYPES.get(typ, "tool"), turn.turn_id)
            self.tools[cid] = span
        span.turn_id = span.turn_id or turn.turn_id

        d = None
        if payload.get("duration_ms") is not None:
            d = max(0.0, as_num(payload.get("duration_ms")) / 1000.0)
        if d is None:
            d = parse_duration_seconds(payload.get("duration"))
        if d is not None:
            span.explicit_duration = d

        en_ms = payload.get("completed_at_ms")
        en = parse_ts(as_num(en_ms)) if en_ms not in (None, 0, "0") else ts
        if span.end is None:
            span.end = en
        turn.tool_ids.add(cid)

    def response_item(self, payload: dict[str, Any], ts: Optional[float]) -> None:
        item_type = str(payload.get("type", "") or "").lower()
        if item_type in self.RESPONSE_TOOL_TYPES:
            cid = self.call_id(payload, f"response_tool:{self.seq}")
            turn = self.current_or_last_turn()
            if turn is None:
                turn = self.ensure_turn(None, ts, "implicit")
                self.active_turn = turn
            turn.tool_ids.add(cid)
            if cid not in self.tools:
                self.tools[cid] = ToolSpan(cid, item_type, turn.turn_id, start=ts)

        if item_type == "message" and str(payload.get("role", "")).lower() == "user":
            # Legacy fallback for rollout files without task_started.
            if self.active_turn is None:
                turn = self.ensure_turn(f"user:{self.seq}", ts, "user")
                self.active_turn = turn

    def item_event(self, typ: str, payload: dict[str, Any], ts: Optional[float]) -> None:
        item = payload.get("item")
        if not isinstance(item, dict):
            return
        tid = payload.get("turn_id")
        if tid:
            turn = self.ensure_turn(str(tid), parse_ts(payload.get("started_at_ms")) or ts)
            if self.active_turn is None and turn.end_ts is None:
                self.active_turn = turn
        self.response_item(item, ts)

    def feed(self, obj: dict[str, Any]) -> None:
        self.seq += 1
        ts = self.outer_ts(obj)
        if ts is not None:
            self.last_event_ts = ts
        if self.active_turn and ts is not None:
            self.active_turn.last_ts = ts

        typ, payload = self.unwrap(obj)
        typ = typ.lower()
        self.extract_model(typ, payload)

        if typ in self.TURN_START_TYPES:
            self.start_turn(payload, ts)
        elif typ in self.TURN_END_TYPES:
            self.complete_turn(payload, ts)
        elif typ in self.TURN_ABORT_TYPES:
            self.abort_turn(payload, ts)
        elif typ == "token_count":
            self.token_count(payload)
        elif typ == "raw_response_completed":
            self.raw_response_completed(payload)
        elif typ in self.TOOL_BEGIN_TYPES:
            self.begin_tool(typ, payload, ts)
        elif typ in self.TOOL_END_TYPES:
            self.end_tool(typ, payload, ts)
        elif typ == "response_item":
            self.response_item(payload, ts)
        elif typ in self.RESPONSE_TOOL_TYPES or typ == "message":
            self.response_item(payload, ts)
        elif typ in {"item_started", "item_completed", "item_updated"}:
            self.item_event(typ, payload, ts)

    def _spans_for_turn(self, turn: Turn) -> list[ToolSpan]:
        return [self.tools[cid] for cid in turn.tool_ids if cid in self.tools]

    def turn_metrics(self, active_file: bool) -> ViewMetrics:
        if not self.turns:
            return ViewMetrics(scope="turn", model=self.model, active=active_file)

        turn = self.turns[-1]
        spans = self._spans_for_turn(turn)
        tool_s, coverage = union_duration(spans)
        wall_s = turn.wall_seconds(active_file=active_file and turn.end_ts is None)

        # Clamp tool time to wall time for the LLM estimate only. We still display
        # the measured tool union itself so timing anomalies remain visible.
        subtractable_tool = min(tool_s, wall_s) if wall_s > 0 else 0.0
        llm_s = max(0.0, wall_s - subtractable_tool)
        usage = turn.usage()

        tps = None
        if usage.output_tokens > 0 and llm_s > 0.05:
            tps = usage.output_tokens / llm_s

        return ViewMetrics(
            scope="turn",
            model=turn.model or self.model,
            rounds=1,
            steps=len(turn.tool_ids),
            wall_seconds=wall_s,
            llm_seconds_est=llm_s,
            tool_seconds=tool_s,
            ttft_avg_ms=turn.ttft_ms,
            tokens_per_second_est=tps,
            usage=usage,
            active=active_file and turn.end_ts is None,
            tool_timing_coverage=coverage,
            context_window=turn.context_window or self.context_window,
            current_context_tokens=self.current_context_tokens,
            exact_response_count=turn.exact_response_count,
        )

    def session_metrics(self, active_file: bool) -> ViewMetrics:
        all_spans: list[ToolSpan] = []
        total_wall = 0.0
        total_tool = 0.0
        total_llm = 0.0
        cover_num = 0
        cover_den = 0
        ttfts: list[float] = []
        steps: set[str] = set()
        exact_count = 0

        for i, turn in enumerate(self.turns):
            spans = self._spans_for_turn(turn)
            tool_s, coverage = union_duration(spans)
            is_latest_live = (i == len(self.turns) - 1 and active_file and turn.end_ts is None)
            wall_s = turn.wall_seconds(active_file=is_latest_live)
            total_wall += wall_s
            total_tool += tool_s
            total_llm += max(0.0, wall_s - min(tool_s, wall_s))
            steps.update(turn.tool_ids)
            if turn.ttft_ms is not None:
                ttfts.append(turn.ttft_ms)
            cover_num += round(coverage * len(spans))
            cover_den += len(spans)
            exact_count += turn.exact_response_count

        usage = self.latest_total_usage
        avg_ttft = sum(ttfts) / len(ttfts) if ttfts else None
        tps = usage.output_tokens / total_llm if usage.output_tokens > 0 and total_llm > 0.05 else None
        coverage = cover_num / cover_den if cover_den else 1.0

        return ViewMetrics(
            scope="session",
            model=self.model or (self.turns[-1].model if self.turns else ""),
            rounds=len(self.turns),
            steps=len(steps),
            wall_seconds=total_wall,
            llm_seconds_est=total_llm,
            tool_seconds=total_tool,
            ttft_avg_ms=avg_ttft,
            tokens_per_second_est=tps,
            usage=usage,
            active=active_file,
            tool_timing_coverage=coverage,
            context_window=self.context_window,
            current_context_tokens=self.current_context_tokens,
            exact_response_count=exact_count,
        )


@dataclass
class ParsedRollout:
    path: Path
    parser: RolloutParser
    active_file: bool
    parse_errors: int

    def metrics(self, scope: str) -> ViewMetrics:
        return self.parser.session_metrics(self.active_file) if scope == "session" else self.parser.turn_metrics(self.active_file)


def parse_rollout(path: Path) -> ParsedRollout:
    parser = RolloutParser()
    errors = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                except json.JSONDecodeError:
                    errors += 1
                    continue
                if isinstance(obj, dict):
                    parser.feed(obj)
    except OSError:
        errors += 1

    try:
        active = (time.time() - path.stat().st_mtime) < 15
    except OSError:
        active = False

    return ParsedRollout(path, parser, active, errors)


class IncrementalRolloutReader:
    """Append-only JSONL reader used by the live HUD refresh loop."""

    def __init__(self) -> None:
        self.path: Optional[Path] = None
        self.offset = 0
        self.tail = b""
        self.file_id: Optional[tuple[int, int]] = None
        self.parser = RolloutParser()
        self.parse_errors = 0

    def reset(self, path: Path) -> None:
        self.path = path
        self.offset = 0
        self.tail = b""
        self.file_id = None
        self.parser = RolloutParser()
        self.parse_errors = 0

    def _feed_line(self, raw: bytes) -> None:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            self.parse_errors += 1
            return
        if isinstance(obj, dict):
            self.parser.feed(obj)

    def read(self, path: Path) -> ParsedRollout:
        try:
            stat = path.stat()
            file_id = (int(getattr(stat, "st_ino", 0)), int(stat.st_ctime_ns))
        except OSError:
            self.reset(path)
            return ParsedRollout(path, self.parser, False, 1)

        if self.path != path or stat.st_size < self.offset or (self.file_id is not None and file_id != self.file_id):
            self.reset(path)
        self.file_id = file_id

        try:
            with path.open("rb") as handle:
                handle.seek(self.offset)
                chunk = handle.read()
                self.offset = handle.tell()
        except OSError:
            return ParsedRollout(path, self.parser, False, self.parse_errors + 1)

        if chunk:
            data = self.tail + chunk
            lines = data.split(b"\n")
            self.tail = lines.pop()
            for line in lines:
                self._feed_line(line.rstrip(b"\r"))

        try:
            active = (time.time() - path.stat().st_mtime) < 15
        except OSError:
            active = False
        return ParsedRollout(path, self.parser, active, self.parse_errors)


def executable_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve()


def startup_enabled() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            command = str(value).strip()
            if command.startswith('"') and '"' in command[1:]:
                command = command[1:command.find('"', 1)]
            else:
                command = command.split(" ", 1)[0]
            return Path(command).resolve() == executable_path()
    except (FileNotFoundError, OSError, ImportError):
        return False


def set_startup_enabled(enabled: bool) -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            if enabled:
                command = f'"{executable_path()}"'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except (OSError, ImportError):
        return False


def virtual_screen_bounds() -> tuple[int, int, int, int]:
    """Return Windows virtual desktop bounds; primary-screen fallback elsewhere."""
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            left = int(user32.GetSystemMetrics(76))
            top = int(user32.GetSystemMetrics(77))
            width = int(user32.GetSystemMetrics(78))
            height = int(user32.GetSystemMetrics(79))
            if width > 0 and height > 0:
                return left, top, width, height
        except (AttributeError, OSError):
            pass
    return 0, 0, 1920, 1080


def clamp_window_position(x: int, y: int, width: int, height: int) -> tuple[int, int]:
    left, top, screen_w, screen_h = virtual_screen_bounds()
    margin = 8
    max_x = left + max(margin, screen_w - max(width, 1) - margin)
    max_y = top + max(margin, screen_h - max(height, 1) - margin)
    return max(left + margin, min(int(x), max_x)), max(top + margin, min(int(y), max_y))


def find_latest_rollout(codex_home: Path) -> Optional[Path]:
    candidates: list[tuple[float, Path]] = []
    for base in (codex_home / "sessions", codex_home / "archived_sessions"):
        if not base.exists():
            continue
        try:
            for p in base.rglob("rollout-*.jsonl"):
                try:
                    candidates.append((p.stat().st_mtime, p))
                except OSError:
                    pass
        except OSError:
            pass
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def diagnostic(parsed: ParsedRollout, m: ViewMetrics) -> str:
    bits: list[str] = []
    if m.tool_timing_coverage < 0.999 and m.steps:
        bits.append(f"工具计时覆盖 {m.tool_timing_coverage*100:.0f}%")
    if parsed.parse_errors:
        bits.append(f"忽略 {parsed.parse_errors} 行无效 JSON")
    if m.context_window and m.current_context_tokens:
        pct = m.current_context_tokens / m.context_window * 100.0
        bits.append(f"当前上下文约 {pct:.0f}%")
    if m.usage.reasoning_output_tokens:
        bits.append(f"reasoning {fmt_num(m.usage.reasoning_output_tokens)}")
    if m.exact_response_count:
        bits.append(f"精确 response usage ×{m.exact_response_count}")
    else:
        bits.append("token=累计差值")
    return " · ".join(bits)


# -----------------------------
# CLI / GUI
# -----------------------------

def run_gui(args: argparse.Namespace) -> int:
    try:
        import tkinter as tk
    except Exception as e:
        print(tr(args.lang, "tk_missing"), file=sys.stderr)
        print(e, file=sys.stderr)
        return 2

    codex_home = Path(args.codex_home).expanduser()
    fixed_file = Path(args.file).expanduser() if args.file else None
    lang = args.lang
    state: dict[str, Any] = {"scope": "session" if args.session else "turn", "expanded": False, "visible": True}
    settings = load_settings()
    BG, FG, MUTED = "#1b1b1d", "#d6d6da", "#8b8b92"
    BUTTON_BG, BUTTON_ACTIVE = "#2a2a2e", "#34343a"

    root = tk.Tk()
    root.title(tr(lang, "title"))
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    root.overrideredirect(True)
    try:
        root.attributes("-alpha", 0.97)
    except Exception:
        pass

    frame = tk.Frame(root, bg=BG, padx=8, pady=5)
    frame.pack(fill="both", expand=True)
    scope_button = tk.Button(frame, text=tr(lang, "turn"), command=lambda: toggle_scope(), bg=BUTTON_BG, fg=FG,
                             activebackground=BUTTON_ACTIVE, activeforeground=FG, relief="flat", bd=0,
                             padx=7, pady=1, font=("Segoe UI", 9), cursor="hand2", takefocus=False, highlightthickness=0)
    scope_button.pack(side="left")
    content = tk.Frame(frame, bg=BG, padx=8, pady=0, cursor="hand2")
    content.pack(side="left", fill="both", expand=True)
    compact_label = tk.Label(content, text=f"{tr(lang, 'cache')} --  ·  {tr(lang, 'input')} --  ·  {tr(lang, 'output')} --",
                             bg=BG, fg=FG, font=("Segoe UI", 10), justify="left", anchor="w", cursor="hand2")
    compact_label.pack(side="top", anchor="w")
    full_label = tk.Label(content, text="", bg=BG, fg=FG, font=("Segoe UI", 10), justify="left", anchor="w", cursor="hand2")
    full_detail = tk.Label(content, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8), justify="left", anchor="w", cursor="hand2", pady=2)

    def resize_to_content() -> None:
        try:
            root.update_idletasks()
            x, y = root.winfo_x(), root.winfo_y()
            w, h = max(1, root.winfo_reqwidth()), max(1, root.winfo_reqheight())
            root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def persist_position() -> None:
        try:
            x, y = root.winfo_x(), root.winfo_y()
            settings["x"], settings["y"] = int(x), int(y)
            save_settings(settings)
        except Exception:
            pass

    def set_visible(visible: bool) -> None:
        state["visible"] = bool(visible)
        if visible:
            root.deiconify()
            root.attributes("-topmost", True)
        else:
            persist_position()
            root.withdraw()

    def set_expanded(expanded: bool) -> None:
        state["expanded"] = bool(expanded)
        if expanded:
            compact_label.pack_forget(); full_label.pack(side="top", anchor="w"); full_detail.pack(side="top", anchor="w")
        else:
            full_label.pack_forget(); full_detail.pack_forget(); compact_label.pack(side="top", anchor="w")
        root.after_idle(resize_to_content)

    def toggle_expanded(_event=None) -> str:
        set_expanded(not state["expanded"]); return "break"

    def copy_visible(_event=None) -> str:
        try:
            root.clipboard_clear(); root.clipboard_append(full_label.cget("text") if state["expanded"] else compact_label.cget("text")); root.update()
        except Exception:
            pass
        return "break"

    def quit_app(_event=None) -> None:
        persist_position()
        tray_state["quit"] = True
        if tray_icon["icon"] is not None:
            try: tray_icon["icon"].stop()
            except Exception: pass
        root.destroy()

    def toggle_scope(_event=None) -> str:
        state["scope"] = "session" if state["scope"] == "turn" else "turn"; render(True); return "break"

    cache: dict[str, Any] = {"path": None, "parsed": None, "metrics": None}
    reader = IncrementalRolloutReader()

    def compact_text(m: ViewMetrics) -> str:
        hit = m.usage.cache_hit; hit_text = f"{hit:.0f}%" if hit is not None else "--"
        return f"{tr(lang, 'cache')} {hit_text}  ·  {tr(lang, 'input')} {fmt_num(m.usage.input_tokens)}  ·  {tr(lang, 'output')} {fmt_num(m.usage.output_tokens)}"

    def expanded_detail(parsed: ParsedRollout, m: ViewMetrics, path: Path) -> str:
        bits: list[str] = []
        if m.context_window and m.current_context_tokens:
            bits.append((f"Context ~{m.current_context_tokens / m.context_window * 100:.0f}%" if lang == "en" else f"上下文约 {m.current_context_tokens / m.context_window * 100:.0f}%"))
        if m.usage.reasoning_output_tokens: bits.append(f"reasoning {fmt_num(m.usage.reasoning_output_tokens)}")
        if m.tool_timing_coverage < 0.999 and m.steps: bits.append((f"Tool timing {m.tool_timing_coverage*100:.0f}%" if lang == "en" else f"工具计时覆盖 {m.tool_timing_coverage*100:.0f}%"))
        bits.append((f"Exact response usage ×{m.exact_response_count}" if m.exact_response_count else "token=cumulative delta") if lang == "en" else (f"精确 response usage ×{m.exact_response_count}" if m.exact_response_count else "token=累计差值"))
        if parsed.parse_errors: bits.append((f"Ignored {parsed.parse_errors} invalid JSON lines" if lang == "en" else f"忽略 {parsed.parse_errors} 行无效 JSON"))
        if args.debug: bits.append(path.name)
        return "  ·  ".join(bits)

    def render(force_resize: bool = False) -> None:
        parsed, path = cache.get("parsed"), cache.get("path")
        scope_label = tr(lang, "turn") if state["scope"] == "turn" else tr(lang, "session")
        scope_button.config(text=scope_label)
        if parsed is None or path is None:
            compact_label.config(text=f"{tr(lang, 'cache')} --  ·  {tr(lang, 'input')} --  ·  {tr(lang, 'output')} --")
            full_label.config(text=tr(lang, "not_found")); full_detail.config(text=str(codex_home))
        else:
            m = parsed.metrics(state["scope"]); cache["metrics"] = m
            compact_label.config(text=compact_text(m)); full_label.config(text=("● " if m.active else "○ ") + m.status_line(args.model, lang)); full_detail.config(text=expanded_detail(parsed, m, path))
        if force_resize: root.after_idle(resize_to_content)

    drag = {"offset_x": 0, "offset_y": 0, "press_x": 0, "press_y": 0, "moved": False}
    def on_down(e):
        drag.update(offset_x=e.x_root-root.winfo_x(), offset_y=e.y_root-root.winfo_y(), press_x=e.x_root, press_y=e.y_root, moved=False)
    def on_move(e):
        if max(abs(e.x_root-drag["press_x"]), abs(e.y_root-drag["press_y"])) >= 5: drag["moved"] = True
        if drag["moved"]: root.geometry(f"+{e.x_root-drag['offset_x']}+{e.y_root-drag['offset_y']}")
    def on_release(_e):
        if drag["moved"]: persist_position()
        else: toggle_expanded()
        return "break"

    for widget in (content, compact_label, full_label, full_detail, frame):
        widget.bind("<ButtonPress-1>", on_down); widget.bind("<B1-Motion>", on_move); widget.bind("<ButtonRelease-1>", on_release)
        widget.bind("<Button-3>", lambda _e: set_visible(False)); widget.bind("<Button-2>", copy_visible)
    scope_button.bind("<Button-3>", lambda _e: set_visible(False)); scope_button.bind("<Button-2>", copy_visible)
    root.bind("<Escape>", lambda _e: set_visible(False)); root.bind("<Control-c>", copy_visible); root.bind("<Key-s>", toggle_scope); root.bind("<Key-S>", toggle_scope); root.bind("<space>", toggle_expanded)
    root.protocol("WM_DELETE_WINDOW", lambda: set_visible(False))

    root.update_idletasks()
    initial_w = max(1, root.winfo_reqwidth())
    default_x = root.winfo_screenwidth() - initial_w - 24
    x, y = clamp_window_position(int(settings.get("x", default_x)), int(settings.get("y", 24)), initial_w, root.winfo_reqheight())
    root.geometry(f"+{x}+{y}")

    tray_queue: queue.Queue[str] = queue.Queue()
    tray_icon: dict[str, Any] = {"icon": None}
    tray_state: dict[str, Any] = {"quit": False}
    try:
        import pystray
        from PIL import Image, ImageDraw
        image = Image.new("RGBA", (64, 64), (27, 27, 29, 255)); draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill=(87, 185, 126, 255)); draw.text((18, 17), "C", fill=(255, 255, 255, 255))
        def tray_action(action):
            return lambda icon, item: tray_queue.put(action)
        menu = pystray.Menu(
            pystray.MenuItem(tr(lang, "show"), tray_action("show")),
            pystray.MenuItem(tr(lang, "hide"), tray_action("hide")),
            pystray.MenuItem(tr(lang, "startup"), tray_action("startup"), checked=lambda item: startup_enabled()),
            pystray.MenuItem(tr(lang, "about"), tray_action("about")),
            pystray.MenuItem(tr(lang, "quit"), tray_action("quit")),
        )
        icon = pystray.Icon(APP_NAME, image, tr(lang, "title"), menu); tray_icon["icon"] = icon
        threading.Thread(target=icon.run, daemon=True, name="codex-overlay-tray").start()
    except Exception:
        pass

    def pump_tray() -> None:
        try:
            while True:
                action = tray_queue.get_nowait()
                if action == "show": set_visible(True)
                elif action == "hide": set_visible(False)
                elif action == "startup": set_startup_enabled(not startup_enabled())
                elif action == "about":
                    try:
                        from tkinter import messagebox
                        messagebox.showinfo(tr(lang, "title"), f"{tr(lang, 'unofficial')}\n\nRead-only local session monitor. No network access.")
                    except Exception: pass
                elif action == "quit": quit_app()
        except queue.Empty:
            pass
        if not tray_state["quit"]: root.after(100, pump_tray)

    def refresh() -> None:
        p = fixed_file if fixed_file else find_latest_rollout(codex_home)
        if p is None or not p.exists():
            if cache.get("path") is not None or cache.get("parsed") is not None:
                cache.update(path=None, parsed=None, metrics=None); render(True)
        else:
            parsed = reader.read(p); cache.update(path=p, parsed=parsed); render(False)
        root.after(max(100, int(args.interval * 1000)), refresh)

    set_expanded(False); pump_tray(); refresh(); root.mainloop(); return 0

def main() -> int:
    ap = argparse.ArgumentParser(description="Codex Token Overlay — read-only local session HUD")
    ap.add_argument("--codex-home", default=str(codex_home_default()))
    ap.add_argument("--file", help="Monitor one rollout JSONL instead of auto-selecting latest")
    ap.add_argument("--interval", type=float, default=0.75)
    ap.add_argument("--once", action="store_true", help="Print one status line and exit")
    ap.add_argument("--session", action="store_true", help="Start/print session cumulative scope")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--no-model", dest="model", action="store_false", help="Hide model name")
    ap.add_argument("--lang", choices=("auto", "zh-CN", "en"), default="auto", help="UI language (default: auto)")
    ap.set_defaults(model=True)
    args = ap.parse_args()
    args.lang = resolve_language(args.lang)

    if args.once:
        p = Path(args.file).expanduser() if args.file else find_latest_rollout(Path(args.codex_home).expanduser())
        if not p:
            print(tr(args.lang, "invalid_rollout", home=args.codex_home), file=sys.stderr)
            return 1
        parsed = parse_rollout(p)
        scope = "session" if args.session else "turn"
        m = parsed.metrics(scope)
        print(m.status_line(include_model=args.model, lang=args.lang))
        if args.debug:
            print(diagnostic(parsed, m))
        print(p)
        return 0

    return run_gui(args)


if __name__ == "__main__":
    raise SystemExit(main())

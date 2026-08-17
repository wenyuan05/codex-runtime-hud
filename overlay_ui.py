"""Canvas-based Tk UI for Codex Runtime HUD.

The parser remains in :mod:`codex_runtime_hud`; this module only owns presentation,
interaction and UI preferences so visual changes cannot alter metric semantics.
"""

from __future__ import annotations

import math
import ctypes
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Optional


def _enable_windows_dpi_awareness() -> None:
    """Ask Windows for crisp per-monitor rendering before creating Tk."""
    if sys.platform != "win32":
        return
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE (V2 context is preferred on Win10+).
        user32 = ctypes.windll.user32
        setter = getattr(user32, "SetProcessDpiAwarenessContext", None)
        if setter is not None:
            setter(ctypes.c_void_p(-4))  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            return
    except (AttributeError, OSError, TypeError):
        pass
    try:
        # Windows 8.1 fallback: PROCESS_PER_MONITOR_DPI_AWARE = 2.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError, TypeError):
        pass


def run_gui(args: Any) -> int:
    try:
        import tkinter as tk
    except Exception as exc:
        from codex_runtime_hud import tr
        print(tr(args.lang, "tk_missing"), file=sys.stderr)
        print(exc, file=sys.stderr)
        return 2

    from codex_runtime_hud import (
        IncrementalReaderPool,
        ParsedRollout,
        RolloutCandidate,
        SessionSelection,
        ViewMetrics,
        codex_home_default,
        fmt_num,
        fmt_time,
        load_settings,
        resolve_language,
        save_settings,
        set_startup_enabled,
        startup_enabled,
        tr,
    )
    from icon_assets import create_icon_image

    codex_home = Path(args.codex_home).expanduser() if args.codex_home else codex_home_default()
    fixed_file = Path(args.file).expanduser() if args.file else None
    settings = load_settings()
    language_mode = args.lang if args.lang != "auto" else settings.get("language", "auto")
    if language_mode not in {"auto", "zh-CN", "en"}:
        language_mode = "auto"
    lang = resolve_language(language_mode)
    state: dict[str, Any] = {
        "scope": "session" if args.session else settings.get("scope", "turn"),
        "expanded": bool(settings.get("expanded", False)),
        # The compact layout has its own anchor.  Keep it separate from the
        # expanded window's temporary, edge-clamped position so collapsing at
        # the right/bottom screen edge returns to the original compact spot.
        "compact_anchor": None,
        "always_on_top": bool(settings.get("always_on_top", True)),
        "language_mode": language_mode,
        "session_selection_mode": settings.get("session_selection_mode", "auto"),
        "selected_session_key": settings.get("selected_session_key", ""),
        "visible": True,
    }
    if state["scope"] not in {"turn", "session"}:
        state["scope"] = "turn"
    if state["session_selection_mode"] not in {"auto", "manual"}:
        state["session_selection_mode"] = "auto"
        state["selected_session_key"] = ""

    BG = "#18181a"
    SURFACE = "#1c1c1f"
    SURFACE_2 = "#242428"
    BORDER = "#343439"
    FG = "#f2f2f3"
    SECONDARY = "#a5a5aa"
    MUTED = "#6f6f75"
    ACCENT = "#e2bd68"
    STATUS_BLUE = "#70aee8"
    WARNING = "#b99b6a"
    DANGER = "#ad6f76"
    UI = ("Segoe UI Variable", 10)
    UI_SMALL = ("Segoe UI Variable", 9)
    UI_TINY = ("Segoe UI Variable", 8)
    MONO = ("Cascadia Mono", 10)
    # Tk has no native rounded, borderless window primitive.  On Windows the
    # transparent-color window attribute gives the canvas a real rounded
    # silhouette: the key color in the four corners is removed by the window
    # manager instead of merely being painted to look rounded.
    # Keep the key close to black so unsupported screenshot paths do not leak
    # a loud chroma color; it is removed by the Windows window manager.
    CORNER_KEY = "#010101"
    window_bg = BG

    _enable_windows_dpi_awareness()
    root = tk.Tk()
    root.title(tr(lang, "title"))
    root.configure(bg=window_bg)
    root.overrideredirect(True)
    root.resizable(False, False)
    if sys.platform == "win32":
        try:
            root.configure(bg=CORNER_KEY)
            root.wm_attributes("-transparentcolor", CORNER_KEY)
            window_bg = CORNER_KEY
        except tk.TclError:
            # Some Tcl/Tk builds do not expose transparentcolor.  The HUD
            # remains fully usable with a painted background in that case.
            root.configure(bg=BG)
    topmost_var = tk.BooleanVar(value=state["always_on_top"])
    language_var = tk.StringVar(value=language_mode)
    try:
        root.attributes("-alpha", 0.98)
    except Exception:
        pass

    canvas = tk.Canvas(root, bg=window_bg, bd=0, highlightthickness=0, cursor="hand2")
    canvas.pack(fill="both", expand=True)
    cache: dict[str, Any] = {"path": None, "parsed": None, "metrics": None, "candidate": None, "candidates": []}
    readers = IncrementalReaderPool(max_readers=4)
    sessions = SessionSelection()
    scope_bounds = (0, 0, 0, 0)
    session_bounds = (0, 0, 0, 0)
    drag: dict[str, Any] = {"offset_x": 0, "offset_y": 0, "press_x": 0, "press_y": 0, "moved": False, "target": "body"}
    tray_queue: queue.Queue[str] = queue.Queue()
    tray_icon: dict[str, Any] = {"icon": None}
    tray_state: dict[str, Any] = {"quit": False}
    context_menu: Optional[tk.Menu] = None
    session_popup: Optional[tk.Toplevel] = None

    def tk_screen_bounds() -> tuple[int, int, int, int]:
        """Use Tk's logical virtual-screen coordinates for DPI-safe placement."""
        try:
            left = int(root.winfo_vrootx())
            top = int(root.winfo_vrooty())
            width = int(root.winfo_vrootwidth())
            height = int(root.winfo_vrootheight())
            if width > 0 and height > 0:
                return left, top, width, height
        except Exception:
            pass
        return 0, 0, int(root.winfo_screenwidth()), int(root.winfo_screenheight())

    def clamp_tk_position(x: int, y: int, width: int, height: int) -> tuple[int, int]:
        left, top, screen_w, screen_h = tk_screen_bounds()
        margin = 8
        max_x = left + max(margin, screen_w - max(width, 1) - margin)
        max_y = top + max(margin, screen_h - max(height, 1) - margin)
        return max(left + margin, min(int(x), max_x)), max(top + margin, min(int(y), max_y))

    def window_size() -> tuple[int, int]:
        # Compact mode keeps the HUD narrow while giving its three headline
        # counters a readable vertical rhythm instead of squeezing them into
        # one horizontal strip.
        return (360, 214) if state["expanded"] else (220, 112)

    def rounded_rect(x1: int, y1: int, x2: int, y2: int, radius: int, fill: str, tags: Any = ()) -> None:
        radius = max(1, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
        canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=fill, outline="", tags=tags)
        canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, fill=fill, outline="", tags=tags)
        for box, start in (((x1, y1, x1 + 2 * radius, y1 + 2 * radius), 90),
                           ((x2 - 2 * radius, y1, x2, y1 + 2 * radius), 0),
                           ((x1, y2 - 2 * radius, x1 + 2 * radius, y2), 180),
                           ((x2 - 2 * radius, y2 - 2 * radius, x2, y2), 270)):
            canvas.create_arc(*box, start=start, extent=90, fill=fill, outline="", tags=tags)

    def draw_text(x: float, y: float, text: str, font: Any = UI, fill: str = FG, anchor: str = "w", tags: Any = ()) -> None:
        canvas.create_text(x, y, text=text, font=font, fill=fill, anchor=anchor, tags=tags)

    def format_context(metrics: Optional[ViewMetrics], missing: bool) -> tuple[str, Optional[float]]:
        if missing or metrics is None or not metrics.context_window or metrics.current_context_tokens is None:
            return tr(lang, "no_data"), None
        pct = max(0.0, min(100.0, metrics.current_context_tokens / metrics.context_window * 100.0))
        return f"{pct:.0f}%", pct

    def metric_values(parsed: Optional[ParsedRollout], metrics: Optional[ViewMetrics]) -> dict[str, str]:
        empty = tr(lang, "no_data")
        keys = ("cache", "input", "output", "steps", "llm", "tools", "ttft", "speed", "reasoning", "context")
        if parsed is None or metrics is None:
            return {key: empty for key in keys}
        usage_missing = metrics.usage_pending
        hit = metrics.usage.cache_hit
        context, _ = format_context(metrics, False)
        return {
            "cache": empty if usage_missing or hit is None else f"{hit:.0f}%",
            "input": empty if usage_missing else fmt_num(metrics.usage.input_tokens),
            "output": empty if usage_missing else fmt_num(metrics.usage.output_tokens),
            "steps": str(metrics.steps),
            "llm": fmt_time(metrics.llm_seconds_est) if metrics.wall_seconds > 0 else empty,
            "tools": fmt_time(metrics.tool_seconds),
            "ttft": empty if metrics.ttft_avg_ms is None else fmt_time(metrics.ttft_avg_ms / 1000.0),
            "speed": empty if metrics.tokens_per_second_est is None or not math.isfinite(metrics.tokens_per_second_est) else f"{metrics.tokens_per_second_est:.0f}",
            "reasoning": empty if usage_missing else fmt_num(metrics.usage.reasoning_output_tokens),
            "context": context,
        }

    def draw_ui() -> None:
        nonlocal scope_bounds, session_bounds
        width, height = window_size()
        canvas.delete("all")
        canvas.configure(width=width, height=height)
        # Two concentric silhouettes create a crisp one-pixel frame while the
        # transparent canvas corners remain outside the window body.
        rounded_rect(1, 1, width - 1, height - 1, 14, BORDER)
        rounded_rect(2, 2, width - 2, height - 2, 13, SURFACE)
        canvas.create_rectangle(2, 12, 3, height - 12, fill=ACCENT, outline="")
        parsed = cache.get("parsed")
        path = cache.get("path")
        metrics = cache.get("metrics")
        values = metric_values(parsed, metrics)

        if state["expanded"]:
            session_w, session_h = 108, 24
            session_x, session_y = 14, 8
            session_bounds = (session_x, session_y, session_x + session_w, session_y + session_h)
            button_fill = SURFACE_2 if fixed_file is None else "#242428"
            rounded_rect(session_x, session_y, session_x + session_w, session_y + session_h, 7, button_fill, ("sessions",))
            mode_text = tr(lang, "sessions_auto") if state["session_selection_mode"] == "auto" else tr(lang, "sessions_manual")
            draw_text(session_x + session_w / 2, session_y + 12, tr(lang, "sessions"), UI_TINY, FG if fixed_file is None else MUTED, "center", ("sessions",))
            scope_w, scope_h = 96, 24
            scope_x, scope_y = width - scope_w - 14, 10
            scope_bounds = (scope_x, scope_y, scope_x + scope_w, scope_y + scope_h)
            rounded_rect(scope_x, scope_y, scope_x + scope_w, scope_y + scope_h, 7, SURFACE_2, ("scope",))
            half = scope_w // 2
            active_x = scope_x if state["scope"] == "turn" else scope_x + half
            rounded_rect(active_x + 2, scope_y + 2, active_x + half - 2, scope_y + scope_h - 2, 5, "#30343b", ("scope",))
            draw_text(scope_x + half // 2, scope_y + 12, tr(lang, "current"), UI_TINY, FG if state["scope"] == "turn" else MUTED, "center", ("scope",))
            draw_text(scope_x + half + half // 2, scope_y + 12, tr(lang, "session"), UI_TINY, FG if state["scope"] == "session" else MUTED, "center", ("scope",))

            model = metrics.model if metrics and metrics.model and args.model else "Codex"
            candidate = cache.get("candidate")
            if candidate is not None and candidate.is_active():
                indicator_color = ACCENT
            elif candidate is not None and candidate.is_waiting_for_update():
                indicator_color = STATUS_BLUE
            else:
                indicator_color = MUTED
            canvas.create_oval(16, 39, 22, 45, fill=indicator_color, outline="")
            draw_text(29, 42, model, ("Segoe UI Variable", 11), FG)
            session_name = candidate.display_name() if candidate is not None else tr(lang, "not_found")
            draw_text(16, 56, f"{session_name} · {mode_text}", UI_TINY, SECONDARY)
            if args.debug and path is not None:
                draw_text(16, 68, path.name, UI_TINY, MUTED)

            for x, (label, value) in zip((18, 132, 246), ((tr(lang, "cache"), values["cache"]), ("In", values["input"]), ("Out", values["output"]))):
                draw_text(x, 78, label, UI_TINY, SECONDARY)
                draw_text(x, 95, value, ("Cascadia Mono", 13), FG)

            runtime = (
                (tr(lang, "steps"), values["steps"]),
                (tr(lang, "ttft"), values["ttft"]),
                (tr(lang, "llm"), values["llm"]),
                (tr(lang, "tools"), values["tools"]),
                (tr(lang, "speed"), values["speed"] + (" tok/s" if values["speed"] != tr(lang, "no_data") else "")),
                (tr(lang, "reasoning"), values["reasoning"]),
            )
            for index, (label, value) in enumerate(runtime):
                x = 18 + (index % 3) * 114
                y = 126 + (index // 3) * 31
                draw_text(x, y, label, UI_TINY, MUTED)
                draw_text(x, y + 14, value, MONO, SECONDARY)

            context_text, pct = format_context(metrics, parsed is None or metrics is None)
            draw_text(18, 204, tr(lang, "context"), UI_TINY, MUTED)
            bar_x, bar_y, bar_w = 78, 201, 224
            rounded_rect(bar_x, bar_y, bar_x + bar_w, bar_y + 5, 3, "#303035")
            if pct is not None and pct > 0:
                bar_color = DANGER if pct > 90 else WARNING if pct >= 70 else "#7f8998"
                rounded_rect(bar_x, bar_y, bar_x + max(3, int(bar_w * pct / 100.0)), bar_y + 5, 3, bar_color)
            draw_text(width - 18, 204, context_text, UI_TINY, SECONDARY, "e")
            if args.debug and path is not None and parsed is not None and metrics is not None:
                draw_text(18, 210, f"errors={parsed.parse_errors} · coverage={metrics.tool_timing_coverage*100:.0f}%", UI_TINY, MUTED)
        else:
            session_w, session_h = 72, 24
            session_x, session_y = 10, 8
            session_bounds = (session_x, session_y, session_x + session_w, session_y + session_h)
            rounded_rect(session_x, session_y, session_x + session_w, session_y + session_h, 7, SURFACE_2, ("sessions",))
            draw_text(session_x + session_w / 2, session_y + 12, tr(lang, "sessions"), UI_TINY, FG if fixed_file is None else MUTED, "center", ("sessions",))
            scope_w, scope_h = 72, 24
            scope_x, scope_y = width - scope_w - 10, 8
            scope_bounds = (scope_x, scope_y, scope_x + scope_w, scope_y + scope_h)
            rounded_rect(scope_x, scope_y, scope_x + scope_w, scope_y + scope_h, 7, SURFACE_2, ("scope",))
            rounded_rect(scope_x + 2, scope_y + 2, scope_x + scope_w - 2, scope_y + scope_h - 2, 5, "#30343b", ("scope",))
            draw_text(scope_x + scope_w / 2, scope_y + 12, tr(lang, "current") if state["scope"] == "turn" else tr(lang, "session"), UI_TINY, FG, "center", ("scope",))
            for index, (label, value) in enumerate(
                ((tr(lang, "cache"), values["cache"]), ("In", values["input"]), ("Out", values["output"]))
            ):
                y = 49 + index * 20
                draw_text(18, y, label, UI_TINY, SECONDARY)
                draw_text(82, y, value, MONO, FG)

    def persist_ui() -> None:
        try:
            if not state["expanded"]:
                state["compact_anchor"] = (int(root.winfo_x()), int(root.winfo_y()))
            settings.update({
                "x": int(root.winfo_x()),
                "y": int(root.winfo_y()),
                "expanded": bool(state["expanded"]),
                "scope": state["scope"],
                "language": state["language_mode"],
                "always_on_top": bool(state["always_on_top"]),
                "session_selection_mode": state["session_selection_mode"],
                "selected_session_key": state["selected_session_key"],
            })
            save_settings(settings)
        except Exception:
            pass

    def move_window_to_saved_position() -> None:
        width, height = window_size()
        left, top, screen_w, screen_h = tk_screen_bounds()
        default_x = left + screen_w - width - 24
        x, y = clamp_tk_position(int(settings.get("x", default_x)), int(settings.get("y", top + 24)), width, height)
        root.geometry(f"{width}x{height}+{x}+{y}")
        if not state["expanded"]:
            state["compact_anchor"] = (x, y)

    def set_visible(visible: bool) -> None:
        state["visible"] = bool(visible)
        if visible:
            root.deiconify()
            root.attributes("-topmost", state["always_on_top"])
        else:
            persist_ui()
            root.withdraw()

    def set_expanded(expanded: bool, persist: bool = True) -> None:
        expanded = bool(expanded)
        was_expanded = bool(state["expanded"])
        if expanded and not was_expanded:
            state["compact_anchor"] = (int(root.winfo_x()), int(root.winfo_y()))
        state["expanded"] = expanded
        draw_ui()
        root.update_idletasks()
        if was_expanded and not expanded and state["compact_anchor"] is not None:
            # Restore against the compact layout, not the expanded layout's
            # clamped left/top coordinate.  This is what keeps a HUD parked
            # at the right edge from appearing to collapse toward the left.
            x, y = state["compact_anchor"]
        else:
            x, y = root.winfo_x(), root.winfo_y()
        x, y = clamp_tk_position(x, y, *window_size())
        root.geometry(f"{window_size()[0]}x{window_size()[1]}+{x}+{y}")
        if not expanded:
            state["compact_anchor"] = (x, y)
        if persist:
            persist_ui()

    def toggle_expanded(_event: Any = None) -> str:
        set_expanded(not state["expanded"])
        return "break"

    def set_scope_value(value: str) -> None:
        state["scope"] = value
        persist_ui()
        draw_ui()

    def toggle_scope(_event: Any = None) -> str:
        set_scope_value("session" if state["scope"] == "turn" else "turn")
        return "break"

    def copy_visible(_event: Any = None) -> str:
        metrics = cache.get("metrics")
        text = tr(lang, "not_found") if metrics is None else metrics.status_line(include_model=args.model, lang=lang)
        try:
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
        except Exception:
            pass
        return "break"

    def set_topmost(enabled: bool) -> None:
        state["always_on_top"] = bool(enabled)
        topmost_var.set(state["always_on_top"])
        root.attributes("-topmost", state["always_on_top"])
        persist_ui()

    def reset_position() -> None:
        left, top, screen_w, _ = tk_screen_bounds()
        width, height = window_size()
        x, y = clamp_tk_position(left + screen_w - width - 24, top + 24, width, height)
        root.geometry(f"{width}x{height}+{x}+{y}")
        persist_ui()

    def set_language(mode: str) -> None:
        nonlocal lang
        state["language_mode"] = mode
        language_var.set(mode)
        lang = resolve_language(mode)
        persist_ui()
        build_context_menu()
        draw_ui()
        # pystray may cache labels on Windows; force the native tray menu to
        # re-evaluate its dynamic text/checked callbacks after a language
        # selection changes.
        if tray_icon["icon"] is not None:
            try:
                refresh_tray_menu()
            except Exception:
                pass

    def refresh_tray_menu() -> None:
        """Replaced after pystray starts; keeps non-tray runs harmless."""

    def close_session_picker() -> None:
        nonlocal session_popup
        if session_popup is not None:
            try:
                session_popup.grab_release()
            except Exception:
                pass
            try:
                session_popup.destroy()
            except Exception:
                pass
        session_popup = None

    def set_session_auto() -> None:
        state["session_selection_mode"] = "auto"
        state["selected_session_key"] = ""
        persist_ui()
        close_session_picker()
        root.after_idle(refresh_once)

    def set_session_manual(key: str) -> None:
        state["session_selection_mode"] = "manual"
        state["selected_session_key"] = key
        persist_ui()
        close_session_picker()
        root.after_idle(refresh_once)

    def session_activity(candidate: RolloutCandidate) -> tuple[str, str]:
        if candidate.is_active():
            return tr(lang, "session_active"), ACCENT
        if candidate.is_waiting_for_update():
            return tr(lang, "session_waiting"), STATUS_BLUE
        return tr(lang, "session_idle"), MUTED

    def session_row_text(candidate: RolloutCandidate) -> str:
        activity, _color = session_activity(candidate)
        return f"{candidate.display_name()}  ·  {activity}"

    def select_session_row(_event: Any, key: str) -> str:
        """Select after mouse release so the underlying HUD never reopens the picker."""
        set_session_manual(key)
        return "break"

    def show_session_picker() -> None:
        nonlocal session_popup
        if fixed_file is not None:
            return
        if session_popup is not None:
            close_session_picker()
            return
        candidates = cache.get("candidates", [])
        popup = tk.Toplevel(root)
        session_popup = popup
        popup.title(tr(lang, "session_picker_title"))
        popup.configure(bg=SURFACE)
        popup.overrideredirect(True)
        popup.attributes("-topmost", state["always_on_top"])
        frame = tk.Frame(popup, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill="both", expand=True)
        header = tk.Label(frame, text=tr(lang, "session_picker_title"), bg=SURFACE, fg=FG, font=UI)
        header.pack(fill="x", padx=12, pady=(10, 4))
        auto_active = state["session_selection_mode"] == "auto"
        auto = tk.Button(frame, text=("● " if auto_active else "○ ") + tr(lang, "sessions_auto"), command=set_session_auto,
                         anchor="w", relief="flat", bd=0, bg=SURFACE_2, activebackground="#30343b", fg=FG, activeforeground=FG,
                         font=UI_SMALL, padx=12, pady=6)
        auto.pack(fill="x", padx=8, pady=(0, 6))
        holder = tk.Frame(frame, bg=SURFACE)
        holder.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        list_canvas = tk.Canvas(holder, bg=SURFACE, bd=0, highlightthickness=0, width=316, height=min(240, max(34, len(candidates) * 34)))
        scrollbar = tk.Scrollbar(holder, orient="vertical", command=list_canvas.yview)
        rows = tk.Frame(list_canvas, bg=SURFACE)
        rows_window = list_canvas.create_window((0, 0), window=rows, anchor="nw")
        list_canvas.configure(yscrollcommand=scrollbar.set)
        list_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        rows.bind("<Configure>", lambda _e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))
        list_canvas.bind("<Configure>", lambda e: list_canvas.itemconfigure(rows_window, width=e.width))
        if not candidates:
            tk.Label(rows, text=tr(lang, "sessions_none"), bg=SURFACE, fg=MUTED, anchor="w", font=UI_SMALL, padx=12, pady=8).pack(fill="x")
        for candidate in candidates:
            selected = state["session_selection_mode"] == "manual" and state["selected_session_key"] == candidate.key
            activity, status_color = session_activity(candidate)
            row = tk.Frame(rows, bg=SURFACE_2 if selected else SURFACE, cursor="hand2")
            row.pack(fill="x", pady=1)
            name_label = tk.Label(row, text=("● " if selected else "○ ") + candidate.display_name(), bg=row.cget("bg"), fg=FG,
                                  anchor="w", font=UI_SMALL, padx=10, pady=6, cursor="hand2")
            name_label.pack(side="left", fill="x", expand=True)
            status_label = tk.Label(row, text=activity, bg=row.cget("bg"), fg=status_color, anchor="e", font=UI_TINY, padx=10, pady=6, cursor="hand2")
            status_label.pack(side="right")
            for widget in (row, name_label, status_label):
                widget.bind("<ButtonRelease-1>", lambda event, key=candidate.key: select_session_row(event, key))
        popup.bind("<Escape>", lambda _e: close_session_picker())
        popup.protocol("WM_DELETE_WINDOW", close_session_picker)
        popup.update_idletasks()
        x = root.winfo_x()
        y = root.winfo_y() + root.winfo_height() + 6
        x, y = clamp_tk_position(x, y, popup.winfo_reqwidth(), popup.winfo_reqheight())
        popup.geometry(f"+{x}+{y}")
        popup.focus_force()
        try:
            popup.grab_set()
        except tk.TclError:
            pass

    def quit_app(_event: Any = None) -> None:
        persist_ui()
        tray_state["quit"] = True
        if tray_icon["icon"] is not None:
            try:
                tray_icon["icon"].stop()
            except Exception:
                pass
        root.destroy()

    def show_context_menu(event: Any) -> str:
        if context_menu is not None:
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()
        return "break"

    def build_context_menu() -> None:
        nonlocal context_menu
        if context_menu is not None:
            try:
                context_menu.destroy()
            except Exception:
                pass
        context_menu = tk.Menu(root, tearoff=False)
        context_menu.add_command(label=tr(lang, "current"), command=lambda: set_scope_value("turn"))
        context_menu.add_command(label=tr(lang, "session"), command=lambda: set_scope_value("session"))
        context_menu.add_command(label=tr(lang, "sessions"), command=show_session_picker, state="normal" if fixed_file is None else "disabled")
        context_menu.add_separator()
        context_menu.add_checkbutton(label=tr(lang, "topmost"), variable=topmost_var, command=lambda: set_topmost(topmost_var.get()))
        context_menu.add_checkbutton(label=tr(lang, "startup"), command=lambda: set_startup_enabled(not startup_enabled()))
        context_menu.add_separator()
        language_menu = tk.Menu(context_menu, tearoff=False)
        language_menu.add_radiobutton(label=tr(lang, "language_auto"), variable=language_var, value="auto", command=lambda: set_language("auto"))
        language_menu.add_radiobutton(label=tr(lang, "language_english"), variable=language_var, value="en", command=lambda: set_language("en"))
        language_menu.add_radiobutton(label=tr(lang, "language_chinese"), variable=language_var, value="zh-CN", command=lambda: set_language("zh-CN"))
        context_menu.add_cascade(label=tr(lang, "language"), menu=language_menu)
        context_menu.add_separator()
        context_menu.add_command(label=tr(lang, "reset_position"), command=reset_position)
        context_menu.add_command(label=tr(lang, "copy"), command=copy_visible)
        context_menu.add_command(label=tr(lang, "quit"), command=quit_app)

    def on_press(event: Any) -> None:
        in_scope = scope_bounds[0] <= event.x <= scope_bounds[2] and scope_bounds[1] <= event.y <= scope_bounds[3]
        in_sessions = session_bounds[0] <= event.x <= session_bounds[2] and session_bounds[1] <= event.y <= session_bounds[3]
        target = "sessions" if in_sessions else "scope" if in_scope else "body"
        drag.update(offset_x=event.x_root - root.winfo_x(), offset_y=event.y_root - root.winfo_y(), press_x=event.x_root, press_y=event.y_root, moved=False, target=target)

    def on_move(event: Any) -> None:
        if max(abs(event.x_root - drag["press_x"]), abs(event.y_root - drag["press_y"])) >= 5:
            drag["moved"] = True
        if drag["moved"]:
            root.geometry(f"+{event.x_root - drag['offset_x']}+{event.y_root - drag['offset_y']}")

    def on_release(_event: Any) -> str:
        if drag["moved"]:
            persist_ui()
        elif drag["target"] == "scope":
            toggle_scope()
        elif drag["target"] == "sessions":
            show_session_picker()
        else:
            toggle_expanded()
        return "break"

    def render() -> None:
        parsed, path = cache.get("parsed"), cache.get("path")
        cache["metrics"] = parsed.metrics(state["scope"]) if parsed is not None and path is not None else None
        draw_ui()

    def refresh_once() -> None:
        candidate: Optional[RolloutCandidate] = None
        candidates: list[RolloutCandidate] = []
        if fixed_file is not None:
            path = fixed_file
        else:
            resolution = sessions.resolve(codex_home, state["session_selection_mode"], state["selected_session_key"])
            candidate, candidates, path = resolution.candidate, resolution.candidates, resolution.candidate.path if resolution.candidate else None
            if resolution.mode != state["session_selection_mode"] or resolution.selected_key != state["selected_session_key"]:
                state["session_selection_mode"] = resolution.mode
                state["selected_session_key"] = resolution.selected_key
                persist_ui()
        cache["candidate"] = candidate
        cache["candidates"] = candidates
        if path is None or not path.exists():
            cache.update(path=None, parsed=None, metrics=None)
        else:
            cache.update(path=path, parsed=readers.read(path))
        render()
        refresh_tray_menu()

    def refresh() -> None:
        refresh_once()
        root.after(max(100, int(args.interval * 1000)), refresh)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_move)
    canvas.bind("<ButtonRelease-1>", on_release)
    canvas.bind("<Button-2>", copy_visible)
    canvas.bind("<Button-3>", show_context_menu)
    root.bind("<Button-3>", show_context_menu)
    root.bind("<Escape>", lambda _e: set_visible(False))
    root.bind("<Control-c>", copy_visible)
    root.bind("<Key-s>", toggle_scope)
    root.bind("<Key-S>", toggle_scope)
    root.bind("<space>", toggle_expanded)
    root.protocol("WM_DELETE_WINDOW", lambda: set_visible(False))

    build_context_menu()
    root.attributes("-topmost", state["always_on_top"])
    move_window_to_saved_position()
    draw_ui()

    try:
        import pystray
        image = create_icon_image(64)

        def tray_action(action: str):
            return lambda icon, item: tray_queue.put(action)

        def build_tray_menu():
            language_menu = pystray.Menu(
                pystray.MenuItem(lambda item: tr(lang, "language_auto"), tray_action("language:auto"), checked=lambda item: state["language_mode"] == "auto", radio=True),
                pystray.MenuItem(lambda item: tr(lang, "language_english"), tray_action("language:en"), checked=lambda item: state["language_mode"] == "en", radio=True),
                pystray.MenuItem(lambda item: tr(lang, "language_chinese"), tray_action("language:zh-CN"), checked=lambda item: state["language_mode"] == "zh-CN", radio=True),
            )
            session_items = [
                pystray.MenuItem(lambda item: tr(lang, "sessions_auto"), tray_action("session:auto"), checked=lambda item: state["session_selection_mode"] == "auto", radio=True),
            ]
            for candidate in cache.get("candidates", []):
                session_items.append(pystray.MenuItem(
                    candidate.display_name(), tray_action(f"session:{candidate.key}"),
                    checked=lambda item, key=candidate.key: state["session_selection_mode"] == "manual" and state["selected_session_key"] == key,
                    radio=True,
                ))
            return pystray.Menu(
                pystray.MenuItem(lambda item: tr(lang, "show"), tray_action("show")),
                pystray.MenuItem(lambda item: tr(lang, "hide"), tray_action("hide")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(lambda item: tr(lang, "sessions"), pystray.Menu(*session_items), enabled=lambda item: fixed_file is None),
                pystray.MenuItem(lambda item: tr(lang, "language"), language_menu),
                pystray.MenuItem(lambda item: tr(lang, "startup"), tray_action("startup"), checked=lambda item: startup_enabled()),
                pystray.MenuItem(lambda item: tr(lang, "about"), tray_action("about")),
                pystray.MenuItem(lambda item: tr(lang, "quit"), tray_action("quit")),
            )

        def refresh_tray_menu() -> None:
            icon = tray_icon["icon"]
            if icon is not None:
                icon.menu = build_tray_menu()
                icon.title = tr(lang, "title")
                icon.update_menu()

        icon = pystray.Icon("CodexRuntimeHUD", image, tr(lang, "title"), build_tray_menu())
        tray_icon["icon"] = icon
        threading.Thread(target=icon.run, daemon=True, name="codex-overlay-tray").start()
    except Exception:
        pass

    def pump_tray() -> None:
        try:
            while True:
                action = tray_queue.get_nowait()
                if action == "show":
                    set_visible(True)
                elif action == "hide":
                    set_visible(False)
                elif action == "startup":
                    set_startup_enabled(not startup_enabled())
                elif action == "session:auto":
                    set_session_auto()
                elif action.startswith("session:"):
                    set_session_manual(action.split(":", 1)[1])
                elif action.startswith("language:"):
                    set_language(action.split(":", 1)[1])
                elif action == "about":
                    try:
                        from tkinter import messagebox
                        messagebox.showinfo(tr(lang, "title"), f"{tr(lang, 'unofficial')}\n\n{tr(lang, 'local_only')}")
                    except Exception:
                        pass
                elif action == "quit":
                    quit_app()
        except queue.Empty:
            pass
        if not tray_state["quit"]:
            root.after(100, pump_tray)

    pump_tray()
    # Let Tk map the window before scanning the session tree.  On machines
    # with many rollout files this keeps the first paint responsive; the
    # normal refresh loop still starts immediately after the event loop begins.
    root.after(0, refresh)
    root.mainloop()
    return 0

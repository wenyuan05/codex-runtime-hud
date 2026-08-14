"""Canvas-based Tk UI for Codex Token Overlay.

The parser remains in :mod:`codex_hud`; this module only owns presentation,
interaction and UI preferences so visual changes cannot alter metric semantics.
"""

from __future__ import annotations

import math
import queue
import threading
from pathlib import Path
from typing import Any, Optional


def run_gui(args: Any) -> int:
    try:
        import tkinter as tk
    except Exception as exc:
        from codex_hud import tr
        import sys
        print(tr(args.lang, "tk_missing"), file=sys.stderr)
        print(exc, file=sys.stderr)
        return 2

    from codex_hud import (
        IncrementalRolloutReader,
        ParsedRollout,
        RootThreadSelector,
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
        "always_on_top": bool(settings.get("always_on_top", True)),
        "language_mode": language_mode,
        "visible": True,
    }
    if state["scope"] not in {"turn", "session"}:
        state["scope"] = "turn"

    BG = "#18181a"
    SURFACE = "#1c1c1f"
    SURFACE_2 = "#242428"
    BORDER = "#343439"
    FG = "#f2f2f3"
    SECONDARY = "#a5a5aa"
    MUTED = "#6f6f75"
    ACCENT = "#9bb2d2"
    WARNING = "#b99b6a"
    DANGER = "#ad6f76"
    UI = ("Segoe UI Variable", 10)
    UI_SMALL = ("Segoe UI Variable", 9)
    UI_TINY = ("Segoe UI Variable", 8)
    MONO = ("Cascadia Mono", 10)

    root = tk.Tk()
    root.title(tr(lang, "title"))
    root.configure(bg=BG)
    root.overrideredirect(True)
    root.resizable(False, False)
    topmost_var = tk.BooleanVar(value=state["always_on_top"])
    language_var = tk.StringVar(value=language_mode)
    try:
        root.attributes("-alpha", 0.98)
    except Exception:
        pass

    canvas = tk.Canvas(root, bg=BG, bd=0, highlightthickness=0, cursor="hand2")
    canvas.pack(fill="both", expand=True)
    cache: dict[str, Any] = {"path": None, "parsed": None, "metrics": None}
    reader = IncrementalRolloutReader()
    selector = RootThreadSelector()
    scope_bounds = (0, 0, 0, 0)
    drag: dict[str, Any] = {"offset_x": 0, "offset_y": 0, "press_x": 0, "press_y": 0, "moved": False, "target": "body"}
    tray_queue: queue.Queue[str] = queue.Queue()
    tray_icon: dict[str, Any] = {"icon": None}
    tray_state: dict[str, Any] = {"quit": False}
    context_menu: Optional[tk.Menu] = None

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
        return (360, 214) if state["expanded"] else (340, 40)

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
        nonlocal scope_bounds
        width, height = window_size()
        canvas.delete("all")
        canvas.configure(width=width, height=height)
        rounded_rect(1, 1, width - 1, height - 1, 10, SURFACE)
        canvas.create_rectangle(1, 10, 2, height - 10, fill=BORDER, outline="")
        parsed = cache.get("parsed")
        path = cache.get("path")
        metrics = cache.get("metrics")
        values = metric_values(parsed, metrics)

        if state["expanded"]:
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
            canvas.create_oval(16, 14, 22, 20, fill=ACCENT if metrics and metrics.active else MUTED, outline="")
            draw_text(29, 17, model, ("Segoe UI Variable", 11), FG)
            draw_text(29, 32, tr(lang, "model_active") if metrics and metrics.active else tr(lang, "model_idle"), UI_TINY, SECONDARY)
            if args.debug and path is not None:
                draw_text(16, 44, path.name, UI_TINY, MUTED)

            for x, (label, value) in zip((18, 132, 246), ((tr(lang, "cache"), values["cache"]), ("In", values["input"]), ("Out", values["output"]))):
                draw_text(x, 62, label, UI_TINY, SECONDARY)
                draw_text(x, 79, value, ("Cascadia Mono", 13), FG)

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
                y = 112 + (index // 3) * 31
                draw_text(x, y, label, UI_TINY, MUTED)
                draw_text(x, y + 14, value, MONO, SECONDARY)

            context_text, pct = format_context(metrics, parsed is None or metrics is None)
            draw_text(18, 192, tr(lang, "context"), UI_TINY, MUTED)
            bar_x, bar_y, bar_w = 78, 189, 224
            rounded_rect(bar_x, bar_y, bar_x + bar_w, bar_y + 5, 3, "#303035")
            if pct is not None and pct > 0:
                bar_color = DANGER if pct > 90 else WARNING if pct >= 70 else "#7f8998"
                rounded_rect(bar_x, bar_y, bar_x + max(3, int(bar_w * pct / 100.0)), bar_y + 5, 3, bar_color)
            draw_text(width - 18, 192, context_text, UI_TINY, SECONDARY, "e")
            if args.debug and path is not None and parsed is not None and metrics is not None:
                draw_text(18, 207, f"errors={parsed.parse_errors} · coverage={metrics.tool_timing_coverage*100:.0f}%", UI_TINY, MUTED)
        else:
            scope_w, scope_h = 72, 24
            scope_x, scope_y = 10, 8
            scope_bounds = (scope_x, scope_y, scope_x + scope_w, scope_y + scope_h)
            rounded_rect(scope_x, scope_y, scope_x + scope_w, scope_y + scope_h, 7, SURFACE_2, ("scope",))
            rounded_rect(scope_x + 2, scope_y + 2, scope_x + scope_w - 2, scope_y + scope_h - 2, 5, "#30343b", ("scope",))
            draw_text(scope_x + scope_w / 2, scope_y + 12, tr(lang, "current") if state["scope"] == "turn" else tr(lang, "session"), UI_TINY, FG, "center", ("scope",))
            draw_text(96, 20, "Cache", UI_TINY, SECONDARY)
            draw_text(132, 20, values["cache"], MONO, FG)
            draw_text(184, 20, "In", UI_TINY, SECONDARY)
            draw_text(207, 20, values["input"], MONO, FG)
            draw_text(260, 20, "Out", UI_TINY, SECONDARY)
            draw_text(294, 20, values["output"], MONO, FG)

    def persist_ui() -> None:
        try:
            settings.update({
                "x": int(root.winfo_x()),
                "y": int(root.winfo_y()),
                "expanded": bool(state["expanded"]),
                "scope": state["scope"],
                "language": state["language_mode"],
                "always_on_top": bool(state["always_on_top"]),
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

    def set_visible(visible: bool) -> None:
        state["visible"] = bool(visible)
        if visible:
            root.deiconify()
            root.attributes("-topmost", state["always_on_top"])
        else:
            persist_ui()
            root.withdraw()

    def set_expanded(expanded: bool, persist: bool = True) -> None:
        state["expanded"] = bool(expanded)
        draw_ui()
        x, y = clamp_tk_position(root.winfo_x(), root.winfo_y(), *window_size())
        root.geometry(f"{window_size()[0]}x{window_size()[1]}+{x}+{y}")
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
        drag.update(offset_x=event.x_root - root.winfo_x(), offset_y=event.y_root - root.winfo_y(), press_x=event.x_root, press_y=event.y_root, moved=False, target="scope" if in_scope else "body")

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
        else:
            toggle_expanded()
        return "break"

    def render() -> None:
        parsed, path = cache.get("parsed"), cache.get("path")
        cache["metrics"] = parsed.metrics(state["scope"]) if parsed is not None and path is not None else None
        draw_ui()

    def refresh() -> None:
        path = fixed_file if fixed_file else selector.choose(codex_home)
        if path is None or not path.exists():
            cache.update(path=None, parsed=None, metrics=None)
        else:
            cache.update(path=path, parsed=reader.read(path))
        render()
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

        language_menu = pystray.Menu(
            pystray.MenuItem(lambda item: tr(lang, "language_auto"), tray_action("language:auto"), checked=lambda item: state["language_mode"] == "auto", radio=True),
            pystray.MenuItem(lambda item: tr(lang, "language_english"), tray_action("language:en"), checked=lambda item: state["language_mode"] == "en", radio=True),
            pystray.MenuItem(lambda item: tr(lang, "language_chinese"), tray_action("language:zh-CN"), checked=lambda item: state["language_mode"] == "zh-CN", radio=True),
        )
        menu = pystray.Menu(
            pystray.MenuItem(lambda item: tr(lang, "show"), tray_action("show")),
            pystray.MenuItem(lambda item: tr(lang, "hide"), tray_action("hide")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: tr(lang, "language"), language_menu),
            pystray.MenuItem(lambda item: tr(lang, "startup"), tray_action("startup"), checked=lambda item: startup_enabled()),
            pystray.MenuItem(lambda item: tr(lang, "about"), tray_action("about")),
            pystray.MenuItem(lambda item: tr(lang, "quit"), tray_action("quit")),
        )
        icon = pystray.Icon("CodexTokenOverlay", image, tr(lang, "title"), menu)
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
    refresh()
    root.mainloop()
    return 0

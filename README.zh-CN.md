# Codex Token Overlay

[English README](README.md)

![演示](assets/demo.gif)

> **Unofficial / Not affiliated with OpenAI（非官方，与 OpenAI 无隶属关系）。**

这是一个 Windows 端 Codex Desktop / Codex CLI Token 使用量悬浮窗。它只读取本地 rollout JSONL，不调用任何 API。

## 隐私

- 只读 `~/.codex/sessions` 与 `~/.codex/archived_sessions` 下的本地 Codex session 文件。
- **不会**读取 `auth.json`、API Key、`.env`、rollout 之外的提示词或凭据。
- 应用运行时不联网；GitHub、Python、PyInstaller 只用于分发和构建。
- 设置文件只保存窗口坐标和 UI 偏好：`%LOCALAPPDATA%\CodexTokenOverlay\settings.json`。
  UI 偏好包括 `expanded`、`scope`、`language`（`auto`、`en`、`zh-CN`）和 `always_on_top`。`Auto` 跟随 Windows UI 语言；手动选择中英文后会记住该选择，改回 `Auto` 才恢复自动检测。

## 下载

从 [Releases](https://github.com/wenyuan05/codex-token-overlay/releases) 下载 `CodexTokenOverlay-v0.3.1-windows-x64.exe`。它是免安装、未签名的 Windows x64 EXE，首次运行可能出现 SmartScreen 提示。

可用 `SHA256SUMS.txt` 校验：

```powershell
Get-FileHash .\CodexTokenOverlay-v0.3.1-windows-x64.exe -Algorithm SHA256
```

双击 EXE 即可运行。折叠 HUD 只显示范围、Cache、In、Out；点击主体展开详细面板。点击“本轮/累计”只切换范围，不会展开。拖动背景区域移动窗口；右键打开原生菜单，可切换范围、始终置顶、开机启动、语言、重置位置、复制和退出。托盘菜单提供显示/隐藏、范围、开机启动、语言（自动/English/简体中文）、关于和退出。开机启动默认关闭，启用后只写入当前用户注册表；位置和 UI 偏好会跨重启保留。

## 源码运行

需要带 Tk 的 Python 3.10+：

```powershell
py -3 -m pip install -r requirements-runtime.txt
py -3 codex_hud.py
py -3 codex_hud.py --once --debug
py -3 codex_hud.py --once --file .\sample_rollout.jsonl --lang en
```

默认根据 Windows UI 语言选择界面（`zh-*` → 简体中文，其余 → English）。也可以使用 `--lang auto`、`--lang zh-CN` 或 `--lang en` 覆盖。

## 构建

在 Windows PowerShell 中执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build.ps1
```

产物为 `dist\CodexTokenOverlay.exe` 和 `dist\SHA256SUMS.txt`；GitHub Actions 会执行相同检查。

## 操作与指标

- 单击主体或按 Space：展开/收起。
- 拖动主体：移动并保存悬浮窗位置。
- 点击“本轮/累计”：切换当前轮或当前 session 累计统计。
- 中键/Ctrl+C：复制当前信息；右键：打开原生设置菜单；Escape：隐藏到托盘。
- 缓存命中率 = `cached_input_tokens / input_tokens`。
- 本轮优先使用精确的 `raw_response_completed` usage，否则使用累计值差分。
- 工具耗时使用区间并集，并发工具不会重复计时。
- 工具事件统一兼容 response-item call/output、legacy begin/end，以及未来的 `item_started/item_completed` wrapper。
- 自动选择最新的合格 root user thread，并排除 subagent/memory consolidation；`--file` 可强制指定 rollout。
- 大型 rollout 会增量扫描 turn 元数据，不会因为最新 turn 位于文件中间而在启动时误选旧数据。
- Codex 尚未持久化 `token_count` 或 response usage 时，Token 会显示为待定，而不是误报为 0。

## 许可证

MIT，详见 [LICENSE](LICENSE)。

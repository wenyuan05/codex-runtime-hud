# Codex Runtime HUD

[English README](README.md)

![演示](assets/codex-runtime-hud-demo.gif)

> **Unofficial / Not affiliated with OpenAI（非官方，与 OpenAI 无隶属关系）。**

这是一个专注于 Codex Desktop / Codex CLI **单轮实时表现**的 Windows 悬浮窗。它会跟随 root user rollout 的 JSONL 增量写入实时刷新，不调用任何 API。

## 监控重点

默认视图是当前轮，而不是历史仪表盘。单轮运行期间，HUD 展示 LLM 耗时、TTFT、工具耗时、Steps、Token 速度、输入/输出 Token、缓存命中率和上下文使用率；“累计”视图仅作为 session 累计对照。

## 隐私

- 只读 `~/.codex/sessions` 与 `~/.codex/archived_sessions` 下的本地 Codex session 文件。
- **不会**读取 `auth.json`、API Key、`.env`、rollout 之外的提示词或凭据。
- 应用运行时不联网；GitHub、Python、PyInstaller 只用于分发和构建。
- 设置文件只保存窗口坐标和 UI 偏好：`%LOCALAPPDATA%\CodexRuntimeHUD\settings.json`。
  UI 偏好包括 `expanded`、`scope`、`language`（`auto`、`en`、`zh-CN`）和 `always_on_top`。`Auto` 跟随 Windows UI 语言；手动选择中英文后会记住该选择，改回 `Auto` 才恢复自动检测。
- 现有 `%LOCALAPPDATA%\CodexTokenOverlay\settings.json` 会作为一次性兼容回退读取；之后的新设置写入 `CodexRuntimeHUD` 文件夹。

## 下载

从 [Releases](https://github.com/wenyuan05/codex-runtime-hud/releases) 下载最新的免安装 Windows x64 EXE。历史 v0.3.1 资产仍保留旧文件名；新构建使用 `CodexRuntimeHUD` 名称。EXE 未签名，首次运行可能出现 SmartScreen 提示。

可用 `SHA256SUMS.txt` 校验：

```powershell
Get-FileHash .\CodexRuntimeHUD.exe -Algorithm SHA256
```

双击 EXE 即可运行。折叠 HUD 只显示范围、Cache、In、Out；点击主体展开详细面板。点击“本轮/累计”只切换范围，不会展开。拖动背景区域移动窗口；右键打开原生菜单，可切换范围、始终置顶、开机启动、语言、重置位置、复制和退出。托盘菜单提供显示/隐藏、范围、开机启动、语言（自动/English/简体中文）、关于和退出。开机启动默认关闭，启用后只写入当前用户注册表；位置和 UI 偏好会跨重启保留。

## 源码运行

需要带 Tk 的 Python 3.10+：

```powershell
py -3 -m pip install -r requirements-runtime.txt
py -3 codex_runtime_hud.py
py -3 codex_runtime_hud.py --once --debug
py -3 codex_runtime_hud.py --once --file .\examples\sample_rollout.jsonl --lang en
```

默认根据 Windows UI 语言选择界面（`zh-*` → 简体中文，其余 → English）。也可以使用 `--lang auto`、`--lang zh-CN` 或 `--lang en` 覆盖。

## 构建

在 Windows PowerShell 中执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build.ps1
```

产物为 `dist\CodexRuntimeHUD.exe` 和 `dist\SHA256SUMS.txt`；GitHub Actions 会执行相同检查。

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

## 仓库目录

- `codex_runtime_hud.py`、`overlay_ui.py`、`icon_assets.py`：应用源码。
- `tests/`：解析器、图标和 UI 设置单元测试。
- `scripts/`：构建、启动和 GIF 采集脚本。
- `packaging/`：PyInstaller spec 和 Windows 版本元数据。
- `docs/releases/`：按版本归档的发布说明。
- `examples/`：测试与 CLI smoke test 使用的安全 sample rollout。

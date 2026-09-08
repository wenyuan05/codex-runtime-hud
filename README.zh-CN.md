# Codex Runtime HUD

[English README](README.md)

![演示](assets/codex-runtime-hud-demo.gif)

> **Unofficial / Not affiliated with OpenAI（非官方，与 OpenAI 无隶属关系）。**

这是一个专注于 Codex Desktop / Codex CLI **单轮实时表现**的 Windows 悬浮窗。它会跟随 root user rollout 的 JSONL 增量写入实时刷新，不调用任何 API。

下一版本：**v0.4.5**。标准 Codex 5h 与周额度改为跟随所有本地任务中最新的账户级快照，不再绑定当前选中的任务；`gpt-reserve` 等其他额度类型也不会再覆盖它们。

## 监控重点

默认视图是当前轮，而不是历史仪表盘。单轮运行期间，HUD 展示 LLM 耗时、TTFT、工具耗时、Steps、Token 速度、输入/输出 Token、缓存命中率和上下文使用率；“累计”视图仅作为 session 累计对照。

## 隐私

- 只读 `~/.codex/sessions` 与 `~/.codex/archived_sessions` 下的本地 Codex session 文件。
- **不会**读取 `auth.json`、API Key、`.env`、rollout 之外的提示词或凭据。
- 应用运行时不联网；GitHub、Python、PyInstaller 只用于分发和构建。
- 设置文件只保存窗口坐标和 UI 偏好：`%LOCALAPPDATA%\CodexRuntimeHUD\settings.json`。
  UI 偏好包括 `expanded`、`scope`、`language`（`auto`、`en`、`zh-CN`）、`always_on_top`、`toggle_hotkey` 和本地会话选择模式。会话列表固定在点击列表外时自动关闭。`Auto` 跟随 Windows UI 语言；手动选择中英文后会记住该选择，改回 `Auto` 才恢复自动检测。
- 现有 `%LOCALAPPDATA%\CodexTokenOverlay\settings.json` 会作为一次性兼容回退读取；之后的新设置写入 `CodexRuntimeHUD` 文件夹。

额度百分比属于账户级数据。HUD 会在所有符合条件的本地 root rollout 中分别合并最新的标准 `limit_id=codex` 5h 与周额度，因此手动选择其他任务也不会令额度停止刷新或被替换；其他额度类型会被有意忽略。

### 会话状态的局限

会话状态只能根据本地 rollout 中已经持久化的生命周期事件推断。“活跃”表示最新 root turn 已开始、尚未匹配 `task_complete`、`turn_complete` 或中止事件，并且近期仍有写入。新的 turn 会取代旧的未闭合 turn；同一稳定 thread 的重复 rollout 在列表中会被合并。Codex 在推理或等待工具时可能暂时不追加 JSONL，因此安静的未完成会话会显示为蓝色的 **运行中（等待更新）**。如果连续 24 小时没有新写入，则视为“空闲”，避免中断的历史 rollout 永远显示为进行中。HUD 也无法知道 Desktop 当前聚焦的是哪个标签页。

## 下载

从 [Releases](https://github.com/wenyuan05/codex-runtime-hud/releases) 下载最新的免安装 Windows x64 EXE。历史 v0.3.1 资产仍保留旧文件名；新构建使用 `CodexRuntimeHUD` 名称。EXE 未签名，首次运行可能出现 SmartScreen 提示。

可用 `SHA256SUMS.txt` 校验：

```powershell
Get-FileHash .\CodexRuntimeHUD.exe -Algorithm SHA256
```

双击 EXE 即可运行。折叠 HUD 顶部提供“会话”按钮、范围、Cache、In、Out；点击主体展开详细面板。展开视图还会显示 rollout 最近一次 `rate_limits` 快照中的 `5h` 与周额度剩余比例和重置倒计时；本地 rollout 未提供某个窗口时显示 `—`，应用不会为此联网查询。点击“会话”会显示可滚动的本地 root 会话列表。“自动跟随”保留稳定的最新 root 会话策略；手动选择某个会话后，HUD 会锁定它，直到重新选择自动跟随。列表只使用本地 `cwd` 项目目录名和短 thread ID，不读取提示词正文。会话列表固定在点击列表外时自动关闭。点击“本轮/累计”只切换范围，不会展开。拖动背景区域移动窗口；拖动右下角斜线手柄可调节窗口大小，紧凑和展开模式分别记忆尺寸。右键打开原生菜单，可隐藏窗口，或切换范围、会话、始终置顶、开机启动、全局显示/隐藏快捷键、语言、重置位置、复制和退出。托盘菜单也提供相同的快捷键设置，以及会话、显示/隐藏、开机启动、语言（自动/English/简体中文）、关于和退出。快捷键可选 `Ctrl+Alt+H`（默认）、`Ctrl+Shift+H`、`Alt+Shift+H` 或禁用；如果组合键已被其他程序占用，应用会保留原设置并提示。开机启动默认关闭，启用后只写入当前用户注册表；位置和 UI 偏好会跨重启保留。

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
- 点击“会话”：选择合格的本地 root thread，或切回自动跟随。
- 拖动主体：移动并保存悬浮窗位置。
- 点击“本轮/累计”：切换当前轮或当前 session 累计统计。
- 中键/Ctrl+C：复制当前信息；右键：打开原生设置菜单；Escape：隐藏到托盘。
- `Ctrl+Alt+H`：在任意应用中显示/隐藏悬浮窗；可在右键或托盘菜单的“显示/隐藏快捷键”中更换或禁用。
- `5h`/周额度按 `window_minutes` 识别，不依赖 `primary`/`secondary` 顺序；进度条和百分比都表示剩余额度。
- 缓存命中率 = `cached_input_tokens / input_tokens`。
- 本轮优先使用精确的 `raw_response_completed` usage，否则使用累计值差分；同一 rollout 内累计计数非零回退时会自动开启新的计数周期，跨重启继续统计。
- 工具耗时使用区间并集，并发工具不会重复计时。
- 工具事件统一兼容 response-item call/output、legacy begin/end，以及未来的 `item_started/item_completed` wrapper。
- 自动模式选择最新的合格 root user thread，并排除 subagent/memory consolidation；手动选择会锁定当前会话，切回自动模式后才恢复自动跟随；`--file` 可强制指定 rollout 并覆盖两种模式。
- 会话状态只是持久化事件推断，不是进程监控；蓝色的 **运行中（等待更新）** 表示“最新 turn 未结束但近期没有新写入”，不保证任务此刻仍在执行。超过 24 小时没有更新的未匹配 turn 会被视为空闲。
- 大型 rollout 会增量扫描 turn 元数据，不会因为最新 turn 位于文件中间而在启动时误选旧数据。
- Codex 尚未持久化有效的 `token_count` 或 response usage 时，Token 会显示为待定；全零占位快照不会误报为真实的 0 Token。

## 许可证

MIT，详见 [LICENSE](LICENSE)。

## 仓库目录

- `codex_runtime_hud.py`、`overlay_ui.py`、`icon_assets.py`：应用源码。
- `tests/`：解析器、图标和 UI 设置单元测试。
- `scripts/`：构建、启动和 GIF 采集脚本。
- `packaging/`：PyInstaller spec 和 Windows 版本元数据。
- `docs/releases/`：按版本归档的发布说明。
- `examples/`：测试与 CLI smoke test 使用的安全 sample rollout。

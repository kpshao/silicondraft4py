# 打包 spike：PyInstaller onedir + LGPL 合规

对应 issue [#16](https://github.com/kpshao/silicondraft4py/issues/16)（T15）。V1 以 PyInstaller `onedir` 为工作假设，最终打包方案（PyInstaller vs Nuitka）仍延后决定（见 [v1-spec.md](v1-spec.md) §5、§10）。本 spike 验证冻结应用能启动、生成并导出，并落实 PySide6-Essentials 与 Qt 的 LGPL 合规材料。

## 结论（macOS，2026-11-05 实测）

| 指标 | 结果 |
| --- | --- |
| 构建平台 | macOS 27.2，Apple Silicon（arm64） |
| 工具版本 | Python 3.13.15、PySide6-Essentials 6.12.0、PyInstaller 6.22.3 |
| 产物 | `dist/SiliconDraft.app`（onedir `.app`） |
| 包体积 | 107.9 MiB，346 个文件 |
| 构建耗时 | 13.0 s（`--clean`，含 PyInstaller 分析） |
| 启动时间 | 1.19 s（冷启动，进程创建到窗口显示并处理一次事件循环） |
| 冻结冒烟 | 通过：加载 `examples/tiny.yaml`，生成 1 lot / 2,700 die，导出 CP CSV + CP STDF |
| 包内依赖 | PySide6-Essentials、shiboken6、numpy、pydantic（含 pydantic-core、annotated-types、typing-inspection、typing-extensions）、PyYAML、pyqtgraph、colorama |

Windows 产物由 [`.github/workflows/package.yml`](../../.github/workflows/package.yml) 在 `windows-latest` 上跑同一脚本生成；本机为 macOS，未做 Windows 实机验证，验收项在 CI 跑通前保持未勾选。Windows 预期布局为 `dist/SiliconDraft/SiliconDraft.exe`。

## 使用

```bash
uv sync                 # 安装 GUI 依赖与 PyInstaller 构建依赖
make package            # 等价于 uv run python scripts/package.py
```

常用参数：

```bash
uv run python scripts/package.py --no-smoke          # 只构建并校验许可证
uv run python scripts/package.py --dist /tmp/dist    # 自定义输出目录
```

脚本可重复执行：每次以 `--noconfirm --clean` 重建，许可证目录按当前环境重写。PyInstaller 产物不保证字节级可复现（内嵌时间戳、Mach-O UUID、签名），"可重复执行"指同一环境可一键重建并通过同一校验。

CI（`.github/workflows/package.yml`）在 `macos-latest` 与 `windows-latest` 上执行同一命令，并上传 `dist/` 作为 artifact；也可用 `workflow_dispatch` 手动触发。

## 产物布局

macOS：

```text
dist/SiliconDraft.app/
  Contents/
    MacOS/SiliconDraft
    Frameworks/                  # Qt frameworks、Python 扩展、_internal 内容
    Resources/
      licenses/                  # 合规材料（见下）
      silicondraft/              # .qm / .mo 数据文件
```

Windows：

```text
dist/SiliconDraft/
  SiliconDraft.exe
  _internal/                     # PyInstaller 运行时与依赖
  licenses/
```

`dist/package-report.json` 记录平台、工具版本、包体积、构建/启动耗时、依赖许可清单与冒烟结果，便于跨平台对比。

## 冻结冒烟

GUI 入口保留一个隐藏参数 `--smoke-test`，仅由打包脚本调用：

```text
SiliconDraft --smoke-test --scenario <scenario.yaml> --output <dir>
```

冻结进程内依次执行：

1. 创建窗口并显示（冒烟固定使用 Qt 的 `offscreen` 平台插件，可在无桌面会话的 CI 中运行；启动时间在 `smoke-report.json` 中记录窗口显示时刻，由脚本换算）。
2. 安装 gettext `.mo` 与 GUI 的 Qt `.qm` 中文目录，验证两套翻译资源都随包分发；`verify_bundle()` 另行确认 Qt 自带的 `qtbase_zh_CN.qm`、两个项目 catalog 与 Qt 平台插件都在包内。
3. 通过 GUI 的 `GenerationWorker` 加载 scenario 并生成数据。
4. 等 worker 结束后调用 GUI 的导出路径写出 scenario 启用的格式。
5. 校验导出的 CSV/STDF 文件存在，写入 `smoke-report.json`，退出码 0。

脚本还检查导出文件同时包含 `.csv` 与 `.stdf`，因此生成和导出两条主路径都在冻结环境中真实执行。

## LGPL 合规

包内 `licenses/` 包含：

- `SiliconDraft/LICENSE`：项目 MIT 许可证。
- `LGPL-3.0.txt`、`GPL-3.0.txt`：GNU 官方原文（vendored 在 `buildtools/licenses/`，构建时离线复制）。LGPL-3.0 以 GPL-3.0 为基础，两份都要附。
- `QT_NOTICE.txt`：说明 Qt/PySide6 由 PySide6-Essentials 提供、按 LGPL-3.0-only 使用、动态链接、可替换 Qt 库，以及 Qt/PySide6 源码与商业许可链接。
- `THIRD_PARTY_NOTICES.txt`：每个随包发行版的版本、license 表达式和随发行版提供的 license 文件清单。
- 各依赖自带的 license 文件（如 `numpy/LICENSE.txt`、`pyqtgraph/LICENSE.txt`）。

依赖清单由 `distribution_closure(RUNTIME_ROOTS)` 从已安装元数据递归解析，避免手工维护；`PySide6-Addons` 未安装时构建才继续。`verify_bundle()` 会拒绝包内出现 `pyside6_addons`、测试依赖与 `setuptools` 等非运行时组件，并核对包内 `*.dist-info` 的发行版都属于该依赖闭包。

许可证文件由脚本在 PyInstaller 构建完成后写入 `Resources/licenses`，这会使 PyInstaller 之前的 ad-hoc 签名失效；脚本随后用 `codesign --force --sign -` 重新签名并执行 `codesign --verify --strict`。正式发布时 Developer ID 签名与 notarization 必须在所有文件写入之后执行。

构建约束：只安装 `pyside6-essentials`（`pyproject.toml` 的 GUI extra），spec 显式 `excludes` 掉 `pytest`、`hypothesis`、`pystdf`、`jsonschema`、`mypy`、`ruff`、`setuptools`、`pkg_resources`、`pydantic.mypy`。PyInstaller 的 PySide6 hook 自动收集 Qt 平台插件与 Qt 翻译目录。

## 已知问题与后续

- **Windows 未实机验证**：脚本与 CI 已就绪；需在 `windows-latest` 跑通后补记体积/启动时间并勾选验收项。
- **Intel macOS 未覆盖**：本机与 `macos-latest` 均为 arm64；规格支持 Apple Silicon + Intel，若需 Intel 产物应在 Intel runner 上构建或产出 universal2 包。
- **原生平台插件未实测**：冻结冒烟使用 `offscreen` 插件；macOS 的 cocoa 与 Windows 的 qwindows 插件虽在包内并通过存在性校验，但未在真实桌面会话中启动验证。
- **未签名/未公证**：macOS 包为 ad-hoc 签名，下载后受 Gatekeeper 隔离；正式发布需 Developer ID 签名与 notarization。Windows 未做代码签名，SmartScreen 会提示。
- **图标**：当前使用 PyInstaller 默认图标，正式发布需补 `.icns`/`.ico`。
- **体积**：Qt frameworks 占主要部分（QtGui/QtWidgets/QtCore 约 20 MiB，含重复符号链接前）；如需进一步裁剪可评估 Nuitka 或排除未用 Qt 模块，但本 spike 不做优化。
- **仅 GUI 包**：CLI 未单独冻结。CLI 在源码环境可无 GUI 运行；若后续需要单文件 CLI 分发，应另建 spec（可复用 `buildtools/bundle.py` 的许可证逻辑）。
- **测试钩子**：`--smoke-test` 是内部打包钩子，不属于用户界面契约。
- **Linux**：规格为 best-effort，本 spike 未覆盖。

# 引擎与 GUI 分离、依赖边界与 i18n

**Status:** accepted (2026-11-02)

CLI 与 GUI 必须共享同一生成引擎，产品支持英文默认、中文切换，并以 MIT 分发。我们决定：核心引擎纯 Python + NumPy、不依赖 Qt，公开 `load_scenario` / `validate` / `generate` / `export` API；CLI 与 GUI 仅作适配层；GUI 只依赖 PySide6-Essentials，图表用 pyqtgraph（MIT）与自绘 QGraphicsView，避开 QtCharts 等 GPLv3-only 模块；GUI 用 Qt `.ts/.qm`，CLI/引擎用 gettext，导出文件中的标识符与日志保持英文。这样 CLI 可无 Qt 运行、GUI 可替换，MIT 分发不受 GPL-only 模块影响。

<details>
<summary>English</summary>

# Separate the engine from the GUI, with explicit dependency boundaries and i18n

**Status:** accepted (2026-11-02)

The CLI and GUI must share one generation engine; the product is English-first with a Chinese switch, and is distributed under MIT. We will keep the core engine pure Python + NumPy with no Qt dependency, exposing `load_scenario` / `validate` / `generate` / `export` as a public API. CLI and GUI are adapters only. The GUI depends on PySide6-Essentials only, uses pyqtgraph (MIT) for charts and a custom QGraphicsView for wafer maps, and avoids GPLv3-only modules such as QtCharts. GUI strings use Qt `.ts/.qm`; CLI and engine messages use gettext; exported identifiers and logs stay in English. This keeps the CLI runnable without Qt, makes the GUI replaceable, and keeps MIT distribution free of GPL-only modules.

</details>

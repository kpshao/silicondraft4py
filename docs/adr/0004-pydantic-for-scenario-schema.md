# 用 Pydantic 模型作为 scenario schema 的单一来源

**Status:** accepted (2026-11-02)

Scenario v1 需要同时提供类型化模型、结构校验和 JSON Schema。我们决定用 Pydantic v2 模型定义 scenario 结构，运行时校验、默认值与 `silicondraft schema` 输出的 JSON Schema 都由同一份模型生成；跨字段规则（几何、item 引用、linkage、模板）放在独立的语义校验模块，保证错误码与字段路径稳定。这样避免手写 schema 与校验器之间的漂移，并让 CLI、GUI 与后续 `generate` 共享同一个 `load_scenario` seam。代价是核心运行时新增 `pydantic`（含 Rust 扩展 `pydantic-core`）依赖，超出 spec §6 列出的 NumPy + PyYAML；我们接受这一点，因为它不引入 Qt、保持引擎与 GUI 分离，并显著降低校验层维护成本。

<details>
<summary>English</summary>

# Use Pydantic models as the single source of truth for the scenario schema

**Status:** accepted (2026-11-02)

Scenario v1 needs a typed model, structural validation, and a JSON Schema. We will define the scenario structure with Pydantic v2 models so that runtime validation, defaults, and the JSON Schema printed by `silicondraft schema` all come from one source; cross-field rules (geometry, item references, linkage, templates) live in a separate semantic validation module so error codes and field paths stay stable. This avoids drift between a hand-written schema and a hand-written validator and gives the CLI, GUI, and the later `generate` pipeline one `load_scenario` seam. The cost is a new core runtime dependency, `pydantic` (including the Rust `pydantic-core` extension), beyond the NumPy + PyYAML listed in spec §6; we accept it because it adds no Qt dependency, keeps the engine and GUI separate, and materially reduces the maintenance cost of the validation layer.

</details>

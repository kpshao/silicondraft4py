# 预设作为 YAML 片段展开，CLI 逐 lot 生成并释放

**Status:** accepted (2026-11-03)

`quick` / `trend` / `demo` 预设需要在不破坏 “scenario YAML 是唯一入口” 的前提下复用；同时 T07 要求多 lot 生成的峰值内存不随 lot 数线性增长。我们让 scenario 顶层新增可选字段 `preset`，loader 在校验前把预设字典深合并到显式文档之下：标量与映射由显式字段覆盖，列表（例如 `patterns`）整体替换。预设提供默认 product 名 `GEN55LOGIC`，但从不设置 `seed`；`preset` 名称保留在模型与 `scenario_sha256` 中。`quick` 是 1 lot × 25 wafers 无模式，`trend` 是 5 lots × 25 wafers（168 小时 lot 间隔），`demo` 是 1 lot × 25 wafers 加 edge-low、center-high、ring、单 wafer local-spot 与强联动。

生成路径拆成两层。`generate(scenario)` 保持原公开契约，收集全部 lot 并返回完整 `GenerationResult`，供脚本与现有测试使用；新增 `generate_to_directory(scenario, out_dir, ...)` 逐 lot 生成，写完该 lot 的 CP CSV、WAT CSV 与每 die 真值后立即丢弃测量数组，并用 `ManifestBuilder` 累加 manifest 摘要、用流式矩（Chan 合并）累加 WAT↔CP 的 `observed_r`。CLI 的 `generate` 使用流式路径。`StreamingSummary` 返回 lot/wafer/die 计数、联动报告与模式贡献，供 CLI 打印。

**考虑的其他方案**

- 用 CLI `--preset` 选择预设：与 “scenario YAML 是唯一入口” 冲突，也会让 GUI 与 CLI 的复现路径分叉。
- 预设文件 + YAML include：需要额外的文件解析与路径语义，而三个内置预设足够小，直接作为字典维护更简单。
- 预设整体替换 scenario、不支持覆盖：用户无法在 `demo` 上改 wafer 数或产品名，预设会变成不可调参的孤岛。
- 让 `generate()` 返回惰性序列：会破坏“返回完整 `GenerationResult`”的公开契约与大量按索引访问的测试，收益仅是内存。
- 先生成全部 lot、再统一导出：实现简单，但峰值内存随 lot 数线性增长，直接违反 T07 验收。

**后果**

- 原始 YAML 在展开前不满足 JSON Schema 的 `product` 必填约束；`silicondraft validate`/`generate` 通过 loader 展开后校验。外部 JSON Schema 工具应校验展开后的文档，GUI 保存时应写展开后的 scenario（后续里程碑）。
- 列表是整体替换：在预设的 `patterns` 上追加需要写完整列表，不能只写新增项。
- 流式路径在导出中途失败时会留下已写出的部分文件；这与“导出非事务”一致，重新运行到新目录即可。`generate()` + `export()` 仍在全部生成成功后统一写出。
- 流式路径仍保留 manifest 所需的每 lot / 每 wafer 摘要（良率、latent 均值、缺陷坐标、模式贡献），这些是小对象，随 lot/wafer 数线性增长；被释放的是逐 die 测量数组，峰值内存因此由单 lot 数据主导。
- 流式 `observed_r` 由分块矩合并得到，与一次性 Pearson 计算可能有约 1e-12 量级的浮点差异；契约仍是样本估计值，不使用精确浮点比较。
- 日志与 manifest 的 `scenario_sha256` 包含预设名与展开后的字段；修改预设定义会改变 hash，这是期望的可复现性行为。

<details>
<summary>English</summary>

# Expand presets as YAML fragments and stream generation lot by lot

**Status:** accepted (2026-11-03)

The `quick` / `trend` / `demo` presets need reuse without breaking "scenario YAML is the single entry point", while T07 requires multi-lot peak memory not to grow linearly with the lot count. The scenario gains an optional top-level `preset` field; before validation, the loader deep-merges the preset dictionary under the explicit document: scalars and mappings are overridden by explicit fields, while lists (such as `patterns`) are replaced wholesale. Presets provide a default product name `GEN55LOGIC` but never set `seed`; the `preset` name stays in the model and in `scenario_sha256`. `quick` is 1 lot × 25 wafers with no patterns, `trend` is 5 lots × 25 wafers with a 168-hour lot interval, and `demo` is 1 lot × 25 wafers with edge-low, center-high, ring, a wafer-scoped local spot, and strong linkage.

Generation splits into two layers. `generate(scenario)` keeps its public contract: it collects every lot and returns the complete `GenerationResult` for scripts and existing tests. The new `generate_to_directory(scenario, out_dir, ...)` generates one lot at a time, writes that lot's CP CSV, WAT CSV, and per-die truth, then immediately drops its measurement arrays; it accumulates manifest summaries with `ManifestBuilder` and WAT↔CP `observed_r` with streaming moments (Chan merge). The CLI's `generate` uses the streaming path. `StreamingSummary` exposes lot/wafer/die counts, the linkage report, and pattern contributions for the CLI to print.

**Considered Options**

- A CLI `--preset` flag: conflicts with "scenario YAML is the single entry point" and forks the CLI and GUI reproduction paths.
- Preset files plus YAML includes: needs extra file resolution and path semantics, while the three built-in presets are small enough to maintain as dictionaries.
- Replacing the whole scenario with a preset and disallowing overrides: users could not change the wafer count or product name on top of `demo`, making presets unadjustable islands.
- Returning a lazy sequence from `generate()`: breaks the "returns a complete `GenerationResult`" public contract and many index-access tests, for a memory-only benefit.
- Generating every lot first and exporting afterwards: simple, but peak memory grows linearly with the lot count, directly violating the T07 acceptance criterion.

**Consequences**

- Before expansion, raw YAML does not satisfy the JSON Schema's required `product`; `silicondraft validate`/`generate` expand it in the loader before validating. External JSON Schema tooling should validate the expanded document, and the GUI should save the expanded scenario (later milestone).
- Lists replace wholesale: appending to a preset's `patterns` requires writing the full list, not just the new entry.
- A streaming failure mid-export can leave partial files behind, consistent with non-transactional export; rerunning into a new directory is safe. `generate()` + `export()` still write only after all generation succeeds.
- The streaming path still retains the per-lot/per-wafer summaries the manifest needs (yields, latent means, defect coordinates, pattern contributions); these are small objects that grow with the lot/wafer count. The released data is the per-die measurement arrays, so peak memory is dominated by one lot.
- Streaming `observed_r` comes from merged chunk moments and can differ from a one-shot Pearson calculation by roughly 1e-12; it remains a sample estimate, and tests do not require exact float equality.
- Logs and the manifest's `scenario_sha256` include the preset name and the expanded fields; changing a preset definition changes the hash, which is the intended reproducibility behaviour.

</details>

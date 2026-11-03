# CP CSV 默认使用每 lot 一个 long CSV，并保留多块格式

**Status:** accepted (2026-11-03)

CP CSV 原先只有每 wafer 一个文件的四块布局（ADR-0005），下游 pandas/YMS 导入必须按 `[SECTION]` 自行分块解析；WAT CSV 已经是每 lot 一个 flat long CSV，CP 缺少对应的通用长表。我们决定新增 CP long CSV，并把 `export.cp_csv_layout` 的默认值设为 `long`；`blocks` 保留现有四块格式，`both` 同时输出两套。long CSV 每个 lot 一个文件 `{product}_{lot}_CP_{timestamp}.csv`，一行 = wafer × die × item，表头固定为 `lot_id,wafer_id,die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,hard_bin_name,soft_bin,soft_bin_name,die_pass,test_num,item_id,value,unit,lsl,usl,pass,timestamp`。`pass` 是 item-level pass（与 WAT long CSV 相同，Bernoulli item 值非零才通过），`die_pass` 是 die-level pass（`hard_bin == 1`）；`hard_bin_name`/`soft_bin_name` 取自 `binning.py` 的静态定义。long CSV 不包含文件级元数据、`csv_format_version`、`product`、`test_program`、`typical` 或 `description`；其表头契约由本 ADR 定义为 CP long CSV v1。`schema_version` 保持 1，`export.cp_csv` 仍是总开关。此决定部分取代 ADR-0005 的「不保留无块纯表格式」条款。

**考虑的其他方案**

- 保留多块为默认、long 作为可选：向后兼容，但用户默认仍需解析块语法，无法直接用 pandas/YMS 导入。
- 用 long 完全替换多块：表最简洁，但丢失文件级元数据与 bin/spec 定义；多块格式对需要自描述文件的场景仍有价值。
- 把 long 做成后处理转换器：需要先写多块再解析，增加 I/O 与失败面，且无法在流式生成时逐 lot 写出。
- 在 long 表每行重复 `csv_format_version`/`scenario_sha256` 等元数据：1.4M 行时体积显著增加，且与 WAT long CSV 风格不一致。
- 只输出 bin 编号、不输出名称：主表更窄，但默认格式不再自描述 bin 语义。
- 把 long 文件按 wafer 拆分：降低单文件大小，但违背「一个 lot 一个文件」的通用导入约定。

**后果**

- 默认 `silicondraft generate` 从每 wafer 一个多块 CSV 变为每 lot 一个 long CSV；需要旧行为的 scenario 显式设置 `export.cp_csv_layout: blocks`。
- 现有依赖四块布局的测试、示例与文档需要迁移；这是有意的默认变更。
- long CSV 无法承载文件级元数据与 bin 定义；需要 provenance 时使用 ground truth manifest 或 `blocks`/`both`。
- 25 wafer × 21 item 的 lot 约 1.4M 行，超过 Excel 单表上限；long CSV 面向 pandas/YMS 等程序化消费者。
- `schema_version` 不变；`cp_csv` 与 `cp_csv_layout` 均为 schema 字段，JSON Schema 自动暴露。
- WAT long CSV 的既有列风格成为两种 phase 的共同参照；未来 WAT 若重新讨论多块布局，应以本 ADR 为参照。

<details>
<summary>English</summary>

# Make CP CSV default to one long CSV per lot while keeping the multi-block format

**Status:** accepted (2026-11-03)

The CP CSV previously only had the per-wafer four-block layout (ADR-0005), so pandas/YMS imports had to split it by `[SECTION]`; the WAT CSV is already one flat long CSV per lot, and CP lacked a comparable general-purpose long table. We add a CP long CSV and set `export.cp_csv_layout` to default to `long`; `blocks` keeps the existing four-block format, and `both` writes both. The long CSV has one file per lot, `{product}_{lot}_CP_{timestamp}.csv`, with one row per wafer × die × item and the fixed header `lot_id,wafer_id,die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,hard_bin_name,soft_bin,soft_bin_name,die_pass,test_num,item_id,value,unit,lsl,usl,pass,timestamp`. `pass` is the item-level pass (same as the WAT long CSV; Bernoulli items require a non-zero value), `die_pass` is the die-level pass (`hard_bin == 1`), and `hard_bin_name`/`soft_bin_name` come from the static definitions in `binning.py`. The long CSV carries no file-level metadata, `csv_format_version`, `product`, `test_program`, `typical`, or `description`; this ADR defines its header contract as CP long CSV v1. `schema_version` stays 1, and `export.cp_csv` remains the master switch. This decision partially supersedes ADR-0005's "no flat-table fallback" clause.

**Considered Options**

- Keep the multi-block format as the default and make long optional: backward compatible, but the default still requires block parsing and cannot be imported directly by pandas/YMS.
- Replace the multi-block format entirely with long: the simplest table, but it loses file-level metadata and bin/spec definitions; the multi-block format still has value where a self-describing file is required.
- Implement long as a post-processing converter: it would require writing blocks first and parsing them again, adding I/O and failure surface, and it cannot write lot by lot during streaming generation.
- Repeat metadata such as `csv_format_version`/`scenario_sha256` on every long row: adds substantial size at 1.4M rows and diverges from the WAT long CSV style.
- Emit only bin numbers without names: a narrower table, but the default format would no longer describe bin semantics.
- Split the long file per wafer: smaller files, but it violates the general-purpose one-file-per-lot import convention.

**Consequences**

- The default `silicondraft generate` output changes from one multi-block CSV per wafer to one long CSV per lot; scenarios that need the old behaviour must set `export.cp_csv_layout: blocks` explicitly.
- Existing tests, examples, and documentation that depend on the four-block layout must migrate; this is a deliberate default change.
- The long CSV cannot carry file-level metadata or bin definitions; use the ground truth manifest or `blocks`/`both` when provenance is required.
- A 25-wafer × 21-item lot is about 1.4M rows, above Excel's single-sheet limit; the long CSV targets programmatic consumers such as pandas/YMS.
- `schema_version` is unchanged; `cp_csv` and `cp_csv_layout` are both schema fields exposed by the JSON Schema automatically.
- The existing WAT long CSV column style becomes the shared reference for both phases; if WAT's multi-block layout is revisited later, this ADR is the reference point.

</details>

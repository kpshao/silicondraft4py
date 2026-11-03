# CP CSV 采用每 wafer 一个文件的多块布局

**Status:** accepted (2026-11-02)

CP CSV 目前是单一宽表，缺少文件级元数据、bin 定义与测试项规格，无法直接用于验证 YMS 的导入、bin 与 SPC 分析。我们决定把 CP CSV 改为每片 wafer 一个文件（`{product}_{lot}_{wafer}_CP_{timestamp}.csv`），文件内依次包含 `[METADATA]`、`[TEST_ITEMS]`、`[BIN_DEFINITIONS]`、`[TEST_DATA]` 四个块；每块以独占一行的 `[SECTION]` 标记开头，随后是表头行与数据行，块间不放空行。`[METADATA]` 用 `key,value` 两列，字段与 STDF 保持语义对齐（如 `lot_id` ↔ `MIR.LOT_ID`、`wafer_id` ↔ `WIR.WAFER_ID`、`test_program` ↔ `MIR.JOB_NAM`），并包含 `generated_at`；`[TEST_ITEMS]` 输出 `test_num,item_id,unit,typical,lsl,usl,description`；`[BIN_DEFINITIONS]` 输出 `bin_type,bin_number,bin_name,pass_fail,hard_bin,description`；`[TEST_DATA]` 保持一行一颗 die，列为 mm/grid 坐标、test site、hard bin、pass 与每个启用 item 一列。CSV 不再按 lot 合并，`export.split_by_wafer` 移除，不保留无块纯表格式。因元数据包含生成时间，同一 scenario + seed 的文件不再字节级一致，可复现性测试忽略时间戳。

**Considered Options**

- 每 lot 一个文件、按 wafer 重复元数据与数据块：文件数少，但块序列不再是固定四段，解析器要处理 lot 级与 wafer 级两种作用域。
- 每 lot 一个文件、lot 元数据 + wafer 表 + 数据块：能保持两个块，但元数据块需要嵌套表格 schema，且数据块仍要重复 `wafer_id` 列。
- 保留扁平表、把元数据作为每行重复列：无法自然表达文件级元数据、bin 定义与 spec。
- 保留 `split_by_wafer` 开关：CSV 已按 wafer 输出，开关只增加无意义组合。

**Consequences**

- 每个 lot 的 CSV 文件数从 1 增至 wafer 数；文件名必须包含 wafer ID。
- 读取方需按 `[SECTION]` 分块解析；`[TEST_DATA]` 块内仍是单表，可直接用 `csv.DictReader` 读取。
- STDF 布局不变；WAT CSV 未来可复用同一套块 grammar。
- `export.split_by_wafer` 从 scenario schema 移除，属于 schema 变更。

**后续更新（T04）：** soft bin 已实现，`[BIN_DEFINITIONS]` 按同一 schema 同时输出 HARD 与 SOFT 行（SOFT 行通过 `hard_bin` 列映射）；`[TEST_DATA]` 在 `hard_bin` 后增加 `soft_bin` 列；`[METADATA]` 增加 lot 级 `lot_die_count`/`lot_pass_count`/`lot_yield`，与每 wafer 的 `die_count`/`pass_count`/`yield` 并列；`csv_format_version` 从 `1` 升到 `2`。四块布局不变。

**后续更新（T05）：** WAT CSV 已实现为每个 lot 一个 flat long CSV（一行 = wafer × site × item），不复用本 ADR 的四块 grammar；issue #1 与 v1-spec 对 WAT long CSV 的列有单独要求。

**后续更新（T19）：** CP CSV 新增每 lot 一个 flat long CSV（`export.cp_csv_layout: long`）并成为默认；`blocks` 保留本 ADR 的四块布局，`both` 同时输出。因此本 ADR 的「不保留无块纯表格式」条款被 [ADR-0010](0010-cp-long-csv-default-and-multi-block-option.md) 部分取代。

<details>
<summary>English</summary>

# Use a per-wafer, multi-block layout for CP CSV

**Status:** accepted (2026-11-02)

The CP CSV is currently a single flat table with no file-level metadata, bin definitions, or test-item specifications, so it cannot directly validate a YMS's import, bin, and SPC analysis. We will switch CP CSV to one file per wafer (`{product}_{lot}_{wafer}_CP_{timestamp}.csv`) containing four blocks in order: `[METADATA]`, `[TEST_ITEMS]`, `[BIN_DEFINITIONS]`, and `[TEST_DATA]`. Each block starts with a standalone `[SECTION]` marker row, followed by a header row and data rows, with no blank lines between blocks. `[METADATA]` uses `key,value` rows whose keys stay semantically aligned with STDF (e.g. `lot_id` ↔ `MIR.LOT_ID`, `wafer_id` ↔ `WIR.WAFER_ID`, `test_program` ↔ `MIR.JOB_NAM`) and includes `generated_at`; `[TEST_ITEMS]` emits `test_num,item_id,unit,typical,lsl,usl,description`; `[BIN_DEFINITIONS]` emits `bin_type,bin_number,bin_name,pass_fail,hard_bin,description`; `[TEST_DATA]` keeps one row per die with mm/grid coordinates, test site, hard bin, pass, and one column per enabled item. CSV is no longer merged per lot, `export.split_by_wafer` is removed, and there is no flat-table fallback. Because metadata includes a generation timestamp, files from the same scenario + seed are no longer byte-identical; reproducibility tests ignore timestamps.

**Considered Options**

- One file per lot with metadata and data blocks repeated per wafer: fewer files, but the block sequence is no longer a fixed four-part grammar, and parsers must handle both lot-level and wafer-level scopes.
- One file per lot with lot metadata, a wafer table, and a data block: keeps two blocks, but the metadata block needs a nested tabular schema and the data block still repeats `wafer_id`.
- Keep the flat table and repeat metadata as columns on every row: cannot naturally express file-level metadata, bin definitions, or specs.
- Keep the `split_by_wafer` toggle: CSV is already per wafer, so the toggle only adds meaningless combinations.

**Consequences**

- The number of CSV files per lot grows from one to the wafer count, so file names must include the wafer ID.
- Readers must parse blocks by `[SECTION]`; within `[TEST_DATA]`, the content is still a single table and can be read with `csv.DictReader`.
- The STDF layout is unchanged; a future WAT CSV can reuse the same block grammar.
- Removing `export.split_by_wafer` from the scenario schema is a schema change.

**Update (T04):** soft bins are now implemented; `[BIN_DEFINITIONS]` emits both HARD and SOFT rows under the same schema (SOFT rows map to a hard bin through the `hard_bin` column); `[TEST_DATA]` gains a `soft_bin` column after `hard_bin`; `[METADATA]` gains lot-level `lot_die_count`/`lot_pass_count`/`lot_yield` alongside the per-wafer `die_count`/`pass_count`/`yield`; `csv_format_version` moves from `1` to `2`. The four-block layout is unchanged.

**Update (T05):** WAT CSV is now implemented as one flat long CSV per lot (one row per wafer × site × item) and does not reuse this ADR's four-block grammar; issue #1 and the v1-spec specify the WAT long-CSV columns separately.

**Update (T19):** CP CSV gains a flat long CSV per lot (`export.cp_csv_layout: long`) and becomes the default; `blocks` keeps this ADR's four-block layout, and `both` writes both. This ADR's "no flat-table fallback" clause is therefore partially superseded by [ADR-0010](0010-cp-long-csv-default-and-multi-block-option.md).

</details>

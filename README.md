[![CI](https://github.com/kpshao/silicondraft4py/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/kpshao/silicondraft4py/actions/workflows/ci.yml)

# SiliconDraft

SiliconDraft 是一个 scenario（场景）驱动的合成 CP/WAT 测试数据生成器，用于验证良率管理系统（YMS）的数据导入、良率/bin 分析、wafer map、SPC 与相关性分析。V1 覆盖 CP 与 WAT；FT 计划于 V2 支持。

当前处于 V1 开发早期：项目骨架、scenario v1 schema、结构/语义校验与 `validate` / `schema` / `version` CLI 已完成；CP 生成与 CP CSV 导出（`generate`）已接入，包含 21 个 CP 测试项、hard/soft bin、由 spec limits 推导的 pass/fail、lot/wafer/die 良率汇总与 hard/soft bin Pareto，CSV 采用 [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) 的每 wafer 一个文件、四块布局。latent 联动、系统性空间模式与随机缺陷（含 `CP_FUNC`/`CP_SCAN` 默认失败率）、WAT、STDF、ground truth 与 GUI 仍在后续里程碑。

## 安装

需要 Python 3.13。

```bash
uv sync
```

## 使用

### 快速开始

仓库提供 [examples/tiny.yaml](examples/tiny.yaml)：1 lot × 1 wafer，300 mm 晶圆、5×5 mm die，共 2,700 颗 die。

校验并生成 CP CSV：

```bash
uv run silicondraft validate -c examples/tiny.yaml
uv run silicondraft generate -c examples/tiny.yaml -o out/
```

查看输出（四个块 + 2,700 行 die，共 2,769 行）：

```bash
ls -lh out/
head -n 30 out/*.csv                # [METADATA] 与 [TEST_ITEMS]
grep -A13 '^\[BIN_DEFINITIONS\]' out/*.csv
wc -l out/*.csv
```

同一 scenario + seed 重复生成时数据一致，`generated_at` 与文件名时间戳除外。

> **Excel 用户**：默认 `export.encoding: utf-8` 不写 BOM，Excel 双击打开会把 `Ω`、`µA/µm`、`Å` 等单位符号按本地 ANSI 编码解析成乱码。请将 scenario 的 `export.encoding` 设为 `utf-8-sig`（[examples/tiny.yaml](examples/tiny.yaml) 已这样配置），或改用 Excel 的“数据 → 从文本/CSV”并手动选择 UTF-8。

生成 CP 数据并写入 CP CSV：

```bash
uv run silicondraft generate -c scenario.yaml -o out/
```

生成只接受通过校验的 scenario。每片 wafer 一个 CSV，文件内依次包含 `[METADATA]`、`[TEST_ITEMS]`、`[BIN_DEFINITIONS]` 与 `[TEST_DATA]` 四个块；`[TEST_DATA]` 每行一颗 die，包含 mm 与 grid 坐标、test site、hard bin、soft bin、pass 以及每个启用的 CP 测试项一列，不再重复 `lot_id`/`wafer_id`。`[BIN_DEFINITIONS]` 同时输出 hard bin 与 soft bin 定义，soft bin 通过 `hard_bin` 列映射到 hard bin。同一 scenario + seed 生成的数据一致（`generated_at` 与文件名时间戳除外）。

当前里程碑只导出 CP CSV：它使用 `export.encoding`，但暂不读取 `export` 中的 STDF/WAT/ground-truth 选项，也不会应用 `patterns` 或 `linkage`。这些配置随后续里程碑接入。

#### CP CSV 布局

[ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) 规定 CP CSV 每片 wafer 一个文件，文件内依次包含四个块：`[METADATA]`（`key,value` 元数据）、`[TEST_ITEMS]`（测试项与 spec 限值）、`[BIN_DEFINITIONS]`（hard/soft bin 定义）、`[TEST_DATA]`（每 die 测试结果）。文件名为 `{product}_{lot}_{wafer}_CP_{timestamp}.csv`；`[TEST_DATA]` 不重复 `lot_id`/`wafer_id`。`[METADATA]` 还包含 `csv_format_version`、`scenario_sha256`、lot 级 `lot_die_count`/`lot_pass_count`/`lot_yield`、每片 wafer 的 `die_count`/`pass_count`/`yield` 等字段；`test_program` 未在 `product.test_program` 配置时回退为 `items.preset`。`yield` 与 `lot_yield` 为 0–1 分数、保留 6 位小数；die 级结果由 `[TEST_DATA]` 的 `pass` 列给出。`[BIN_DEFINITIONS]` 先输出 HARD 行，再输出 SOFT 行，SOFT 行用 `hard_bin` 列给出到 hard bin 的映射。

```text
[METADATA]
key,value
csv_format_version,2
scenario_schema_version,1
phase,CP
lot_id,GEN55LOGIC-L001
...
wafer_id,W01
...
[TEST_ITEMS]
test_num,item_id,unit,typical,lsl,usl,description
...
[BIN_DEFINITIONS]
bin_type,bin_number,bin_name,pass_fail,hard_bin,description
...
[TEST_DATA]
die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,soft_bin,pass,CP_CONT,...
...
```

每个块以独占一行的 `[SECTION]` 标记开头，块间没有空行。编码遵循 `export.encoding`：默认 `utf-8`（无 BOM）；用 Excel 直接打开时设为 `utf-8-sig`，否则非 ASCII 单位符号会乱码。同一 scenario + seed 的数据仍一致，但 `generated_at` 与文件名时间戳会不同，比较时忽略这两项。

校验一个 scenario 文件。合法配置返回 0，并打印 die 数、item 数等摘要；非法配置返回 1，并给出可定位的字段路径与错误码：

```bash
uv run silicondraft validate -c scenario.yaml
```

输出 JSON Schema：

```bash
uv run silicondraft schema
```

查看版本：

```bash
uv run silicondraft version
```

最小 scenario（完整示例见 [examples/tiny.yaml](examples/tiny.yaml)）：

```yaml
schema_version: 1
product:
  name: GEN55LOGIC
seed: 20260105
```

完整分节与默认值见 [V1 规格](docs/design/v1-spec.md) 与 [领域词汇表](GLOSSARY.md)。

## Python API

```python
from silicondraft import export, generate, load_scenario, validate_scenario

result = validate_scenario("scenario.yaml")
if not result.ok:
    for issue in result.issues:
        print(issue.path, issue.code, issue.message)

scenario = load_scenario("scenario.yaml")  # 结构 + 语义校验通过后返回类型化场景
generated = generate(scenario)  # 返回 GenerationResult
paths = export(generated, out_dir="out")  # 写出 CP CSV，返回文件路径
```

## 开发

```bash
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest
```

CI 在 Ubuntu、macOS 与 Windows 上运行 lint、类型检查与测试。

## 文档

- [V1 规格](docs/design/v1-spec.md)
- [V1 测试项目录](docs/design/v1-test-item-catalog.md)
- [领域词汇表](GLOSSARY.md)
- [架构决策记录](docs/adr/)

## 许可证

MIT，见 [LICENSE](LICENSE)。

<details>
<summary>English</summary>

# SiliconDraft

SiliconDraft is a scenario-driven synthetic CP/WAT test data generator for validating yield management system (YMS) functions such as data import, yield/bin analysis, wafer maps, SPC, and correlation analysis. V1 covers CP and WAT; FT is planned for V2.

The project is in early V1 development: the project skeleton, scenario v1 schema, structural/semantic validation, and the `validate` / `schema` / `version` CLI are in place, along with CP generation and CP CSV export (`generate`). Generation now covers all 21 CP test items, hard/soft bins, pass/fail derived from spec limits, lot/wafer/die yield summaries, and hard/soft-bin Pareto; CP CSV uses the per-wafer, four-block layout set by [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md). Latent-factor linkage, systematic spatial patterns and random defects (including the default `CP_FUNC`/`CP_SCAN` failure rate), WAT, STDF, ground truth, and the GUI arrive in later milestones.

## Install

Python 3.13 is required.

```bash
uv sync
```

## Usage

### Quick start

The repo ships [examples/tiny.yaml](examples/tiny.yaml): 1 lot × 1 wafer, 300 mm wafer, 5×5 mm dies, 2,700 dies total.

Validate and generate CP CSV:

```bash
uv run silicondraft validate -c examples/tiny.yaml
uv run silicondraft generate -c examples/tiny.yaml -o out/
```

Inspect the output (four blocks plus 2,700 die rows, 2,769 lines total):

```bash
ls -lh out/
head -n 30 out/*.csv                # [METADATA] and [TEST_ITEMS]
grep -A13 '^\[BIN_DEFINITIONS\]' out/*.csv
wc -l out/*.csv
```

Repeated generation with the same scenario + seed produces identical data, except for `generated_at` and the timestamp in the file name.

> **Excel users**: the default `export.encoding: utf-8` writes no BOM, so opening the CSV by double-clicking makes Excel decode unit symbols such as `Ω`, `µA/µm`, and `Å` with the local ANSI codepage, producing mojibake. Set `export.encoding` to `utf-8-sig` in your scenario ([examples/tiny.yaml](examples/tiny.yaml) already does), or use Excel's Data → From Text/CSV and choose UTF-8 manually.

Generate CP data and write CP CSV:

```bash
uv run silicondraft generate -c scenario.yaml -o out/
```

Generation only accepts a scenario that passes validation. Each wafer gets its own CSV, containing `[METADATA]`, `[TEST_ITEMS]`, `[BIN_DEFINITIONS]`, and `[TEST_DATA]` in that order; `[TEST_DATA]` has one row per die with mm and grid coordinates, test site, hard bin, soft bin, pass, and one column per enabled CP test item, and no longer repeats `lot_id`/`wafer_id`. `[BIN_DEFINITIONS]` emits both hard- and soft-bin definitions, with soft bins mapping to hard bins through the `hard_bin` column. The same scenario + seed produces identical data (excluding `generated_at` and the timestamp in the file name).

This milestone exports CP CSV only: it honours `export.encoding` but does not yet read the STDF/WAT/ground-truth export options, and it does not apply `patterns` or `linkage`. Those configuration sections follow in later milestones.

#### CP CSV layout

[ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) specifies one CP CSV file per wafer, with four blocks in order: `[METADATA]` (`key,value` metadata), `[TEST_ITEMS]` (test items and spec limits), `[BIN_DEFINITIONS]` (hard/soft bin definitions), and `[TEST_DATA]` (per-die test results). The file name is `{product}_{lot}_{wafer}_CP_{timestamp}.csv`; `[TEST_DATA]` does not repeat `lot_id`/`wafer_id`. `[METADATA]` also carries `csv_format_version`, `scenario_sha256`, the lot-level `lot_die_count`/`lot_pass_count`/`lot_yield`, and the per-wafer `die_count`/`pass_count`/`yield`; `test_program` falls back to `items.preset` when `product.test_program` is not configured. `yield` and `lot_yield` are 0–1 fractions with six decimals; the die-level result is the `pass` column in `[TEST_DATA]`. `[BIN_DEFINITIONS]` emits HARD rows first, then SOFT rows, with the `hard_bin` column mapping each soft bin to its hard bin.

```text
[METADATA]
key,value
csv_format_version,2
scenario_schema_version,1
phase,CP
lot_id,GEN55LOGIC-L001
...
wafer_id,W01
...
[TEST_ITEMS]
test_num,item_id,unit,typical,lsl,usl,description
...
[BIN_DEFINITIONS]
bin_type,bin_number,bin_name,pass_fail,hard_bin,description
...
[TEST_DATA]
die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,soft_bin,pass,CP_CONT,...
...
```

Each block starts with a standalone `[SECTION]` marker, and there are no blank lines between blocks. Encoding follows `export.encoding`: the default `utf-8` writes no BOM; set it to `utf-8-sig` when opening the CSV directly in Excel, otherwise non-ASCII unit symbols appear garbled. The same scenario + seed still produces identical data, but `generated_at` and the file-name timestamp differ, so comparisons should ignore both.

Validate a scenario file. A valid configuration exits 0 and prints a summary (die count, item count, and more); an invalid one exits 1 with locatable field paths and error codes:

```bash
uv run silicondraft validate -c scenario.yaml
```

Print the JSON Schema:

```bash
uv run silicondraft schema
```

Print the version:

```bash
uv run silicondraft version
```

Minimal scenario (see [examples/tiny.yaml](examples/tiny.yaml) for the full example):

```yaml
schema_version: 1
product:
  name: GEN55LOGIC
seed: 20260105
```

See the [V1 specification](docs/design/v1-spec.md) and the [domain glossary](GLOSSARY.md) for all sections and defaults.

## Python API

```python
from silicondraft import export, generate, load_scenario, validate_scenario

result = validate_scenario("scenario.yaml")
if not result.ok:
    for issue in result.issues:
        print(issue.path, issue.code, issue.message)

scenario = load_scenario(
    "scenario.yaml"
)  # returns a typed scenario after structural + semantic validation
generated = generate(scenario)  # returns a GenerationResult
paths = export(generated, out_dir="out")  # writes CP CSV, returns file paths
```

## Development

```bash
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest
```

CI runs lint, type checks, and tests on Ubuntu, macOS, and Windows.

## Documentation

- [V1 specification](docs/design/v1-spec.md)
- [V1 test item catalog](docs/design/v1-test-item-catalog.md)
- [Domain glossary](GLOSSARY.md)
- [Architecture decision records](docs/adr/)

## License

MIT, see [LICENSE](LICENSE).

</details>

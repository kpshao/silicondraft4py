[![CI](https://github.com/kpshao/silicondraft4py/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/kpshao/silicondraft4py/actions/workflows/ci.yml)

# SiliconDraft

SiliconDraft 是一个 scenario（场景）驱动的合成 CP/WAT 测试数据生成器，用于验证良率管理系统（YMS）的数据导入、良率/bin 分析、wafer map、SPC 与相关性分析。V1 覆盖 CP 与 WAT；FT 计划于 V2 支持。

当前处于 V1 开发早期：项目骨架、scenario v1 schema、结构/语义校验与 `validate` / `schema` / `version` CLI 已完成；最小 CP 生成与 CP CSV 导出（`generate`）已接入。CP CSV 的目标布局（每 wafer 一个文件，含元数据、测试项、bin 定义与测试数据四个块）已由 [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) 确定，实现见 [#23](https://github.com/kpshao/silicondraft4py/issues/23)；当前 `generate` 仍输出旧的单一宽表。latent 联动、系统性空间模式与随机缺陷（含 `CP_FUNC`/`CP_SCAN` 默认失败率）、soft bin 与良率汇总、WAT、STDF、ground truth 与 GUI 仍在后续里程碑。

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

查看输出（1 行表头 + 2,700 行 die = 2,701 行）：

```bash
ls -lh out/
head -n 2 out/*.csv
wc -l out/*.csv
```

同一 scenario + seed 重复生成时 CSV 内容一致，仅文件名中的时间戳变化。

生成 CP 数据并写入 CP CSV：

```bash
uv run silicondraft generate -c scenario.yaml -o out/
```

生成只接受通过校验的 scenario。CSV 每个 lot 一个文件，每行一颗 die，包含 lot/wafer、mm 与 grid 坐标、test site、hard bin、pass 以及每个启用的 CP 测试项一列。同一 scenario + seed 生成的数据一致（文件名中的时间戳除外）。

当前里程碑只导出 CP CSV：它使用 `export.encoding`，但暂不读取 `export` 中的 STDF/WAT/ground-truth 选项，也不会应用 `patterns` 或 `linkage`。这些配置随后续里程碑接入。

#### CP CSV 目标布局（待实现）

[ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) 将 CP CSV 改为每片 wafer 一个文件，文件内依次包含四个块：`[METADATA]`（`key,value` 元数据）、`[TEST_ITEMS]`（测试项与 spec 限值）、`[BIN_DEFINITIONS]`（bin 定义）、`[TEST_DATA]`（每 die 测试结果）。文件名将是 `{product}_{lot}_{wafer}_CP_{timestamp}.csv`；`[TEST_DATA]` 不再重复 `lot_id`/`wafer_id`。

```text
[METADATA]
key,value
lot_id,GEN55LOGIC-L001
wafer_id,W01
...
[TEST_ITEMS]
test_num,item_id,unit,typical,lsl,usl,description
...
[BIN_DEFINITIONS]
bin_type,bin_number,bin_name,pass_fail,hard_bin,description
...
[TEST_DATA]
die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,pass,CP_CONT,...
...
```

实现见 [#23](https://github.com/kpshao/silicondraft4py/issues/23)；在此之前，`generate` 仍输出本节的单一宽表。目标格式下，同一 scenario + seed 的数据仍一致，但 `generated_at` 与文件名时间戳会不同，比较时忽略这两项。

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

The project is in early V1 development: the project skeleton, scenario v1 schema, structural/semantic validation, and the `validate` / `schema` / `version` CLI are in place, along with minimal CP generation and CP CSV export (`generate`). The target CP CSV layout (one file per wafer with metadata, test-item, bin-definition, and test-data blocks) is set by [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) and tracked in [#23](https://github.com/kpshao/silicondraft4py/issues/23); the current `generate` still writes the old single wide table. Latent-factor linkage, systematic spatial patterns and random defects (including the default `CP_FUNC`/`CP_SCAN` failure rate), soft bins and yield summaries, WAT, STDF, ground truth, and the GUI arrive in later milestones.

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

Inspect the output (1 header + 2,700 die rows = 2,701 lines):

```bash
ls -lh out/
head -n 2 out/*.csv
wc -l out/*.csv
```

Repeated generation with the same scenario + seed produces identical CSV content; only the timestamp in the file name changes.

Generate CP data and write CP CSV:

```bash
uv run silicondraft generate -c scenario.yaml -o out/
```

Generation only accepts a scenario that passes validation. Each lot gets one CSV file with one row per die, containing lot/wafer, mm and grid coordinates, test site, hard bin, pass, and one column per enabled CP test item. The same scenario + seed produces identical data (excluding the timestamp in the file name).

This milestone exports CP CSV only: it honours `export.encoding` but does not yet read the STDF/WAT/ground-truth export options, and it does not apply `patterns` or `linkage`. Those configuration sections follow in later milestones.

#### Target CP CSV layout (not implemented yet)

[ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) changes CP CSV to one file per wafer, with four blocks in order: `[METADATA]` (`key,value` metadata), `[TEST_ITEMS]` (test items and spec limits), `[BIN_DEFINITIONS]` (bin definitions), and `[TEST_DATA]` (per-die test results). The file name will be `{product}_{lot}_{wafer}_CP_{timestamp}.csv`; `[TEST_DATA]` will no longer repeat `lot_id`/`wafer_id`.

```text
[METADATA]
key,value
lot_id,GEN55LOGIC-L001
wafer_id,W01
...
[TEST_ITEMS]
test_num,item_id,unit,typical,lsl,usl,description
...
[BIN_DEFINITIONS]
bin_type,bin_number,bin_name,pass_fail,hard_bin,description
...
[TEST_DATA]
die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,pass,CP_CONT,...
...
```

Implementation is tracked in [#23](https://github.com/kpshao/silicondraft4py/issues/23); until then, `generate` still writes the single wide table described above. In the target layout, the same scenario + seed still produces identical data, but `generated_at` and the file-name timestamp differ, so comparisons should ignore both.

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

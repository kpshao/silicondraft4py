[![CI](https://github.com/kpshao/silicondraft4py/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/kpshao/silicondraft4py/actions/workflows/ci.yml)

# SiliconDraft

SiliconDraft 是一个 scenario（场景）驱动的合成 CP/WAT 测试数据生成器，用于验证良率管理系统（YMS）的数据导入、良率/bin 分析、wafer map、SPC 与相关性分析。V1 覆盖 CP 与 WAT；FT 计划于 V2 支持。

当前处于 V1 开发早期：项目骨架、scenario v1 schema、结构/语义校验与 `validate` / `schema` / `version` CLI 已完成；CP 生成与 CP CSV 导出（`generate`）已接入，包含 21 个 CP 测试项、hard/soft bin、由 spec limits 推导的 pass/fail、lot/wafer/die 良率汇总与 hard/soft bin Pareto；CP CSV 默认每 lot 一个 long CSV，并保留 [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) 的每 wafer 四块布局（见 [ADR-0010](docs/adr/0010-cp-long-csv-default-and-multi-block-option.md)）。WAT 生成与 WAT long CSV、六个 latent process factor 的 lot/wafer/die 分解、WAT↔CP 灵敏度联动、目标相关系数校准与生成报告也已接入（见 [ADR-0006](docs/adr/0006-wat-site-pairing-and-correlation-report.md)）。系统性空间模式、带簇聚的随机缺陷与 ground truth（JSON manifest + 每 die CSV.GZ）已接入（见 [ADR-0007](docs/adr/0007-patterns-defects-and-groundtruth.md)）。`quick` / `trend` / `demo` 预设、多 lot 时间线与 CLI 逐 lot 流式生成也已接入（见 [ADR-0008](docs/adr/0008-scenario-presets-and-streaming-generation.md)）。GUI 主干（scenario 配置树、YAML 加载/保存、预设选择、后台生成与取消、进度与错误展示）已接入；预览、数据表、导出、STDF 与完整中英文切换（`tr()` 接口已留好）留给后续里程碑。

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

查看输出（long CSV：2,700 颗 die × 21 个 CP 项 = 56,700 行数据 + 表头）：

```bash
ls -lh out/
head -n 5 out/*.csv
wc -l out/*.csv
```

若要查看 [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) 的四块布局，在 scenario 的 `export` 中设置 `cp_csv_layout: blocks` 后重新生成。

同一 scenario + seed 重复生成时数据一致，`generated_at` 与文件名时间戳除外。

#### 场景预设

scenario 可用顶层 `preset` 选择内置模板；显式字段覆盖模板（映射深合并，列表整体替换）：

```yaml
schema_version: 1
preset: demo
product:
  name: GEN55LOGIC
seed: 20260105
```

- `quick`：1 lot × 25 wafers，无注入模式，用于快速验证。
- `trend`：5 lots × 25 wafers，跨日期，lot 间隔 168 小时，用于 lot/wafer 趋势。
- `demo`：1 lot × 25 wafers，注入 edge-low、center-high、ring 与单 wafer local-spot，并带强联动，用于演示与 YMS 检测验证。

预设提供默认 product 名 `GEN55LOGIC`，可在 YAML 中覆盖；`seed` 始终由 scenario 指定。CLI 的 `generate` 逐 lot 生成并写出该 lot 的 CSV/真值后立即释放测量数组，峰值内存按单 lot 而非 lot 数增长。Python API 的 `generate()` 仍返回完整 `GenerationResult`；需要同样流式行为时使用 `generate_to_directory()`。

> **Excel 用户**：`unit` 列使用 ASCII SI 记法（`uA`、`ohm`、`angstrom` 等），默认 `export.encoding: utf-8` 双击打开也不会乱码。若产品名、描述等元数据包含中文等非 ASCII 内容，请将 scenario 的 `export.encoding` 设为 `utf-8-sig`（[examples/tiny.yaml](examples/tiny.yaml) 已这样配置），或改用 Excel 的“数据 → 从文本/CSV”并手动选择 UTF-8。

生成 CP 数据并写入 CP CSV：

```bash
uv run silicondraft generate -c scenario.yaml -o out/
```

生成只接受通过校验的 scenario。CP CSV 默认每个 lot 一个 long CSV（`{product}_{lot}_CP_{timestamp}.csv`），一行 = wafer × die × item，表头为 `lot_id,wafer_id,die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,hard_bin_name,soft_bin,soft_bin_name,die_pass,test_num,item_id,value,unit,lsl,usl,pass,timestamp`。`pass` 是该 item 的 item-level pass（Bernoulli 项值非零才通过），`die_pass` 是整颗 die 的 pass/fail（`hard_bin == 1`）；`hard_bin_name`/`soft_bin_name` 给出 bin 名称。设置 `export.cp_csv_layout: blocks` 可改用 [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) 的每 wafer 四块布局，`both` 同时写出两套。同一 scenario + seed 生成的数据一致（`generated_at` 与文件名时间戳除外）。

导出同时支持 CP CSV、WAT CSV 与 ground truth，分别由 `export.cp_csv` / `export.wat_csv` / `export.ground_truth` 控制；CP CSV 的布局由 `export.cp_csv_layout`（`long` / `blocks` / `both`，默认 `long`）控制；CSV 遵循 `export.encoding`。`patterns`、`defects` 与 `linkage` 均已接入生成流程；STDF 尚未接入。

#### CP CSV 布局

CP CSV 有两种布局，由 [ADR-0010](docs/adr/0010-cp-long-csv-default-and-multi-block-option.md) 与 [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) 规定。

**long（默认）**：每个 lot 一个文件 `{product}_{lot}_CP_{timestamp}.csv`，纯表格，一行 = wafer × die × item。表头固定为：

```text
lot_id,wafer_id,die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,hard_bin_name,soft_bin,soft_bin_name,die_pass,test_num,item_id,value,unit,lsl,usl,pass,timestamp
GEN55LOGIC-L001,W01,0.0,0.0,30,30,1,1,PASS,100,PASS,1,2001,CP_CONT,4.75,ohm,,100,1,2026-01-05T10:00:00+00:00
```

`timestamp` 是该 wafer 的 CP 测试时间（ISO 8601 UTC），每行重复；`lsl`/`usl` 无界时留空。long CSV 不含文件级元数据、`csv_format_version` 或完整 bin 定义；provenance 由 ground truth manifest 与文件名承载。25 wafer × 21 item 的 lot 约 1.4M 行，超过 Excel 单表上限，面向 pandas/YMS 等程序化消费者。

**blocks**：设置 `export.cp_csv_layout: blocks` 时恢复 [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) 的每 wafer 一个文件、四块布局。文件名为 `{product}_{lot}_{wafer}_CP_{timestamp}.csv`；文件内依次包含 `[METADATA]`（`key,value` 元数据）、`[TEST_ITEMS]`（测试项与 spec 限值）、`[BIN_DEFINITIONS]`（hard/soft bin 定义）、`[TEST_DATA]`（每 die 测试结果）。`[TEST_DATA]` 每行一颗 die，包含 mm 与 grid 坐标、test site、hard bin、soft bin、pass 以及每个启用的 CP 测试项一列，不重复 `lot_id`/`wafer_id`。`[METADATA]` 还包含 `csv_format_version`、`scenario_sha256`、lot 级 `lot_die_count`/`lot_pass_count`/`lot_yield`、每片 wafer 的 `die_count`/`pass_count`/`yield` 等字段；`test_program` 未在 `product.test_program` 配置时回退为 `items.preset`。`yield` 与 `lot_yield` 为 0–1 分数、保留 6 位小数；die 级结果由 `[TEST_DATA]` 的 `pass` 列给出。`[BIN_DEFINITIONS]` 先输出 HARD 行，再输出 SOFT 行，SOFT 行用 `hard_bin` 列给出到 hard bin 的映射。

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

每个块以独占一行的 `[SECTION]` 标记开头，块间没有空行。`unit` 列使用 ASCII SI 记法（如 `uA`、`ohm`、`angstrom`），默认 `utf-8`（无 BOM）也能在 Excel 中直接打开；若产品名等元数据包含中文等非 ASCII 内容，请将 `export.encoding` 设为 `utf-8-sig`。同一 scenario + seed 的数据仍一致，但 `generated_at` 与文件名时间戳会不同，比较时忽略这两项。

#### WAT 与 WAT↔CP 联动

WAT 只在 PCM 站点测量：每个 lot 输出一个 long CSV（`{product}_{lot}_WAT_{timestamp}.csv`），一行 = wafer × site × item，列为 `lot_id,wafer_id,wat_site,site_x_mm,site_y_mm,test_num,item_id,value,unit,lsl,usl,pass,timestamp`。站点坐标以 mm 表示；`timestamp` 是该 wafer 的 WAT 测试时间（ISO 8601 UTC），早于同一 wafer 的 CP 测试时间。`export.wat_csv` 控制是否写出（默认 `true`；[examples/tiny.yaml](examples/tiny.yaml) 为保持 CP 快速开始示例而关闭）。

生成时，六个 latent process factor（`F_VT`、`F_MOB`、`F_TOX`、`F_RC`、`F_LEAK`、`F_SC`）由 lot/wafer/die 三层标准化分量合成；相关 WAT 与 CP 项通过校准后的灵敏度矩阵加载同一因子。默认 28 对联动来自[测试项目录](docs/design/v1-test-item-catalog.md)，可在 scenario 中逐对覆盖或新增，支持负相关与一对多联动。自定义 WAT 项没有主 latent factor，不能参与联动；需要联动时请使用内置 WAT 项。WAT 站点与最近 die 的配对，以及目标/达成/观测 r 的定义见 [ADR-0006](docs/adr/0006-wat-site-pairing-and-correlation-report.md)。

```yaml
linkage:
  overrides:
    - wat: WAT_IDSATN
      cp: CP_IONN
      target_r: -0.50
    - wat: WAT_VTN
      cp: CP_VIL
      target_r: 0.35
```

`generate` 会为每对 WAT↔CP 打印 `target_r`、`achieved_r`（标定后模型隐含的总体相关）与 `observed_r`（本次生成数据按 site-nearest-die 配对得到的样本相关）：

```text
linkage: WAT_VTN -> CP_VTHN factor=F_VT target_r=0.800 achieved_r=0.800 observed_r=0.758
```

容差为 `target_r ≥ 0.5` 时绝对误差 ≤ 0.05，否则 ≤ 0.08；该容差针对 `achieved_r`。`observed_r` 是有限样本估计，规模越小波动越大：默认 1 lot × 25 wafers × 9 sites 只有 225 个配对，样本 r 无法稳定满足该容差；要验证生成数据本身，请使用足够大的场景（例如 10 lots × 25 wafers × 21 sites）。Python API 通过 `GenerationResult.wat_items`、`GenerationResult.wat_lots` 与 `GenerationResult.linkage_report` 暴露相同数据。

#### 空间模式、随机缺陷与 ground truth

`patterns` 支持 `center_high`、`center_low`、`edge_high`、`edge_low`、`ring`、`radial_gradient`、`local_spot`。每个模式可作用于 `yield` 和/或指定 CP item；`scope: lot` 作用于 lot 内所有 wafer，`scope: wafer` 在每个 lot 只作用于一张由 seed 确定的 wafer；多个模式按顺序叠加。模式只修改测量值，bin 始终由 spec limits 与 bin 规则推导。

```yaml
patterns:
  - kind: edge_low
    scope: lot
    target: yield
    amplitude: 0.35
    extent_mm: 25.0
  - kind: center_high
    target_item: CP_FRO
    amplitude: 0.05
    radius_mm: 40.0
  - kind: local_spot
    scope: wafer
    target: yield
    amplitude: -0.90
    radius_mm: 15.0
    center_mm: [40.0, -20.0]

defects:
  model: clustered        # 或 poisson
  failure_rate: 0.01      # CP_FUNC/CP_SCAN 期望总失败率
  cluster_size: 8         # 每个缺陷簇的期望失效 die 数
  cluster_radius_mm: 10.0
  target_items: [CP_FUNC, CP_SCAN]
```

yield 模式通过让 `CP_FUNC`（或 `CP_SCAN`）失败来降低良率；正幅度的 `center_high` / `edge_high` 通过降低随机缺陷失败概率体现。item 模式按相对 typical 的比例平移测量值；`ring`、`radial_gradient`、`local_spot` 的幅度可正可负。随机缺陷默认使用簇聚模型（高斯簇强度场 + 负二项缺陷计数），`failure_rate` 是所有 `target_items` 合计的 die 级期望失败率。

`export.ground_truth` 默认开启：每次生成运行输出一个 JSON manifest（`{product}_ground_truth_{timestamp}.json`），并为每个 lot 默认生成一个每 die 真值文件（`{product}_{lot}_die_truth_{timestamp}.csv.gz`）。manifest 包含完整 scenario 与 `scenario_sha256`、seed、每 lot/wafer 良率、latent factor 均值、模式清单与各自贡献、随机缺陷簇、联动目标/达成 r、outlier wafer 以及 die 真值文件名。die 真值包含 `true_pass`、true hard/soft bin、六个 latent factor 与 `pattern_ids`（以 `|` 分隔）。`--no-die-truth` 只关闭每 die 文件，manifest 仍写出；`export.ground_truth: false` 关闭整个 ground truth。

示例场景 [examples/patterns.yaml](examples/patterns.yaml) 同时注入 edge-low 良率模式、center-high item 模式、单 wafer local-spot 与默认随机缺陷：

```bash
uv run silicondraft generate -c examples/patterns.yaml -o out/
```

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

### 图形界面

GUI 依赖 PySide6-Essentials：

```bash
uv sync --extra gui
uv run silicondraft-gui
```

主窗口左侧显示当前 scenario 的配置树；工具栏可打开/保存 YAML、选择 `quick` / `trend` / `demo` 预设，并在后台 worker 线程生成数据。生成期间进度条与状态栏跟随当前 lot/wafer，Cancel 可停止生成并把窗口恢复到可操作状态；加载、保存或生成时的配置错误以 `path: message [code]` 列在右侧问题列表中。保存会写出完全展开后的 scenario，重新加载结果一致。预览、数据表、导出与完整中英文切换（`tr()` 接口已留好）不在本里程碑内。

## Python API

```python
from silicondraft import (
    export,
    generate,
    generate_to_directory,
    load_scenario,
    save_scenario,
    validate_scenario,
)

result = validate_scenario("scenario.yaml")
if not result.ok:
    for issue in result.issues:
        print(issue.path, issue.code, issue.message)

scenario = load_scenario("scenario.yaml")  # 结构 + 语义校验通过后返回类型化场景
generated = generate(scenario)  # 返回 GenerationResult
paths = export(generated, out_dir="out")  # 按 export 选项写出 CSV 与 ground truth
paths = export(generated, out_dir="out", include_die_truth=False)  # 覆盖每 die 真值开关

# 或逐 lot 生成并导出，峰值内存按单 lot 增长：
summary, paths = generate_to_directory(scenario, out_dir="out")

for entry in generated.linkage_report:
    print(entry.wat_item, entry.cp_item, entry.target_r, entry.achieved_r)
for report in generated.pattern_reports:
    print(report.pattern_id, report.realized_failures, report.item_shift_sum)
```

`generate()` 与 `generate_to_directory()` 接受可选的 `progress` 与 `should_cancel` 回调：`progress` 在每个 wafer 完成后收到 `GenerationProgress`，`should_cancel` 返回 `True` 时生成抛出 `GenerationCancelled`。`save_scenario(scenario, path)` 把 scenario 写成完全展开、可直接重新加载的 YAML。

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

The project is in early V1 development: the project skeleton, scenario v1 schema, structural/semantic validation, and the `validate` / `schema` / `version` CLI are in place, along with CP generation and CP CSV export (`generate`). Generation now covers all 21 CP test items, hard/soft bins, pass/fail derived from spec limits, lot/wafer/die yield summaries, and hard/soft-bin Pareto; CP CSV defaults to one long CSV per lot and retains the per-wafer four-block layout from [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md) (see [ADR-0010](docs/adr/0010-cp-long-csv-default-and-multi-block-option.md)). WAT generation with a long CSV, the lot/wafer/die decomposition of six latent process factors, WAT↔CP sensitivity linkage, target-correlation calibration, and the generation report are also in place (see [ADR-0006](docs/adr/0006-wat-site-pairing-and-correlation-report.md)). Systematic spatial patterns, clustered random defects, and ground truth (a JSON manifest plus per-die CSV.GZ) are in place too (see [ADR-0007](docs/adr/0007-patterns-defects-and-groundtruth.md)). The `quick` / `trend` / `demo` presets, multi-lot timelines, and the CLI's per-lot streaming generation are also in place (see [ADR-0008](docs/adr/0008-scenario-presets-and-streaming-generation.md)). The GUI backbone — scenario configuration tree, YAML load/save, preset selection, background generation with cancel, progress, and readable issues — is also in place; previews, the data table, export, STDF, and the full English/Chinese switch (the `tr()` seam is in place) arrive in later milestones.

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

Inspect the output (long CSV: 2,700 dies × 21 CP items = 56,700 data rows plus the header):

```bash
ls -lh out/
head -n 5 out/*.csv
wc -l out/*.csv
```

To inspect the four-block layout from [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md), set `cp_csv_layout: blocks` in the scenario's `export` section and regenerate.

Repeated generation with the same scenario + seed produces identical data, except for `generated_at` and the timestamp in the file name.

#### Scenario presets

A scenario can select a built-in template with the top-level `preset` field; explicit fields override the template (mappings merge deeply, lists replace wholesale):

```yaml
schema_version: 1
preset: demo
product:
  name: GEN55LOGIC
seed: 20260105
```

- `quick`: 1 lot × 25 wafers, no injected patterns, for fast validation.
- `trend`: 5 lots × 25 wafers across dates with a 168-hour lot interval, for lot/wafer trends.
- `demo`: 1 lot × 25 wafers with edge-low, center-high, ring, and a wafer-scoped local spot plus strong linkage, for demos and YMS detection validation.

Presets default the product name to `GEN55LOGIC`, which the YAML may override; `seed` always comes from the scenario. The CLI's `generate` writes each lot's CSV and truth files and then releases that lot's measurement arrays, so peak memory follows one lot rather than the lot count. The Python `generate()` API still returns the complete `GenerationResult`; use `generate_to_directory()` for the same streaming behaviour.

> **Excel users**: the `unit` column uses ASCII SI notation (e.g. `uA`, `ohm`, `angstrom`), so the default BOM-less `export.encoding: utf-8` opens correctly when double-clicked. If metadata such as the product name or descriptions contains non-ASCII text, set `export.encoding` to `utf-8-sig` in your scenario ([examples/tiny.yaml](examples/tiny.yaml) already does), or use Excel's Data → From Text/CSV and choose UTF-8 manually.

Generate CP data and write CP CSV:

```bash
uv run silicondraft generate -c scenario.yaml -o out/
```

Generation only accepts a scenario that passes validation. CP CSV defaults to one long CSV per lot (`{product}_{lot}_CP_{timestamp}.csv`), with one row per wafer × die × item and the header `lot_id,wafer_id,die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,hard_bin_name,soft_bin,soft_bin_name,die_pass,test_num,item_id,value,unit,lsl,usl,pass,timestamp`. `pass` is the item-level pass (Bernoulli items require a non-zero value), `die_pass` is the die-level pass (`hard_bin == 1`), and `hard_bin_name`/`soft_bin_name` give the bin names. Set `export.cp_csv_layout: blocks` for the per-wafer four-block layout from [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md), or `both` to write both. The same scenario + seed produces identical data (excluding `generated_at` and the timestamp in the file name).

Export covers CP CSV, WAT CSV, and ground truth, controlled by `export.cp_csv` / `export.wat_csv` / `export.ground_truth`; the CP CSV layout is controlled by `export.cp_csv_layout` (`long` / `blocks` / `both`, default `long`); CSV output honours `export.encoding`. `patterns`, `defects`, and `linkage` are all part of generation; STDF is not wired up yet.

#### CP CSV layout

CP CSV has two layouts, defined by [ADR-0010](docs/adr/0010-cp-long-csv-default-and-multi-block-option.md) and [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md).

**long (default)**: one file per lot, `{product}_{lot}_CP_{timestamp}.csv`, a pure table with one row per wafer × die × item. The header is fixed:

```text
lot_id,wafer_id,die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,hard_bin_name,soft_bin,soft_bin_name,die_pass,test_num,item_id,value,unit,lsl,usl,pass,timestamp
GEN55LOGIC-L001,W01,0.0,0.0,30,30,1,1,PASS,100,PASS,1,2001,CP_CONT,4.75,ohm,,100,1,2026-01-05T10:00:00+00:00
```

`timestamp` is the wafer's CP test time (ISO 8601 UTC), repeated on every row; `lsl`/`usl` are empty when unbounded. The long CSV carries no file-level metadata, `csv_format_version`, or full bin definitions; provenance comes from the ground truth manifest and the file name. A 25-wafer × 21-item lot is about 1.4M rows, above Excel's single-sheet limit, so the long CSV targets programmatic consumers such as pandas/YMS.

**blocks**: setting `export.cp_csv_layout: blocks` restores the per-wafer four-block layout from [ADR-0005](docs/adr/0005-cp-csv-multiblock-layout.md). The file name is `{product}_{lot}_{wafer}_CP_{timestamp}.csv`; each file contains `[METADATA]` (`key,value` metadata), `[TEST_ITEMS]` (test items and spec limits), `[BIN_DEFINITIONS]` (hard/soft bin definitions), and `[TEST_DATA]` (per-die test results). `[TEST_DATA]` has one row per die with mm and grid coordinates, test site, hard bin, soft bin, pass, and one column per enabled CP test item, and does not repeat `lot_id`/`wafer_id`. `[METADATA]` also carries `csv_format_version`, `scenario_sha256`, the lot-level `lot_die_count`/`lot_pass_count`/`lot_yield`, and the per-wafer `die_count`/`pass_count`/`yield`; `test_program` falls back to `items.preset` when `product.test_program` is not configured. `yield` and `lot_yield` are 0–1 fractions with six decimals; the die-level result is the `pass` column in `[TEST_DATA]`. `[BIN_DEFINITIONS]` emits HARD rows first, then SOFT rows, with the `hard_bin` column mapping each soft bin to its hard bin.

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

Each block starts with a standalone `[SECTION]` marker, and there are no blank lines between blocks. The `unit` column uses ASCII SI notation (e.g. `uA`, `ohm`, `angstrom`), so the default BOM-less `utf-8` opens directly in Excel; if metadata such as the product name contains non-ASCII text, set `export.encoding` to `utf-8-sig`. The same scenario + seed still produces identical data, but `generated_at` and the file-name timestamp differ, so comparisons should ignore both.

#### WAT and WAT↔CP linkage

WAT is measured at PCM sites only: each lot produces one long CSV (`{product}_{lot}_WAT_{timestamp}.csv`) with one row per wafer × site × item and columns `lot_id,wafer_id,wat_site,site_x_mm,site_y_mm,test_num,item_id,value,unit,lsl,usl,pass,timestamp`. Site coordinates are in millimetres; `timestamp` is that wafer's WAT test time (ISO 8601 UTC) and precedes the CP test time for the same wafer. `export.wat_csv` controls whether the file is written (default `true`; [examples/tiny.yaml](examples/tiny.yaml) disables it to keep the CP quick start small).

Six latent process factors (`F_VT`, `F_MOB`, `F_TOX`, `F_RC`, `F_LEAK`, `F_SC`) combine standardized lot, wafer, and die components; related WAT and CP items load on the same factor through the calibrated sensitivity matrix. The 28 default pairs come from the [test item catalog](docs/design/v1-test-item-catalog.md) and can be overridden or extended per pair in the scenario; negative correlations and one-to-many links are supported. Custom WAT items have no primary latent factor and cannot participate in linkage; use the built-in WAT items for linkage. See [ADR-0006](docs/adr/0006-wat-site-pairing-and-correlation-report.md) for the WAT-site/nearest-die pairing and the target/achieved/observed correlation definitions.

```yaml
linkage:
  overrides:
    - wat: WAT_IDSATN
      cp: CP_IONN
      target_r: -0.50
    - wat: WAT_VTN
      cp: CP_VIL
      target_r: 0.35
```

`generate` prints `target_r`, `achieved_r` (the population correlation implied by the calibrated model), and `observed_r` (the sample correlation over the generated data, paired by nearest die) for every WAT↔CP pair:

```text
linkage: WAT_VTN -> CP_VTHN factor=F_VT target_r=0.800 achieved_r=0.800 observed_r=0.758
```

The tolerance is an absolute error ≤ 0.05 when `target_r >= 0.5`, otherwise ≤ 0.08; it applies to `achieved_r`. `observed_r` is a finite-sample estimate and varies more in smaller runs: the schema default of 1 lot × 25 wafers × 9 sites provides only 225 pairs, where the sample r cannot reliably meet that tolerance. To verify the generated data itself, use a large enough scenario (for example 10 lots × 25 wafers × 21 sites). The Python API exposes the same data through `GenerationResult.wat_items`, `GenerationResult.wat_lots`, and `GenerationResult.linkage_report`.

#### Spatial patterns, random defects, and ground truth

`patterns` supports `center_high`, `center_low`, `edge_high`, `edge_low`, `ring`, `radial_gradient`, and `local_spot`. Each pattern targets `yield` and/or a selected CP item; `scope: lot` applies to every wafer in the lot, while `scope: wafer` applies to one seed-selected wafer per lot; multiple patterns compose in order. Patterns only modify measurement values, so bins are always derived from spec limits and bin rules.

```yaml
patterns:
  - kind: edge_low
    scope: lot
    target: yield
    amplitude: 0.35
    extent_mm: 25.0
  - kind: center_high
    target_item: CP_FRO
    amplitude: 0.05
    radius_mm: 40.0
  - kind: local_spot
    scope: wafer
    target: yield
    amplitude: -0.90
    radius_mm: 15.0
    center_mm: [40.0, -20.0]

defects:
  model: clustered        # or poisson
  failure_rate: 0.01      # expected combined CP_FUNC/CP_SCAN failure rate
  cluster_size: 8         # expected failing dies per defect cluster
  cluster_radius_mm: 10.0
  target_items: [CP_FUNC, CP_SCAN]
```

A yield pattern creates failures by failing `CP_FUNC` (or `CP_SCAN`); positive-amplitude `center_high` / `edge_high` instead reduce the random-defect failure probability. An item pattern shifts that item's measurements by a fraction of its typical value; `ring`, `radial_gradient`, and `local_spot` amplitudes carry their own sign. Random defects use a clustered model by default (a Gaussian cluster-intensity field with negative-binomial defect counts), and `failure_rate` is the expected die-level failure rate across all `target_items`.

`export.ground_truth` is enabled by default: each generation run produces one JSON manifest (`{product}_ground_truth_{timestamp}.json`) plus, by default, one per-die truth file per lot (`{product}_{lot}_die_truth_{timestamp}.csv.gz`). The manifest carries the full scenario and `scenario_sha256`, seed, per-lot/per-wafer yields, latent-factor means, the pattern manifest with each pattern's contribution, random-defect clusters, target/achieved linkage correlations, outlier wafers, and the die-truth file names. Per-die truth contains `true_pass`, true hard/soft bins, the six latent factors, and `pattern_ids` separated by `|`. `--no-die-truth` suppresses only the per-die file (the manifest is still written); `export.ground_truth: false` disables ground truth entirely.

[examples/patterns.yaml](examples/patterns.yaml) combines an edge-low yield pattern, a center-high item pattern, a wafer-scoped local spot, and the default random defects:

```bash
uv run silicondraft generate -c examples/patterns.yaml -o out/
```

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

### GUI

The GUI depends on PySide6-Essentials:

```bash
uv sync --extra gui
uv run silicondraft-gui
```

The main window shows the current scenario's configuration tree on the left. The toolbar opens and saves YAML, selects the `quick` / `trend` / `demo` presets, and generates in a background worker thread. During generation the progress bar and status bar follow the current lot/wafer; Cancel stops the run and restores the window to a usable state. Configuration errors from loading, saving, or generation appear in the right-hand issues list as `path: message [code]`. Saving writes the fully expanded scenario, so reloading yields the same scenario. Previews, the data table, export, and the full English/Chinese switch (the `tr()` seam is in place) are outside this milestone.

## Python API

```python
from silicondraft import (
    export,
    generate,
    generate_to_directory,
    load_scenario,
    save_scenario,
    validate_scenario,
)

result = validate_scenario("scenario.yaml")
if not result.ok:
    for issue in result.issues:
        print(issue.path, issue.code, issue.message)

scenario = load_scenario(
    "scenario.yaml"
)  # returns a typed scenario after structural + semantic validation
generated = generate(scenario)  # returns a GenerationResult
paths = export(generated, out_dir="out")  # writes CSV and ground truth per export options
paths = export(generated, out_dir="out", include_die_truth=False)  # override per-die truth

# Or generate and export one lot at a time; peak memory follows a single lot:
summary, paths = generate_to_directory(scenario, out_dir="out")

for entry in generated.linkage_report:
    print(entry.wat_item, entry.cp_item, entry.target_r, entry.achieved_r)
for report in generated.pattern_reports:
    print(report.pattern_id, report.realized_failures, report.item_shift_sum)
```

`generate()` and `generate_to_directory()` accept optional `progress` and `should_cancel` callbacks: `progress` receives a `GenerationProgress` after each wafer, and generation raises `GenerationCancelled` when `should_cancel` returns `True`. `save_scenario(scenario, path)` writes a fully expanded scenario that reloads to the same value.

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

# SiliconDraft V1 规格（草案）

> 状态：已发布为 [GitHub issue #1](https://github.com/kpshao/silicondraft4py/issues/1)（2026-11-02）。本文件作为设计附录保留；issue 是规范的唯一来源。
> 关联：[GLOSSARY.md](../../GLOSSARY.md) · [V1 测试项目录](v1-test-item-catalog.md) · [ADR-0001](../adr/0001-latent-factor-generation-model.md) · [ADR-0002](../adr/0002-own-stdf-v4-writer.md) · [ADR-0003](../adr/0003-engine-gui-separation-and-i18n.md)

## 1. 背景与目标

SiliconDraft 生成可复现的合成半导体测试数据，用于验证良率管理系统（YMS）的数据导入、良率/bin 分析、wafer map 与空间模式、SPC/Cpk、以及 WAT↔CP 相关性分析。V1 只生成 CP 与 WAT；FT 计划于 V2 支持。生成器同时输出 ground truth manifest，供外部验证 harness 对 YMS 的检测结果打分。

## 2. 范围

### 2.1 In scope

- Scenario YAML（版本化 schema、JSON Schema 校验、`quick` / `trend` / `demo` 预设）。
- Wafer 几何：150/200/300mm，die grid，edge exclusion，notch 朝向，CP 多站点并测。
- WAT 在 PCM/TEG 站点测量（默认 9 点）；CP 对每颗 die 测量。
- 内置通用 55nm CMOS 逻辑测试项目录：15 个 WAT 项 + 21 个 CP 项，可覆盖。
- Latent factor 联动引擎 + 目标相关系数校准。
- 系统性空间模式与随机缺陷，两者分开建模并可叠加。
- Hard bin / soft bin。
- Ground truth：JSON 摘要 + 每 die CSV.GZ。
- 导出：CP 每个 lot 一个 STDF V4 + 每 wafer 一个 wide CSV；WAT 每个 lot 一个 long CSV。
- CLI 与 GUI；英文默认、中文可切换；GUI 支持 ground truth 叠加。

### 2.2 Out of scope（V1）

- FT 数据、FT 测试项、CP→FT 单颗追溯（V2）。
- 导入真实测试数据；YMS 的分析/评分逻辑；数据库、服务端、网络上传、多用户。
- Reticle field 级空间模式、die 旋转、flat 朝向建模。
- macOS 14 以下；Linux 仅 best-effort。
- 最终打包方案（PyInstaller vs Nuitka）暂缓决定；V1 以 PyInstaller `onedir` 为工作假设。

## 3. 领域模型

术语以 [GLOSSARY.md](../../GLOSSARY.md) 为准。核心关系：

- `Product` → `Lot` → `Wafer` → `Die`（CP 测量到 die）。
- `Wafer` → `WAT site`（PCM/TEG 站点，每片少量）。
- `Die` → `Test site`（多站点并测中的探针卡站点）。
- `Scenario` → latent process factors → WAT/CP test items → hard/soft bins。
- `Ground truth manifest` 记录注入的模式、latent factor、目标/实际相关系数与每 die 真相。

## 4. 功能需求

### 4.1 Scenario

#### 4.1.1 文件格式与版本

- 作者格式为 YAML；`schema_version` 为必填整数，V1 为 `1`。
- 提供 JSON Schema；`silicondraft validate` 与 GUI 加载时执行结构校验 + 语义校验（die grid 能放入 wafer、item 引用存在、bin 码唯一、linkage 引用存在等）。
- GUI 保存时写入完全展开后的 scenario，而非仅保存 diff，保证可复现。

#### 4.1.2 分节

`schema_version`、`product`、`wafer`、`lots`、`items`、`patterns`、`linkage`、`export`、`seed`、`metadata`。

`product.test_program` 为可选字段，表示测试程序名；未填写时回退为 `items.preset`。

#### 4.1.3 预设

- `quick`：1 lot × 25 wafers，无注入模式，用于快速验证。
- `trend`：5 lots × 25 wafers，跨日期，用于 lot/wafer 趋势。
- `demo`：1 lot × 25 wafers，注入多种空间模式与强联动，用于演示与 YMS 检测验证。

#### 4.1.4 示例

```yaml
schema_version: 1

product:
  name: GEN55LOGIC
  device_family: cmos_logic
  process_node: "55nm"
  fab: FAB-A
  test_program: GEN55LOGIC_CP

wafer:
  diameter_mm: 300
  die_size_mm: [5.0, 5.0]
  edge_exclusion_mm: 3.0
  notch: down
  cp_sites: 4
  wat_sites: 9

lots:
  count: 1
  wafers_per_lot: 25
  lot_id_template: "{product}-L{lot:03d}"
  wafer_id_template: "W{wafer:02d}"
  start_date: "2026-01-05T08:00:00"
  wat_to_cp_gap_min: 120
  cp_duration_min_per_wafer: 45
  lot_interval_hours: 168

items:
  preset: generic_cmos_logic_55nm
  overrides: []

patterns:
  - kind: edge_low
    scope: lot
    target: yield
    amplitude: 0.08
    extent_mm: 25.0
  - kind: center_high
    scope: wafer
    target_item: CP_FRO
    amplitude: 0.05
    radius_mm: 40.0

linkage:
  overrides:
    - wat: WAT_VTN
      cp: CP_VTHN
      target_r: 0.80

export:
  cp_stdf: true
  cp_csv: true
  wat_csv: true
  ground_truth: true
  include_die_truth: true
  encoding: utf-8

seed: 20260105

metadata:
  author: ""
  note: "quick preset"
```

### 4.2 Wafer 布局

- 直径支持 150/200/300mm，默认 300mm。
- die 尺寸可配置，默认 5.0×5.0mm。
- edge exclusion 默认 3.0mm；只保留 die 中心落在可用半径内的完整 die，不生成 partial die。
- notch 朝下；坐标原点在 wafer 中心，+X 向右、+Y 向上。
- 内部几何用 mm；STDF PRR 使用整数 grid index；CSV 同时输出 mm 与 grid。
- CP 多站点：默认 4 site，按测试顺序分配；可选 site offset；STDF PTR/PRR 填 `SITE_NUM`。
- WAT 站点：默认 9 点 = 中心 + 0.5R 四个正交方向 + 0.9R 四个对角方向；站点数可配置为 5/9/13/21。
- WAT 在 lot 内按 wafer 生成，时间上早于 CP。

### 4.3 测试项目录

- 内置 `generic_cmos_logic_55nm` 预设：15 个 WAT 项 + 21 个 CP 项，定义见 [V1 测试项目录](v1-test-item-catalog.md)。
- 每项包含：`test_num`、规范英文 ID、单位、典型值、LSL/USL、分布、业务含义、测试条件。
- `items.overrides` 支持增删项、修改单位/限值/分布/联动参数；GUI V1 只做启用/停用与限值编辑，完整项编辑器留 V2。
- 导出文件只使用规范英文 ID；中文名称仅用于界面显示。

### 4.4 生成流程

#### 4.4.1 流水线

`scenario 校验 → wafer 布局 → latent factors（lot/wafer/die 三层）→ WAT 站点值 → CP item 值 → 系统性空间模式注入 → 随机缺陷 → binning → ground truth → 预览/导出`。

#### 4.4.2 Latent factor 与校准

- 六个共享因子：`F_VT`、`F_MOB`、`F_TOX`、`F_RC`、`F_LEAK`、`F_SC`。
- 每个因子分解为 lot 级、wafer 级、die 级分量 + 独立测量噪声；WAT 与 CP 通过灵敏度矩阵加载同一因子。
- 目标相关系数来自默认联动表或 scenario 覆盖；引擎校准载荷，使实际相关系数落在容差内：目标 r ≥ 0.5 时绝对误差 ≤ 0.05，否则 ≤ 0.08。
- 生成报告输出每对 WAT↔CP 的目标/实际 r。

#### 4.4.3 系统性空间模式

V1 模式目录：`center-high`、`center-low`、`edge-high`、`edge-low`、`ring`、`radial-gradient`、`local-spot`。

- 每个模式可指定：作用对象（yield / 指定 item / 两者）、幅度、空间范围（半径或宽度）、作用粒度（lot 或 wafer）、叠加方式。
- 多个模式可叠加；同一 wafer 上允许同时存在不同模式。
- 模式作用于 die 级值或 die pass/fail；不得直接改写 bin 码，bin 由规则推导。

#### 4.4.4 随机缺陷

- 默认用负二项/簇聚模型：缺陷密度 + 簇聚参数；可配置为 Poisson。
- 缺陷导致 `CP_FUNC` / `CP_SCAN` 失败或指定 item 失效；默认 `CP_FUNC`/`CP_SCAN` 总失败率 1%。
- 缺陷结果进入 ground truth，供 YMS 的簇聚/异常检测验证。

#### 4.4.5 Binning

- Hard bin 默认：1=pass、2=parametric fail、3=functional/structural fail、4=continuity/contact fail。
- Soft bin 默认：100=pass、201=continuity、202=leakage、203=Iddq、204=Vth、205=frequency、206=functional/scan、207=other parametric。
- pass/fail 由 spec limits 与 bin 规则推导；bin 表可在 scenario 覆盖。
- STDF 输出 HBR/SBR；CSV 的 `[BIN_DEFINITIONS]` 块输出 bin 定义，`[TEST_DATA]` 同时包含 hard/soft bin 列。

#### 4.4.6 可复现性

- `seed` 必填；随机数按 lot/wafer/item 派生，保证同一 scenario + seed 产生相同数据（时间戳除外）。
- Ground truth 记录 `scenario_sha256`、引擎版本与 seed。

### 4.5 Ground truth

- JSON 摘要：引擎版本、完整 scenario + SHA-256、seed、生成时间、product、lot/wafer 摘要、每 wafer 良率、latent factor 均值、注入模式清单、目标 vs 实际相关系数、outlier wafer、每 die 真值文件名。
- 每 die CSV.GZ：`lot_id, wafer_id, die_x_mm, die_y_mm, grid_x, grid_y, test_site, true_pass, true_hard_bin, true_soft_bin, F_VT, F_MOB, F_TOX, F_RC, F_LEAK, F_SC, pattern_ids`。
- `--no-die-truth` 可关闭每 die 真值输出。

### 4.6 导出

- **CP STDF V4**：MIR、MRR、PCR、HBR、SBR、WIR、WRR、WCR、PIR、PRR、PTR、TSR 全套。
- **CP CSV**：每片 wafer 一个 wide CSV，采用四块布局（见 [ADR-0005](../adr/0005-cp-csv-multiblock-layout.md)）：
  - `[METADATA]`：`key,value` 两列，记录 `csv_format_version`、`scenario_schema_version`、`phase`、`lot_id`、`product`、`device_family`、`process_node`、`fab`、`test_program`、`tester_type`、`exec_type`、`exec_version`、`generated_at`、`seed`、`scenario_sha256`、`wafer_id`、`diameter_mm`、`die_size_x_mm`、`die_size_y_mm`、`edge_exclusion_mm`、`notch`、`cp_sites`、`die_count`、`pass_count`、`yield`；键名与 STDF 字段的语义映射见 ADR-0005。
  - `[TEST_ITEMS]`：`test_num,item_id,unit,typical,lsl,usl,description`，一行一个启用的 CP item，按 catalog 顺序。
  - `[BIN_DEFINITIONS]`：`bin_type,bin_number,bin_name,pass_fail,hard_bin,description`，定义 hard bin 与未来的 soft bin 及其映射；`pass_fail` 用 `P`/`F`。
  - `[TEST_DATA]`：一行一颗 die，列为 `die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,pass` 加每个启用 item 一列。
  - 每个块以独占一行的 `[SECTION]` 标记开头，随后是表头行与数据行；块间不放空行。
- **WAT CSV**：每个 lot 一个 long CSV，一行 = wafer × site × item；列包含 site 的 mm 坐标、test_num、item_id、value、unit、LSL/USL、pass、timestamp。
- 文件命名：STDF 与 WAT CSV 为 `{product}_{lot}_{phase}_{timestamp}.{ext}`；CP CSV 为 `{product}_{lot}_{wafer}_CP_{timestamp}.csv`。
- 默认 UTF-8 无 BOM；可选 BOM 以兼容 Excel。
- CP CSV 固定按 wafer 输出；不提供合并为 lot 文件的选项。
- 时间戳：CSV 用 ISO 8601（UTC）；STDF 用其标准时间格式。
- 数值：CSV 使用点号小数；缺失值留空；`yield` 为 0–1 的分数、保留 6 位小数；STDF 使用标准 missing code。

### 4.7 CLI

```text
silicondraft generate -c scenario.yaml -o out/
silicondraft validate -c scenario.yaml
silicondraft schema
silicondraft version
```

常用参数：`--seed`、`--output`、`--formats stdf,csv`、`--lang en|zh`、`--log-level`、`--dry-run`、`--overwrite`、`--no-die-truth`。

- `generate` 一步完成生成与导出。
- `validate` 只校验并打印摘要（die 数、item 数、预计文件大小/耗时）。
- 退出码：0 成功、1 配置错误、2 生成错误、3 导出错误。
- 不提供纯命令行拼装完整 scenario 的模式；scenario YAML 是唯一入口。

### 4.8 GUI

- 单主窗口：左侧 scenario 配置树，右侧预览 tab，顶部 Preset/Generate/Cancel/Export/Language，底部进度条。
- 预览 tab：Wafer Map、Distribution、Correlation、Trend、Table。
- 配置以表单为主；另提供 YAML 编辑器对话框，加载/保存同一 scenario。
- Generate 在 worker 线程运行，支持进度与取消；完成后填充预览，Export 才可用。
- Export 对话框：输出目录、格式、ground truth、die truth；可覆盖当前 scenario 的导出选项。
- Wafer Map 支持按 bin 或选定 item 着色；支持 ground truth 模式叠加开关。
- 预览使用降采样；数据表分页。
- 记住语言、窗口布局与最近目录。

### 4.9 国际化

- 语言：`en`（默认）、`zh_CN`；GUI Settings → Language 实时切换；CLI `--lang`。
- GUI 字符串用 Qt `tr()` + `.ts/.qm`；CLI/引擎用 gettext `.po/.mo`；共享稳定错误码。
- 日志保持英文；导出文件中的 item ID、bin 名、列名保持英文。
- 日期/数字格式固定为 ISO 8601 与点号小数，不使用 locale 相关分隔符。
- 仓库文档按 CLAUDE.md：中文优先 + 英文折叠。

## 5. 默认值与性能

| 项目 | 默认值 |
|---|---|
| Wafer | 300mm，die 5.0×5.0mm，edge exclusion 3mm |
| Lot | 1 lot × 25 wafers；`trend` 预设 5 lots；最大 10 lots × 25 wafers |
| WAT sites | 9（中心 + 0.5R × 4 + 0.9R × 4） |
| CP sites | 4 |
| Items | 15 WAT + 21 CP |
| FUNC/SCAN 失败率 | 1% |
| 性能目标 | 单 lot 生成+导出 < 60s；内存 < 2GB |

## 6. 架构

- **核心引擎**：纯 Python + NumPy，不依赖 Qt；模块：
  - `scenario`（模型、加载、校验、JSON Schema）
  - `geometry`（wafer 布局、die grid、WAT 站点、多站点分配）
  - `catalog`（内置目录、预设、overrides）
  - `latent`（因子模型、相关性校准）
  - `patterns`（系统性空间模式）
  - `defects`（随机缺陷）
  - `binning`（hard/soft bin）
  - `dataset`（列式数据集、lot/wafer 元数据）
  - `groundtruth`
  - `exporters.csv` / `exporters.stdf`
  - `api`（公开 API）
  - `cli`
  - `gui`
- **公开 API**：

```python
from silicondraft import load_scenario, validate_scenario, generate, export

scenario = load_scenario("scenario.yaml")
result = generate(scenario)
export(result, out_dir="out", formats=("stdf", "csv"))
```

- **依赖**：核心 `numpy`、`PyYAML`；GUI extra `PySide6-Essentials`、`pyqtgraph`；测试 `pytest`、`hypothesis`、`pytest-qt`、`pystdf`（GPL-2.0，仅测试）、`stdfast`（可选第二 oracle）。
- **包布局**：`src/silicondraft/`、`tests/`、`docs/`。
- **平台**：Python 3.13；Windows 11、macOS 14+（Apple Silicon + Intel）官方支持；Linux best-effort。
- **打包**：V1 以 PyInstaller `onedir` 为工作假设；最终方案延后决定。只打包 PySide6-Essentials，动态链接 Qt，附 LGPL 文本与 notices。

## 7. 测试与 CI

- 单元测试：wafer 几何、catalog 校验、bin 规则、ground truth 一致性。
- 性质测试（Hypothesis）：die 数、无重叠、edge exclusion、scenario 校验。
- 相关性测试：实际 r 落在目标容差内。
- 模式测试：注入方向/幅度可检测，ground truth 与注入一致。
- Golden tests：STDF/CSV 语义比较（忽略时间戳）。
- 独立解析器：`pystdf` 解析生成的 STDF，交叉核对记录数与字段值；`stdfast` 可选第二 oracle。
- GUI 冒烟测试：pytest-qt。
- CI：GitHub Actions，Ubuntu + macOS + Windows，Python 3.13；ruff + mypy 严格模式 + pytest。

## 8. 验收标准

1. `silicondraft generate -c quick.yaml -o out/` 产出 CP STDF + CP CSV + WAT CSV + ground truth。
2. STDF 可被 `pystdf` 解析，记录数与关键字段值与 CSV 一致。
3. 目标 r ≥ 0.5 的联动对实际 r 误差 ≤ 0.05；其余 ≤ 0.08。
4. 注入的空间模式在 wafer map 上方向正确，ground truth 与注入参数一致。
5. 同一 scenario + seed 重复生成，数据一致（时间戳除外）。
6. CLI 可在无 GUI 环境运行，退出码符合约定。
7. GUI 完成 configure → generate → preview → export 全流程；中英文切换无需重启。
8. 单 lot 生成+导出 < 60s，内存 < 2GB。

## 9. 里程碑（垂直切片）

1. 项目骨架：pyproject、src layout、CI、scenario schema + 校验 + 预设。
2. Wafer 布局 + 几何测试。
3. Catalog + latent 生成 + binning + 测试。
4. CSV 导出 + ground truth + CLI。
5. STDF writer + `pystdf` 交叉验证。
6. GUI：配置 + 生成 + 预览 + 导出 + i18n。
7. 打包 spike（决定 PyInstaller/Nuitka 细节，不阻塞前六步）。

## 10. 未决与延后

- FT：V2。
- 最终打包方案：PyInstaller vs Nuitka，另行决定。
- 真实测试程序对齐：如有现成清单，后续替换默认目录。
- Reticle field 级模式、die 旋转、flat 朝向：V2 候选。
- Linux 支持：best-effort。
- macOS 13 及以下：不支持。

## 11. 验收场景

| YMS 功能 | 数据特征 | Ground truth 用途 |
|---|---|---|
| STDF/CSV 导入解析 | CP STDF + CSV、WAT CSV 完整可读 | 文件清单与记录数 |
| 良率/bin 分析 | lot/wafer/die 良率、hard/soft bin Pareto | 每 wafer 真实良率与 bin |
| Wafer map / 空间模式 | 注入 center/edge/ring/spot 模式 | 模式清单与影响范围 |
| SPC/Cpk | 受控分布、规格限、outlier wafer | latent factor 与真实分布参数 |
| WAT↔CP 相关性 | 目标相关系数联动 | 目标 vs 实际 r |
| 异常检测 | 随机缺陷簇聚、outlier wafer | 真实缺陷位置与簇参数 |

<details>
<summary>English</summary>

# SiliconDraft V1 Specification (Draft)

> Status: local draft (2026-11-02), not yet published to GitHub. Once approved, it becomes the V1 spec issue.
> Related: [GLOSSARY.md](../../GLOSSARY.md) · [V1 test item catalog](v1-test-item-catalog.md) · [ADR-0001](../adr/0001-latent-factor-generation-model.md) · [ADR-0002](../adr/0002-own-stdf-v4-writer.md) · [ADR-0003](../adr/0003-engine-gui-separation-and-i18n.md)

## 1. Background and goals

SiliconDraft generates reproducible synthetic semiconductor test data to validate yield management system (YMS) functions: data import, yield/bin analysis, wafer maps and spatial patterns, SPC/Cpk, and WAT↔CP correlation. V1 generates CP and WAT only; FT is planned for V2. The generator also emits a ground-truth manifest so an external validation harness can score the YMS's detection results.

## 2. Scope

### 2.1 In scope

- Scenario YAML (versioned schema, JSON Schema validation, `quick` / `trend` / `demo` presets).
- Wafer geometry: 150/200/300 mm, die grid, edge exclusion, notch orientation, multi-site CP probing.
- WAT measured at PCM/TEG sites (9 sites by default); CP measured per die.
- Built-in generic 55 nm CMOS logic test item catalog: 15 WAT items + 21 CP items, overridable.
- Latent-factor linkage engine with target correlation calibration.
- Systematic spatial patterns and random defects modeled separately and composable.
- Hard bin / soft bin.
- Ground truth: JSON summary + per-die CSV.GZ.
- Export: one STDF V4 per CP lot plus one wide CSV per wafer; one long CSV per WAT lot.
- CLI and GUI; English-first with a Chinese switch; GUI ground-truth overlay.

### 2.2 Out of scope (V1)

- FT data, FT test items, CP→FT unit traceability (V2).
- Importing real test data; YMS analysis/scoring; database, server, network upload, multi-user.
- Reticle-field-level patterns, die rotation, flat orientation.
- macOS below 14; Linux is best-effort only.
- Final packaging choice (PyInstaller vs Nuitka). V1 assumes PyInstaller `onedir`.

## 3. Domain model

Terminology follows [GLOSSARY.md](../../GLOSSARY.md). Core relationships:

- `Product` → `Lot` → `Wafer` → `Die` (CP measures per die).
- `Wafer` → `WAT site` (PCM/TEG, a few sites per wafer).
- `Die` → `Test site` (probe-card site in multi-site probing).
- `Scenario` → latent process factors → WAT/CP test items → hard/soft bins.
- `Ground truth manifest` records injected patterns, latent factors, target/achieved correlations, and per-die truth.

## 4. Functional requirements

### 4.1 Scenario

#### 4.1.1 File format and versioning

- Authoring format is YAML; `schema_version` is a required integer and is `1` in V1.
- A JSON Schema is provided; `silicondraft validate` and GUI loading perform structural and semantic validation (die grid fits the wafer, item references exist, bin codes are unique, linkage references exist, etc.).
- The GUI saves the fully resolved scenario, not just a diff, to guarantee reproducibility.

#### 4.1.2 Sections

`schema_version`, `product`, `wafer`, `lots`, `items`, `patterns`, `linkage`, `export`, `seed`, `metadata`.

`product.test_program` is optional and names the test program; when omitted it falls back to `items.preset`.

#### 4.1.3 Presets

- `quick`: 1 lot × 25 wafers, no injected patterns, for fast validation.
- `trend`: 5 lots × 25 wafers across dates, for lot/wafer trends.
- `demo`: 1 lot × 25 wafers with multiple spatial patterns and strong linkage, for demos and YMS detection validation.

#### 4.1.4 Example

```yaml
schema_version: 1

product:
  name: GEN55LOGIC
  device_family: cmos_logic
  process_node: "55nm"
  fab: FAB-A
  test_program: GEN55LOGIC_CP

wafer:
  diameter_mm: 300
  die_size_mm: [5.0, 5.0]
  edge_exclusion_mm: 3.0
  notch: down
  cp_sites: 4
  wat_sites: 9

lots:
  count: 1
  wafers_per_lot: 25
  lot_id_template: "{product}-L{lot:03d}"
  wafer_id_template: "W{wafer:02d}"
  start_date: "2026-01-05T08:00:00"
  wat_to_cp_gap_min: 120
  cp_duration_min_per_wafer: 45
  lot_interval_hours: 168

items:
  preset: generic_cmos_logic_55nm
  overrides: []

patterns:
  - kind: edge_low
    scope: lot
    target: yield
    amplitude: 0.08
    extent_mm: 25.0
  - kind: center_high
    scope: wafer
    target_item: CP_FRO
    amplitude: 0.05
    radius_mm: 40.0

linkage:
  overrides:
    - wat: WAT_VTN
      cp: CP_VTHN
      target_r: 0.80

export:
  cp_stdf: true
  cp_csv: true
  wat_csv: true
  ground_truth: true
  include_die_truth: true
  encoding: utf-8

seed: 20260105

metadata:
  author: ""
  note: "quick preset"
```

### 4.2 Wafer layout

- Diameters 150/200/300 mm, default 300 mm.
- Die size configurable, default 5.0×5.0 mm.
- Edge exclusion default 3.0 mm; only complete dies whose centre lies inside the usable radius are kept; no partial dies.
- Notch down; origin at wafer centre; +X right, +Y up.
- Internal geometry in mm; STDF PRR uses integer grid indices; CSV includes both mm and grid.
- CP multi-site: 4 sites by default, assigned in test order; optional site offsets; STDF PTR/PRR populate `SITE_NUM`.
- WAT sites: 9 by default = centre + 4 orthogonal at 0.5R + 4 diagonal at 0.9R; configurable to 5/9/13/21.
- WAT is generated per wafer within the lot and timestamps precede CP.

### 4.3 Test item catalog

- Built-in `generic_cmos_logic_55nm` preset: 15 WAT + 21 CP items, defined in [V1 test item catalog](v1-test-item-catalog.md).
- Each item has `test_num`, canonical English ID, unit, typical value, LSL/USL, distribution, business meaning, and test conditions.
- `items.overrides` can add/remove items and change units, limits, distributions, and linkage parameters. GUI V1 only enables/disables items and edits limits; a full item editor is V2.
- Export files use canonical English IDs only; Chinese names are UI-only.

### 4.4 Generation pipeline

#### 4.4.1 Pipeline

`scenario validation → wafer layout → latent factors (lot/wafer/die levels) → WAT site values → CP item values → systematic pattern injection → random defects → binning → ground truth → preview/export`.

#### 4.4.2 Latent factors and calibration

- Six shared factors: `F_VT`, `F_MOB`, `F_TOX`, `F_RC`, `F_LEAK`, `F_SC`.
- Each factor decomposes into lot-level, wafer-level, and die-level components plus independent measurement noise; WAT and CP load on the same factors through a sensitivity matrix.
- Target correlations come from the default linkage table or scenario overrides. The engine calibrates loadings so the achieved correlation stays within tolerance: absolute error ≤ 0.05 for target r ≥ 0.5, otherwise ≤ 0.08.
- The generation report lists target/achieved r for every WAT↔CP pair.

#### 4.4.3 Systematic spatial patterns

V1 pattern catalog: `center-high`, `center-low`, `edge-high`, `edge-low`, `ring`, `radial-gradient`, `local-spot`.

- Each pattern specifies: target (yield / selected item / both), amplitude, spatial extent (radius or width), scope (lot or wafer), and composition mode.
- Patterns compose; multiple patterns may coexist on one wafer.
- Patterns act on die-level values or die pass/fail; they never write bin codes directly—bins are derived by rules.

#### 4.4.4 Random defects

- Default model is negative-binomial/clustered: defect density + clustering parameter; Poisson is configurable.
- Defects cause `CP_FUNC` / `CP_SCAN` failures or failures of selected items; default total `CP_FUNC`/`CP_SCAN` failure rate is 1%.
- Defect results appear in ground truth for validating the YMS's clustering/outlier detection.

#### 4.4.5 Binning

- Default hard bins: 1=pass, 2=parametric fail, 3=functional/structural fail, 4=continuity/contact fail.
- Default soft bins: 100=pass, 201=continuity, 202=leakage, 203=Iddq, 204=Vth, 205=frequency, 206=functional/scan, 207=other parametric.
- Pass/fail is derived from spec limits and bin rules; the bin table is overridable in the scenario.
- STDF writes HBR/SBR; the CSV `[BIN_DEFINITIONS]` block carries bin definitions, and `[TEST_DATA]` includes hard/soft bin columns.

#### 4.4.6 Reproducibility

- `seed` is required; random streams are derived per lot/wafer/item so the same scenario + seed produces identical data (excluding timestamps).
- Ground truth records `scenario_sha256`, engine version, and seed.

### 4.5 Ground truth

- JSON summary: engine version, full scenario + SHA-256, seed, generation time, product, lot/wafer summary, per-wafer yield, latent-factor means, injected pattern manifest, target vs achieved correlations, outlier wafers, and per-die truth file names.
- Per-die CSV.GZ: `lot_id, wafer_id, die_x_mm, die_y_mm, grid_x, grid_y, test_site, true_pass, true_hard_bin, true_soft_bin, F_VT, F_MOB, F_TOX, F_RC, F_LEAK, F_SC, pattern_ids`.
- `--no-die-truth` disables per-die truth output.

### 4.6 Export

- **CP STDF V4**: MIR, MRR, PCR, HBR, SBR, WIR, WRR, WCR, PIR, PRR, PTR, TSR.
- **CP CSV**: one wide CSV per wafer with a four-block layout (see [ADR-0005](../adr/0005-cp-csv-multiblock-layout.md)):
  - `[METADATA]`: `key,value` rows carrying `csv_format_version`, `scenario_schema_version`, `phase`, `lot_id`, `product`, `device_family`, `process_node`, `fab`, `test_program`, `tester_type`, `exec_type`, `exec_version`, `generated_at`, `seed`, `scenario_sha256`, `wafer_id`, `diameter_mm`, `die_size_x_mm`, `die_size_y_mm`, `edge_exclusion_mm`, `notch`, `cp_sites`, `die_count`, `pass_count`, and `yield`; the semantic mapping to STDF fields is documented in ADR-0005.
  - `[TEST_ITEMS]`: `test_num,item_id,unit,typical,lsl,usl,description`, one row per enabled CP item in catalog order.
  - `[BIN_DEFINITIONS]`: `bin_type,bin_number,bin_name,pass_fail,hard_bin,description`, defining hard bins and, later, soft bins and their mapping; `pass_fail` uses `P`/`F`.
  - `[TEST_DATA]`: one row per die with `die_x_mm,die_y_mm,grid_x,grid_y,test_site,hard_bin,pass` plus one column per enabled item.
  - Each block starts with a standalone `[SECTION]` marker row, followed by a header row and data rows; no blank lines between blocks.
- **WAT CSV**: one long CSV per lot, one row per wafer × site × item; site mm coordinates, test_num, item_id, value, unit, LSL/USL, pass, timestamp.
- File naming: `{product}_{lot}_{phase}_{timestamp}.{ext}` for STDF and WAT CSV; `{product}_{lot}_{wafer}_CP_{timestamp}.csv` for CP CSV.
- UTF-8 without BOM by default; optional BOM for Excel compatibility.
- CP CSV is always per wafer; there is no option to merge it into a lot file.
- Timestamps: ISO 8601 (UTC) in CSV; STDF standard time format.
- Numbers: dot decimal in CSV; empty cells for missing values; `yield` is a 0–1 fraction with six decimal places; standard STDF missing codes.

### 4.7 CLI

```text
silicondraft generate -c scenario.yaml -o out/
silicondraft validate -c scenario.yaml
silicondraft schema
silicondraft version
```

Common flags: `--seed`, `--output`, `--formats stdf,csv`, `--lang en|zh`, `--log-level`, `--dry-run`, `--overwrite`, `--no-die-truth`.

- `generate` performs generation and export in one step.
- `validate` validates and prints a summary (die count, item count, estimated file size/runtime).
- Exit codes: 0 success, 1 configuration error, 2 generation error, 3 export error.
- No fully flag-driven mode for assembling a complete scenario; scenario YAML is the single entry point.

### 4.8 GUI

- Single main window: scenario tree on the left; preview tabs on the right; Preset/Generate/Cancel/Export/Language toolbar; progress bar at the bottom.
- Preview tabs: Wafer Map, Distribution, Correlation, Trend, Table.
- Form-based configuration plus a YAML editor dialog loading/saving the same scenario.
- Generate runs in a worker thread with progress and cancel; preview fills on completion and Export becomes available.
- Export dialog: output directory, formats, ground truth, die truth; it may override the scenario's export options for the current run.
- Wafer Map colours by bin or selected item; optional ground-truth overlay.
- Preview uses downsampling; the table is paginated.
- Remembers language, window layout, and recent directories.

### 4.9 Internationalization

- Languages: `en` (default), `zh_CN`; GUI switches live via Settings → Language; CLI uses `--lang`.
- GUI strings use Qt `tr()` + `.ts/.qm`; CLI/engine messages use gettext `.po/.mo`; stable error codes are shared.
- Logs stay in English; item IDs, bin names, and column names in exported files stay in English.
- Dates/numbers are ISO 8601 and dot decimal; no locale-specific separators.
- Repository docs follow CLAUDE.md: Chinese first with a collapsed English version.

## 5. Defaults and performance

| Item | Default |
|---|---|
| Wafer | 300 mm, die 5.0×5.0 mm, edge exclusion 3 mm |
| Lot | 1 lot × 25 wafers; `trend` preset 5 lots; max 10 lots × 25 wafers |
| WAT sites | 9 (centre + 4 at 0.5R + 4 at 0.9R) |
| CP sites | 4 |
| Items | 15 WAT + 21 CP |
| FUNC/SCAN failure rate | 1% |
| Performance target | < 60 s per lot generation+export; < 2 GB memory |

## 6. Architecture

- **Core engine**: pure Python + NumPy, no Qt dependency. Modules:
  - `scenario` (models, loading, validation, JSON Schema)
  - `geometry` (wafer layout, die grid, WAT sites, multi-site assignment)
  - `catalog` (built-in catalog, presets, overrides)
  - `latent` (factor model, correlation calibration)
  - `patterns` (systematic spatial patterns)
  - `defects` (random defects)
  - `binning` (hard/soft bins)
  - `dataset` (columnar dataset, lot/wafer metadata)
  - `groundtruth`
  - `exporters.csv` / `exporters.stdf`
  - `api` (public API)
  - `cli`
  - `gui`
- **Public API**:

```python
from silicondraft import load_scenario, validate_scenario, generate, export

scenario = load_scenario("scenario.yaml")
result = generate(scenario)
export(result, out_dir="out", formats=("stdf", "csv"))
```

- **Dependencies**: core `numpy`, `PyYAML`; GUI extra `PySide6-Essentials`, `pyqtgraph`; tests `pytest`, `hypothesis`, `pytest-qt`, `pystdf` (GPL-2.0, test-only), `stdfast` (optional second oracle).
- **Package layout**: `src/silicondraft/`, `tests/`, `docs/`.
- **Platforms**: Python 3.13; Windows 11 and macOS 14+ (Apple Silicon + Intel) officially supported; Linux best-effort.
- **Packaging**: V1 assumes PyInstaller `onedir`; the final choice is deferred. Bundle PySide6-Essentials only, link Qt dynamically, and ship LGPL texts and notices.

## 7. Testing and CI

- Unit tests: wafer geometry, catalog validation, bin rules, ground-truth consistency.
- Property tests (Hypothesis): die count, no overlap, edge exclusion, scenario validation.
- Correlation tests: achieved r within target tolerance.
- Pattern tests: injected direction/amplitude is detectable; ground truth matches the injection.
- Golden tests: semantic STDF/CSV comparison (timestamps ignored).
- Independent parser: `pystdf` parses generated STDF and cross-checks record counts and field values; `stdfast` is an optional second oracle.
- GUI smoke tests: pytest-qt.
- CI: GitHub Actions, Ubuntu + macOS + Windows, Python 3.13; ruff + mypy strict + pytest.

## 8. Acceptance criteria

1. `silicondraft generate -c quick.yaml -o out/` produces CP STDF + CP CSV + WAT CSV + ground truth.
2. STDF parses with `pystdf`; record counts and key field values match the CSV.
3. For linkage pairs with target r ≥ 0.5, achieved r error ≤ 0.05; otherwise ≤ 0.08.
4. Injected spatial patterns have the correct direction on the wafer map, and ground truth matches the injection parameters.
5. The same scenario + seed produces identical data (excluding timestamps).
6. CLI runs headless; exit codes follow the contract.
7. GUI completes configure → generate → preview → export; English/Chinese switch requires no restart.
8. Per-lot generation + export < 60 s, memory < 2 GB.

## 9. Milestones (vertical slices)

1. Project skeleton: pyproject, src layout, CI, scenario schema + validation + presets.
2. Wafer layout + geometry tests.
3. Catalog + latent generation + binning + tests.
4. CSV export + ground truth + CLI.
5. STDF writer + `pystdf` cross-validation.
6. GUI: configuration + generation + preview + export + i18n.
7. Packaging spike (PyInstaller/Nuitka details; does not block the first six).

## 10. Deferred and open

- FT: V2.
- Final packaging choice: PyInstaller vs Nuitka, decided later.
- Alignment with a real test program: replace the default catalog if a real list becomes available.
- Reticle-field-level patterns, die rotation, flat orientation: V2 candidates.
- Linux: best-effort.
- macOS 13 and below: unsupported.

## 11. Acceptance scenarios

| YMS function | Data feature | Ground-truth use |
|---|---|---|
| STDF/CSV import | Complete readable CP STDF + CSV, WAT CSV | File list and record counts |
| Yield/bin analysis | Lot/wafer/die yield, hard/soft bin Pareto | True per-wafer yield and bins |
| Wafer map / spatial patterns | Injected centre/edge/ring/spot patterns | Pattern manifest and extent |
| SPC/Cpk | Controlled distributions, spec limits, outlier wafers | Latent factors and true distribution parameters |
| WAT↔CP correlation | Target-correlation linkage | Target vs achieved r |
| Outlier detection | Clustered random defects, outlier wafers | True defect locations and cluster parameters |

</details>

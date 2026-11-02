## 问题陈述

验证良率管理系统（YMS）需要覆盖数据导入、良率/bin 分析、wafer map 与空间模式、SPC/Cpk、WAT↔CP 相关性等能力。但真实晶圆厂数据难以获取，而且没有已知的 ground truth：无法确认某个空间模式是否真的存在、某对测试项的真实相关系数是多少、某颗 die 的真实 bin 是什么。结果是 YMS 的检测与相关性算法只能靠人工抽查，无法自动化验收；真实数据也往往只覆盖少数场景，难以系统性构造中心偏高/边缘偏低、随机缺陷簇、outlier wafer 等边界情况。

## 解决方案

SiliconDraft 是一个 scenario 驱动的合成 CP/WAT 测试数据生成器，同时提供 CLI 与 GUI。用户按 wafer 几何、lot/wafer 数量、测试项目录、空间模式与联动关系配置一次生成；工具输出可复现的 CP/WAT 数据、CP STDF V4 与 CSV、WAT CSV，以及机器可读的 ground truth manifest，供外部验证 harness 对 YMS 的检测和相关性结果打分。V1 覆盖 CP 与 WAT；FT 在 V2 支持。

## 用户故事

### 场景与配置

1. 作为良率工程师，我希望用 YAML 定义一次生成场景，以便场景可审查、可版本化、可复现。
2. 作为良率工程师，我希望 scenario 带 `schema_version`，以便未来升级时能明确识别旧格式。
3. 作为良率工程师，我希望有 `quick` / `trend` / `demo` 三个内置预设，以便不写完整配置也能开始。
4. 作为良率工程师，我希望 GUI 保存完全展开后的 scenario，以便从界面操作也能精确复现。
5. 作为良率工程师，我希望生成前执行结构和语义校验，以便在浪费算力前发现错误。
6. 作为良率工程师，我希望校验覆盖 die grid 能否放入 wafer、item 引用、bin 码唯一性、linkage 引用，以便生成数据内部一致。
7. 作为良率工程师，我希望在预设基础上覆盖测试项、限值和分布，以便匹配我的产品。
8. 作为良率工程师，我希望设置随机种子，以便同一场景重复生成得到相同数据。
9. 作为良率工程师，我希望在场景中记录 product、fab、process node 和备注，以便导出文件自描述。

### Wafer 与测试结构

10. 作为良率工程师，我希望选择 150/200/300mm 晶圆，以便匹配我的产线。
11. 作为良率工程师，我希望配置 die 尺寸和 edge exclusion，以便 die 数与 wafer map 接近真实。
12. 作为良率工程师，我希望采用 notch 朝下、+X 向右、+Y 向上的坐标约定，以便与 YMS 的 wafer map 对齐。
13. 作为良率工程师，我希望不生成 partial die，以便良率口径与生产规则一致。
14. 作为良率工程师，我希望 CP 数据带 test site 信息，以便验证多站点并测分析。
15. 作为良率工程师，我希望 WAT 只在 PCM/TEG 站点测量，以便 WAT 数据符合真实抽样方式。
16. 作为良率工程师，我希望 WAT 站点数可配置（5/9/13/21），以便测试不同抽样密度。
17. 作为良率工程师，我希望 WAT 时间早于 CP，以便时间线与真实流程一致。

### 测试项与联动

18. 作为良率工程师，我希望内置 55nm CMOS 逻辑目录（15 个 WAT + 21 个 CP 项），以便开箱即用且业务含义明确。
19. 作为良率工程师，我希望每个测试项带单位、限值、分布和业务说明，以便 YMS 正确展示和分析。
20. 作为良率工程师，我希望通过配置增删改测试项，以便对齐我的测试程序。
21. 作为良率工程师，我希望 WAT 与 CP 的相关项保持联动，以便相关性分析能找到真实关系。
22. 作为良率工程师，我希望逐对设置目标相关系数，以便验证相关性算法在不同强度下的表现。
23. 作为良率工程师，我希望支持正相关和负相关，以便覆盖两种业务方向。
24. 作为良率工程师，我希望一个 WAT 项可以联动多个 CP 项，以便反映共享工艺因子。
25. 作为良率工程师，我希望生成报告输出目标 vs 实际相关系数，以便确认数据达标。
26. 作为良率工程师，我希望 ground truth 包含 latent factor 值，以便解释相关性的来源。

### 空间模式与随机缺陷

27. 作为良率工程师，我希望注入 center-high / center-low 模式，以便验证中心-边缘良率分析。
28. 作为良率工程师，我希望注入 edge-high / edge-low 模式，以便验证边缘排除和空间分析。
29. 作为良率工程师，我希望注入 ring / radial-gradient 模式，以便验证径向趋势检测。
30. 作为良率工程师，我希望注入 local-spot 模式，以便验证热点检测。
31. 作为良率工程师，我希望模式可以作用于 yield 或指定测试项，以便同时验证良率图和参数图。
32. 作为良率工程师，我希望模式可以作用于 lot 或单张 wafer，以便模拟系统性与单片异常。
33. 作为良率工程师，我希望多个模式可以叠加，以便 YMS 必须分离混合模式。
34. 作为良率工程师，我希望随机缺陷带空间簇聚，以便验证缺陷簇分析。
35. 作为良率工程师，我希望缺陷密度和簇聚参数可配置，以便调节难度。
36. 作为良率工程师，我希望 `CP_FUNC` / `CP_SCAN` 默认总失败率约 1%，以便基线良率真实。
37. 作为良率工程师，我希望模式不直接改写 bin 码，而被 bin 规则推导，以便数据自洽。

### Binning 与良率

38. 作为良率工程师，我希望同时生成 hard bin 和 soft bin，以便良率与失效 Pareto 都能分析。
39. 作为良率工程师，我希望 bin 表可配置，以便 bin 码匹配我的 YMS。
40. 作为良率工程师，我希望 pass/fail 由 spec limits 推导，以便 binning 与参数结果一致。
41. 作为良率工程师，我希望 ground truth 包含 lot/wafer/die 良率，以便核对 YMS 计算。

### Ground truth

42. 作为验证工程师，我希望输出机器可读的 ground truth manifest，以便自动评估 YMS 的检测结果。
43. 作为验证工程师，我希望每 die 真值包含 pass/fail、hard/soft bin、latent factor 和 pattern ID，以便与 YMS 结果逐颗 join。
44. 作为验证工程师，我希望 manifest 包含目标 vs 实际相关系数，以便验证 YMS 的相关性结果。
45. 作为验证工程师，我希望 manifest 包含 outlier wafer 和模式清单，以便计算检测召回率。
46. 作为验证工程师，我希望 manifest 记录完整 scenario 与 SHA-256，以便复现实验。
47. 作为验证工程师，我希望可以关闭每 die 真值输出，以便减小文件体积。

### 导出

48. 作为良率工程师，我希望 CP 导出 STDF V4，以便标准 YMS 直接导入。
49. 作为良率工程师，我希望 CP 导出 wide CSV，以便表格工具和自研脚本直接使用。
50. 作为良率工程师，我希望 WAT 导出 long CSV，以便稀疏站点数据自然表达。
51. 作为良率工程师，我希望 STDF 包含 MIR/MRR/PCR/HBR/SBR/WIR/WRR/WCR/PIR/PRR/PTR/TSR，以便文件完整。
52. 作为良率工程师，我希望文件名包含 product/lot/phase/timestamp，以便快速识别。
53. 作为良率工程师，我希望 CSV 可选择 split-by-wafer，以便测试按片导入。
54. 作为良率工程师，我希望时间戳用 ISO 8601、数值用点号小数，以便跨 locale 解析一致。
55. 作为良率工程师，我希望 CSV 默认 UTF-8 无 BOM，并可选择 BOM，以便兼顾 Excel 与 YMS。
56. 作为良率工程师，我希望 STDF 使用标准 missing code，以便缺失值被正确识别。

### CLI

57. 作为验证工程师，我希望 CLI 一条命令完成生成与导出，以便在 CI 中无人值守运行。
58. 作为验证工程师，我希望 CLI 提供 validate 子命令，以便不生成也能检查场景。
59. 作为验证工程师，我希望 CLI 提供 schema 子命令，以便集成 JSON Schema 工具。
60. 作为验证工程师，我希望退出码有明确约定，以便自动化流程正确分支。
61. 作为验证工程师，我希望用 `--seed` / `--output` / `--formats` / `--lang` 覆盖少量参数，以便复用同一场景做多组实验。
62. 作为验证工程师，我希望 CLI 支持英文/中文消息，以便团队使用。

### GUI

63. 作为良率工程师，我希望单主窗口左侧配置、右侧预览，以便快速调参和看效果。
64. 作为良率工程师，我希望 wafer map 按 bin 或选定参数着色，以便导出前确认空间模式。
65. 作为良率工程师，我希望查看分布直方图，以便确认限值和分布。
66. 作为良率工程师，我希望查看 WAT↔CP 散点图，以便肉眼确认相关性。
67. 作为良率工程师，我希望查看 lot/wafer 趋势和数据表，以便检查批量数据。
68. 作为良率工程师，我希望生成过程可取消并显示进度，以便控制长任务。
69. 作为良率工程师，我希望导出对话框可选择格式、split-by-wafer 和 ground truth，以便一次生成多种产物。
70. 作为良率工程师，我希望在 wafer map 上叠加 ground truth 模式，以便对比注入与观测。
71. 作为良率工程师，我希望 GUI 保存/加载 scenario YAML，以便共享和复现配置。
72. 作为用户，我希望界面英文默认、中文可切换且无需重启，以便适配我的语言。
73. 作为用户，我希望记住语言、窗口布局和最近目录，以便重复使用。
74. 作为高级用户，我希望 GUI 提供 YAML 编辑器，以便表单覆盖不到的高级配置也能编辑。

### 质量与开发者

75. 作为验证工程师，我希望同一 scenario + seed 生成完全相同的数据（时间戳除外），以便测试和对比可靠。
76. 作为验证工程师，我希望单 lot 生成+导出在 60s 内、内存低于 2GB，以便本地迭代。
77. 作为开发者，我希望通过公开 Python API 调用生成与导出，以便写脚本而不依赖 CLI/GUI。
78. 作为开发者，我希望核心引擎不依赖 Qt，以便在无 GUI 环境运行。
79. 作为维护者，我希望 STDF 输出用独立解析器验证，以便确认互操作性。
80. 作为维护者，我希望几何与相关性有性质测试和容差测试，以便及早发现回归。
81. 作为维护者，我希望 CI 覆盖 Windows/macOS/Ubuntu，以便平台问题尽早暴露。

## 实现决策

1. **Scenario 格式**：YAML 是唯一入口；`schema_version: 1`；分节为 `product`、`wafer`、`lots`、`items`、`patterns`、`linkage`、`export`、`seed`、`metadata`；提供 JSON Schema 与语义校验；内置 `quick` / `trend` / `demo` 预设；GUI 保存完全展开后的 scenario。
2. **公开 API**：`load_scenario`、`validate_scenario`、`generate`、`export`；`generate` 返回 `GenerationResult`，包含 dataset、ground truth 与 generation report；CLI/GUI 只调用公开 API。
3. **引擎边界**：核心引擎纯 Python + NumPy，不依赖 Qt；CLI 与 GUI 是适配层；不把 pandas 引入核心。
4. **生成流水线**：scenario 校验 → wafer 布局 → latent factors（lot/wafer/die 三层）→ WAT 站点值 → CP item 值 → 系统性模式注入 → 随机缺陷 → binning → ground truth → 预览/导出；多 lot 逐个生成并释放。
5. **Wafer 几何**：150/200/300mm；默认 300mm、5.0×5.0mm die、3mm edge exclusion；notch 朝下、+X 向右、+Y 向上；内部用 mm，STDF 用 grid index，CSV 两者都输出；不生成 partial die；CP 默认 4 site；WAT 默认 9 点（中心 + 0.5R×4 + 0.9R×4）。
6. **测试项目录**：默认 `generic_cmos_logic_55nm`（15 WAT + 21 CP），每项含 `test_num`、规范英文 ID、单位、LSL/USL、分布、业务说明；`items.overrides` 可增删改；导出只用英文 ID。
7. **Latent factor**：`F_VT`、`F_MOB`、`F_TOX`、`F_RC`、`F_LEAK`、`F_SC`；lot/wafer/die 分量 + 测量噪声；灵敏度矩阵；目标 r 校准，目标 r ≥ 0.5 时绝对误差 ≤ 0.05，否则 ≤ 0.08；报告输出实际 r。
8. **空间模式**：`center-high`、`center-low`、`edge-high`、`edge-low`、`ring`、`radial-gradient`、`local-spot`；可作用于 yield 或指定 item；作用域为 lot 或 wafer；参数含幅度与空间范围；可叠加；不直接写 bin。
9. **随机缺陷**：默认负二项/簇聚模型，Poisson 可配；参数为缺陷密度与簇聚强度；默认 `CP_FUNC`/`CP_SCAN` 总失败率 1%；缺陷结果进入 ground truth。
10. **Binning**：hard bin 默认 1=pass、2=parametric fail、3=functional/structural fail、4=continuity/contact fail；soft bin 默认 100=pass、201=continuity、202=leakage、203=Iddq、204=Vth、205=frequency、206=functional/scan、207=other parametric；bin 表可配置；pass/fail 由 spec limits 推导；STDF 输出 HBR/SBR，CSV 双列。
11. **Ground truth**：JSON 摘要（引擎版本、完整 scenario + SHA-256、seed、生成时间、product、lot/wafer 摘要、每 wafer 良率、latent 均值、模式清单、目标/实际 r、outlier wafer、die truth 文件名）+ 每 die CSV.GZ（坐标、site、true pass/bin、latent factors、pattern IDs）；`--no-die-truth` 可关闭每 die 真值。
12. **导出**：CP 每 lot 一个 STDF V4（MIR/MRR/PCR/HBR/SBR/WIR/WRR/WCR/PIR/PRR/PTR/TSR）+ 一个 wide CSV；WAT 每 lot 一个 long CSV；命名 `{product}_{lot}_{phase}_{timestamp}.{ext}`；默认 UTF-8 无 BOM；时间戳 ISO 8601；点号小数；STDF 标准 missing code；`--split-by-wafer` 可拆分 CSV。
13. **CLI**：`generate` / `validate` / `schema` / `version`；参数 `--seed`、`--output`、`--formats`、`--split-by-wafer`、`--lang`、`--log-level`、`--dry-run`、`--overwrite`、`--no-die-truth`；退出码 0 成功、1 配置错误、2 生成错误、3 导出错误；YAML 是唯一入口，不提供纯 flag 拼装完整场景。
14. **GUI**：单主窗口；左侧 scenario 树，右侧 Wafer Map / Distribution / Correlation / Trend / Table tabs；Generate 在 worker 线程运行，支持进度与取消；Export 对话框可覆盖格式与 split 选项；wafer map 支持 ground truth 叠加；支持 scenario 保存/加载与 YAML 编辑器；记住语言、窗口布局与最近目录。
15. **国际化**：`en` 默认、`zh_CN` 可切换；GUI 用 Qt `.ts/.qm`，CLI/engine 用 gettext；共享稳定错误码；日志保持英文；导出文件中的 item ID、bin 名、列名保持英文；日期 ISO 8601、点号小数；仓库文档中文优先 + 英文折叠。
16. **依赖与平台**：Python 3.13；核心依赖 `numpy`、`PyYAML`；GUI 依赖 `PySide6-Essentials`、`pyqtgraph`；测试依赖 `pytest`、`hypothesis`、`pytest-qt`、`pystdf`（GPL-2.0，仅测试）、可选 `stdfast`；Windows 11 与 macOS 14+ 官方支持，Linux best-effort。
17. **许可证与打包**：项目 MIT；避免 QtCharts/QtGraphs/QtDataVisualization 等 GPLv3-only 模块；PySide6 动态链接并附 LGPL 文本与 notices；首版以 PyInstaller `onedir` 为工作假设，最终打包方案延后。
18. **可复现性**：`seed` 必填；随机流按 lot/wafer/item 派生；manifest 记录 scenario hash；同一 scenario + seed 除时间戳外完全一致。
19. **性能**：单 lot 生成+导出 < 60s、内存 < 2GB；STDF 流式写出；预览降采样。
20. **测试 seam**：公开 API 是唯一主 seam；CLI subprocess 与 GUI pytest-qt 各一个 smoke test；内部模块不单独设 seam。

## 测试决策

- **好测试的标准**：只断言外部可观察行为，不测试内部实现细节；通过公开 API 构造 scenario、调用 `generate` / `export`，再断言 dataset、ground truth 与导出文件；使用固定 seed 保证确定性；对统计量使用容差与方向断言，不比较精确浮点值。
- **主 seam**：公开引擎 API（`load_scenario` / `validate_scenario` / `generate` / `export`）。所有领域与导出测试都走这一 seam，覆盖 scenario 校验、wafer 几何、catalog、latent 与相关性、模式、随机缺陷、binning、ground truth、CSV 与 STDF 导出。
- **次级 smoke seam**：CLI 用一个小 scenario 通过 subprocess 跑 `generate`，断言退出码、产物文件与 STDF 可解析；GUI 用 pytest-qt 跑一次 configure → generate → preview → export，断言窗口状态与导出文件。两者不复制领域测试。
- **性质测试**：用 Hypothesis 覆盖 die 数、无重叠、edge exclusion、scenario 校验等不变量。
- **相关性测试**：断言目标 r ≥ 0.5 时实际误差 ≤ 0.05，否则 ≤ 0.08；同时断言符号方向。
- **模式测试**：断言注入方向与幅度可检测，ground truth 与注入参数一致。
- **STDF 测试**：用 `pystdf` 解析生成文件，交叉核对记录数与关键字段值；`stdfast` 作为可选第二 oracle。
- **Golden tests**：CSV/STDF 做语义比较，忽略时间戳，不做字节级比较。
- **CI**：GitHub Actions，Ubuntu + macOS + Windows，Python 3.13；ruff + mypy 严格模式 + pytest。
- **Prior art**：仓库尚无代码与测试；本 spec 的测试是第一套，后续模块按同一 seam 模式扩展。
- **测试夹具**：一个 tiny scenario（1 wafer、小 die grid）用于快速测试；`quick` 与 `demo` 预设用于集成测试。

## 范围之外

- FT 数据、FT 测试项、CP→FT 单颗追溯（V2）。
- 导入真实测试数据；实现 YMS 的分析或评分逻辑；数据库、服务端、网络上传、多用户。
- Reticle field 级空间模式、die 旋转、flat 朝向建模。
- macOS 14 以下；Linux 除 best-effort 之外的官方支持。
- 最终打包方案（PyInstaller vs Nuitka）。
- GUI 中的完整自定义测试项编辑器（V2）。
- 与真实测试程序对齐（除非用户提供现成清单）。

## 补充说明

- 领域术语以仓库根目录的 `GLOSSARY.md` 为准；测试项目录见 `docs/design/v1-test-item-catalog.md`；关键决策见 `docs/adr/0001-latent-factor-generation-model.md`、`0002-own-stdf-v4-writer.md`、`0003-engine-gui-separation-and-i18n.md`。
- 本 issue 是规范的唯一来源；本地 `docs/design/v1-spec.md` 作为设计附录保留。
- 默认 55nm 目录的典型值与限值是示意值，均可覆盖；若后续拿到真实测试程序，优先对齐。
- 打包方式按用户要求延后；PyInstaller `onedir` 只是首版工作假设，不阻塞前六个里程碑。
- V1 是数据生成器，不是 YMS；ground truth manifest 是验证能力的关键差异点。

<details>
<summary>English</summary>

## Problem Statement

Validating a yield management system (YMS) requires exercising data import, yield/bin analysis, wafer maps and spatial patterns, SPC/Cpk, and WAT↔CP correlation. Real fab data is hard to obtain and carries no known ground truth: there is no way to confirm whether a spatial pattern really exists, what the true correlation between a pair of test items is, or what a die's true bin is. As a result, the YMS's detection and correlation algorithms can only be spot-checked manually; real data also covers only a few scenarios, making it hard to systematically construct center-high/edge-low patterns, random defect clusters, outlier wafers, and other edge cases.

## Solution

SiliconDraft is a scenario-driven synthetic CP/WAT test data generator with both a CLI and a GUI. The user configures wafer geometry, lot/wafer counts, the test item catalog, spatial patterns, and linkage once; the tool outputs reproducible CP/WAT data, CP STDF V4 and CSV, WAT CSV, and a machine-readable ground truth manifest, so an external validation harness can score the YMS's detection and correlation results. V1 covers CP and WAT; FT is planned for V2.

## User Stories

### Scenario and configuration

1. As a yield engineer, I want to define a generation scenario in YAML, so that the scenario is reviewable, versionable, and reproducible.
2. As a yield engineer, I want the scenario to carry a `schema_version`, so that future upgrades can identify old formats unambiguously.
3. As a yield engineer, I want built-in `quick` / `trend` / `demo` presets, so that I can start without writing a full config.
4. As a yield engineer, I want the GUI to save the fully resolved scenario, so that GUI-driven runs are also exactly reproducible.
5. As a yield engineer, I want structural and semantic validation before generation, so that errors surface before compute is spent.
6. As a yield engineer, I want validation to cover die-grid fit, item references, bin-code uniqueness, and linkage references, so that generated data is internally consistent.
7. As a yield engineer, I want to override test items, limits, and distributions on top of a preset, so that the data matches my product.
8. As a yield engineer, I want to set a random seed, so that repeating a scenario produces the same data.
9. As a yield engineer, I want to record product, fab, process node, and notes in the scenario, so that exported files are self-describing.

### Wafer and test structure

10. As a yield engineer, I want to choose 150/200/300 mm wafers, so that the data matches my line.
11. As a yield engineer, I want to configure die size and edge exclusion, so that die counts and wafer maps are realistic.
12. As a yield engineer, I want notch-down, +X-right, +Y-up coordinates, so that wafer maps align with my YMS.
13. As a yield engineer, I want no partial dies, so that yield definitions match production rules.
14. As a yield engineer, I want CP data to carry test-site information, so that I can validate multi-site analysis.
15. As a yield engineer, I want WAT measured only at PCM/TEG sites, so that WAT data reflects real sampling.
16. As a yield engineer, I want configurable WAT site counts (5/9/13/21), so that I can test different sampling densities.
17. As a yield engineer, I want WAT timestamps before CP, so that the timeline matches the real flow.

### Test items and linkage

18. As a yield engineer, I want a built-in 55 nm CMOS logic catalog (15 WAT + 21 CP items), so that the data is usable out of the box with clear business meaning.
19. As a yield engineer, I want every item to carry units, limits, distributions, and a business description, so that the YMS can display and analyze it correctly.
20. As a yield engineer, I want to add/remove/modify items via configuration, so that the data aligns with my test program.
21. As a yield engineer, I want related WAT and CP items to be linked, so that correlation analysis finds real relationships.
22. As a yield engineer, I want to set a target correlation per pair, so that I can validate correlation algorithms at known strengths.
23. As a yield engineer, I want both positive and negative correlations, so that both business directions are covered.
24. As a yield engineer, I want one WAT item to link to multiple CP items, so that shared process factors are represented.
25. As a yield engineer, I want the generation report to show target vs achieved correlations, so that I can confirm the data meets the request.
26. As a yield engineer, I want latent factor values in ground truth, so that I can explain where the correlation comes from.

### Spatial patterns and random defects

27. As a yield engineer, I want to inject center-high / center-low patterns, so that I can validate center-versus-edge yield analysis.
28. As a yield engineer, I want to inject edge-high / edge-low patterns, so that I can validate edge exclusion and spatial analysis.
29. As a yield engineer, I want to inject ring / radial-gradient patterns, so that I can validate radial trend detection.
30. As a yield engineer, I want to inject local-spot patterns, so that I can validate hotspot detection.
31. As a yield engineer, I want patterns to target yield or a selected test item, so that both yield maps and parametric maps can be validated.
32. As a yield engineer, I want patterns scoped to a lot or a single wafer, so that I can simulate systematic and single-wafer excursions.
33. As a yield engineer, I want multiple patterns to overlap, so that the YMS must separate mixed patterns.
34. As a yield engineer, I want random defects with spatial clustering, so that I can validate defect-cluster analysis.
35. As a yield engineer, I want configurable defect density and clustering, so that I can sweep difficulty.
36. As a yield engineer, I want a default total `CP_FUNC` / `CP_SCAN` failure rate of about 1%, so that baseline yield is realistic.
37. As a yield engineer, I want patterns to affect data rather than write bin codes directly, so that bins are always derived and the data stays self-consistent.

### Binning and yield

38. As a yield engineer, I want both hard bins and soft bins, so that yield and failure Pareto analyses both work.
39. As a yield engineer, I want a configurable bin table, so that bin codes match my YMS.
40. As a yield engineer, I want pass/fail derived from spec limits, so that binning agrees with parametric results.
41. As a yield engineer, I want lot/wafer/die yields in ground truth, so that I can check the YMS's calculations.

### Ground truth

42. As a validation engineer, I want a machine-readable ground truth manifest, so that I can automatically evaluate the YMS's detection results.
43. As a validation engineer, I want per-die truth including pass/fail, hard/soft bin, latent factors, and pattern IDs, so that I can join it with YMS results die by die.
44. As a validation engineer, I want target vs achieved correlations in the manifest, so that I can verify the YMS's correlation results.
45. As a validation engineer, I want outlier wafers and the pattern manifest, so that I can compute detection recall.
46. As a validation engineer, I want the full scenario and its SHA-256 in the manifest, so that I can reproduce the experiment.
47. As a validation engineer, I want to disable per-die truth output, so that output size can be reduced.

### Export

48. As a yield engineer, I want CP exported as STDF V4, so that a standard YMS can ingest it directly.
49. As a yield engineer, I want CP exported as wide CSV, so that spreadsheet tools and custom scripts can use it directly.
50. As a yield engineer, I want WAT exported as long CSV, so that sparse site data is represented naturally.
51. As a yield engineer, I want STDF to include MIR/MRR/PCR/HBR/SBR/WIR/WRR/WCR/PIR/PRR/PTR/TSR, so that the files are complete.
52. As a yield engineer, I want file names to include product/lot/phase/timestamp, so that files are easy to identify.
53. As a yield engineer, I want optional split-by-wafer CSV, so that per-wafer ingestion can be tested.
54. As a yield engineer, I want ISO 8601 timestamps and dot decimals, so that parsing is consistent across locales.
55. As a yield engineer, I want UTF-8 without BOM by default with an optional BOM, so that Excel and YMS ingestion both work.
56. As a yield engineer, I want STDF standard missing codes, so that missing values are recognized correctly.

### CLI

57. As a validation engineer, I want a one-command CLI that generates and exports, so that I can run it unattended in CI.
58. As a validation engineer, I want a validate subcommand, so that I can check a scenario without generating.
59. As a validation engineer, I want a schema subcommand, so that I can integrate JSON Schema into tooling.
60. As a validation engineer, I want documented exit codes, so that automation can branch correctly.
61. As a validation engineer, I want `--seed` / `--output` / `--formats` / `--lang` overrides, so that one scenario supports multiple experiments.
62. As a validation engineer, I want English/Chinese CLI messages, so that my team can use it.

### GUI

63. As a yield engineer, I want a single main window with configuration on the left and preview on the right, so that I can iterate quickly.
64. As a yield engineer, I want a wafer map coloured by bin or a selected item, so that I can confirm spatial patterns before export.
65. As a yield engineer, I want distribution histograms, so that I can confirm limits and distributions.
66. As a yield engineer, I want a WAT↔CP scatter plot, so that I can see correlation strength directly.
67. As a yield engineer, I want lot/wafer trends and a data table, so that I can inspect bulk data.
68. As a yield engineer, I want generation to be cancellable with progress, so that long runs are controllable.
69. As a yield engineer, I want an export dialog with format, split-by-wafer, and ground-truth options, so that one run can produce several outputs.
70. As a yield engineer, I want a ground-truth overlay on the wafer map, so that I can compare injected patterns with observations.
71. As a yield engineer, I want the GUI to save/load scenario YAML, so that configs can be shared and reproduced.
72. As a user, I want an English-first UI with a Chinese switch that needs no restart, so that it fits my language.
73. As a user, I want language, window layout, and recent directories remembered, so that repeated use is efficient.
74. As an advanced user, I want a YAML editor in the GUI, so that settings beyond the form can still be edited.

### Quality and developer experience

75. As a validation engineer, I want the same scenario + seed to produce identical data (excluding timestamps), so that tests and comparisons are reliable.
76. As a validation engineer, I want one lot to generate+export in under 60 s and under 2 GB, so that local iteration is practical.
77. As a developer, I want a public Python API for generation and export, so that I can script without the CLI/GUI.
78. As a developer, I want the core engine to be Qt-free, so that it runs in headless environments.
79. As a maintainer, I want STDF output validated by an independent parser, so that interoperability is trustworthy.
80. As a maintainer, I want property tests for geometry and tolerance tests for correlations, so that regressions surface early.
81. As a maintainer, I want CI across Windows/macOS/Ubuntu, so that platform issues surface early.

## Implementation Decisions

1. **Scenario format**: YAML is the single entry point; `schema_version: 1`; sections `product`, `wafer`, `lots`, `items`, `patterns`, `linkage`, `export`, `seed`, `metadata`; JSON Schema plus semantic validation; built-in `quick` / `trend` / `demo` presets; the GUI saves the fully resolved scenario.
2. **Public API**: `load_scenario`, `validate_scenario`, `generate`, `export`; `generate` returns a `GenerationResult` containing the dataset, ground truth, and generation report; CLI and GUI call only the public API.
3. **Engine boundary**: the core engine is pure Python + NumPy with no Qt dependency; CLI and GUI are adapters; pandas is not introduced into the core.
4. **Generation pipeline**: scenario validation → wafer layout → latent factors (lot/wafer/die levels) → WAT site values → CP item values → systematic pattern injection → random defects → binning → ground truth → preview/export; lots are generated and released one at a time.
5. **Wafer geometry**: 150/200/300 mm; defaults 300 mm, 5.0×5.0 mm die, 3 mm edge exclusion; notch down, +X right, +Y up; internal mm, STDF grid indices, CSV both; no partial dies; 4 CP sites; 9 WAT sites (centre + 4 at 0.5R + 4 at 0.9R).
6. **Test item catalog**: default `generic_cmos_logic_55nm` (15 WAT + 21 CP), each with `test_num`, canonical English ID, unit, LSL/USL, distribution, and business description; `items.overrides` can add/remove/modify; exports use English IDs only.
7. **Latent factors**: `F_VT`, `F_MOB`, `F_TOX`, `F_RC`, `F_LEAK`, `F_SC`; lot/wafer/die components plus measurement noise; sensitivity matrix; target-r calibration with absolute error ≤ 0.05 for target r ≥ 0.5, otherwise ≤ 0.08; the report states achieved r.
8. **Spatial patterns**: `center-high`, `center-low`, `edge-high`, `edge-low`, `ring`, `radial-gradient`, `local-spot`; target yield or a selected item; scope lot or wafer; amplitude and spatial extent parameters; composable; never write bin codes directly.
9. **Random defects**: negative-binomial/clustered model by default, Poisson configurable; parameters are defect density and clustering strength; default `CP_FUNC`/`CP_SCAN` total failure rate 1%; defect results enter ground truth.
10. **Binning**: default hard bins 1=pass, 2=parametric fail, 3=functional/structural fail, 4=continuity/contact fail; default soft bins 100=pass, 201=continuity, 202=leakage, 203=Iddq, 204=Vth, 205=frequency, 206=functional/scan, 207=other parametric; bin table configurable; pass/fail derived from spec limits; STDF HBR/SBR, CSV has both columns.
11. **Ground truth**: JSON summary (engine version, full scenario + SHA-256, seed, generation time, product, lot/wafer summary, per-wafer yield, latent means, pattern manifest, target/achieved r, outlier wafers, die-truth file names) plus per-die CSV.GZ (coordinates, site, true pass/bin, latent factors, pattern IDs); `--no-die-truth` disables per-die truth.
12. **Export**: one STDF V4 per CP lot (MIR/MRR/PCR/HBR/SBR/WIR/WRR/WCR/PIR/PRR/PTR/TSR) plus one wide CSV; one long CSV per WAT lot; naming `{product}_{lot}_{phase}_{timestamp}.{ext}`; UTF-8 without BOM by default; ISO 8601 timestamps; dot decimals; standard STDF missing codes; `--split-by-wafer` splits CSV.
13. **CLI**: `generate` / `validate` / `schema` / `version`; flags `--seed`, `--output`, `--formats`, `--split-by-wafer`, `--lang`, `--log-level`, `--dry-run`, `--overwrite`, `--no-die-truth`; exit codes 0 success, 1 configuration error, 2 generation error, 3 export error; YAML is the only entry point; no fully flag-driven scenario assembly.
14. **GUI**: single main window; scenario tree on the left; Wafer Map / Distribution / Correlation / Trend / Table tabs on the right; Generate runs in a worker thread with progress and cancel; Export dialog can override formats and split options; wafer map supports ground-truth overlay; scenario save/load and YAML editor; remembers language, layout, and recent directories.
15. **Internationalization**: `en` default, `zh_CN` switchable; GUI uses Qt `.ts/.qm`, CLI/engine use gettext; stable shared error codes; logs stay English; item IDs, bin names, and column names in exports stay English; ISO 8601 dates and dot decimals; repository docs Chinese-first with a collapsed English version.
16. **Dependencies and platforms**: Python 3.13; core dependencies `numpy`, `PyYAML`; GUI dependencies `PySide6-Essentials`, `pyqtgraph`; test dependencies `pytest`, `hypothesis`, `pytest-qt`, `pystdf` (GPL-2.0, test-only), optional `stdfast`; Windows 11 and macOS 14+ officially supported, Linux best-effort.
17. **License and packaging**: project is MIT; avoid GPLv3-only modules such as QtCharts/QtGraphs/QtDataVisualization; link PySide6 dynamically and ship LGPL texts and notices; first release assumes PyInstaller `onedir`; the final packaging choice is deferred.
18. **Reproducibility**: `seed` is required; random streams derive per lot/wafer/item; the manifest records the scenario hash; the same scenario + seed is identical except timestamps.
19. **Performance**: one lot generation+export under 60 s and under 2 GB; streaming STDF writer; downsampled preview.
20. **Test seams**: the public API is the only primary seam; one CLI subprocess smoke test and one GUI pytest-qt smoke test; internal modules have no separate seams.

## Testing Decisions

- **What makes a good test**: assert only externally observable behaviour, not implementation details; construct a scenario and call `generate` / `export` through the public API, then assert on the dataset, ground truth, and exported files; use a fixed seed for determinism; use tolerances and directional assertions for statistics rather than exact floating-point equality.
- **Primary seam**: the public engine API (`load_scenario` / `validate_scenario` / `generate` / `export`). All domain and export tests go through it, covering scenario validation, wafer geometry, catalog, latent/correlation, patterns, random defects, binning, ground truth, CSV, and STDF export.
- **Secondary smoke seams**: CLI runs `generate` via subprocess with a small scenario and asserts exit code, output files, and a parseable STDF; GUI runs one pytest-qt configure → generate → preview → export flow and asserts window state and exported files. Neither duplicates domain tests.
- **Property tests**: Hypothesis covers die count, non-overlap, edge exclusion, and scenario-validation invariants.
- **Correlation tests**: achieved error ≤ 0.05 for target r ≥ 0.5, otherwise ≤ 0.08; also assert the sign.
- **Pattern tests**: injected direction and amplitude are detectable, and ground truth matches the injection parameters.
- **STDF tests**: `pystdf` parses generated files and cross-checks record counts and key field values; `stdfast` is an optional second oracle.
- **Golden tests**: semantic CSV/STDF comparison ignoring timestamps; no byte-level comparison.
- **CI**: GitHub Actions, Ubuntu + macOS + Windows, Python 3.13; ruff + mypy strict + pytest.
- **Prior art**: the repository has no code or tests yet; this spec's tests establish the pattern for later modules.
- **Fixtures**: a tiny scenario (1 wafer, small die grid) for fast tests; `quick` and `demo` presets for integration tests.

## Out of Scope

- FT data, FT test items, and CP→FT unit traceability (V2).
- Importing real test data; implementing YMS analysis or scoring; database, server, network upload, multi-user.
- Reticle-field-level spatial patterns, die rotation, flat orientation.
- macOS below 14; Linux beyond best-effort.
- The final packaging choice (PyInstaller vs Nuitka).
- A full custom test-item editor in the GUI (V2).
- Alignment with a real test program (unless the user provides one).

## Further Notes

- Domain terms follow `GLOSSARY.md`; the test item catalog is in `docs/design/v1-test-item-catalog.md`; key decisions are in `docs/adr/0001-latent-factor-generation-model.md`, `0002-own-stdf-v4-writer.md`, and `0003-engine-gui-separation-and-i18n.md`.
- This issue is the canonical specification; the local `docs/design/v1-spec.md` remains as a design appendix.
- The default 55 nm catalog's typical values and limits are illustrative and overridable; if a real test program becomes available, align to it first.
- Packaging is deferred at the user's request; PyInstaller `onedir` is only a first-release working assumption and does not block the first six milestones.
- V1 is a data generator, not a YMS; the ground truth manifest is the key differentiator for validation.

</details>

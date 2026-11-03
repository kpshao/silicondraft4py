# SiliconDraft 领域词汇表

SiliconDraft 生成可复现的合成 CP 与 WAT 测试数据（FT 计划于 V2 支持），用于验证良率管理系统的数据导入、良率/bin 分析、wafer map、SPC 与相关性分析等功能。

## 语言

### 对象与阶段

**Wafer（晶圆）**：
一片半导体衬底，上面分布着多个 die；是空间模式与 wafer 级统计的基本单位。
_Avoid_：片子、圆片

**Die（晶粒）**：
晶圆上单个未封装的集成电路；CP 测试与良率统计的基本单位。
_Avoid_：chip、芯片（在指代封装前对象时）

**Lot（批次）**：
一起经过同一工艺、共享同一 lot ID 的一组 wafer；是 wafer 间趋势与 wafer 级相关性的上层分组。
_Avoid_：batch、批号

**CP（Circuit Probe，晶圆测试）**：
封装前对晶圆上每颗 die 进行的电性测试；每颗 die 产生一条测试结果。
_Avoid_：wafer sort、probe test

**WAT（Wafer Acceptance Test，晶圆允收测试）**：
通过 scribe line 中的 PCM/TEG 结构监测工艺的电性测试；每片 wafer 只在少量站点测量，不按 die 测量。
_Avoid_：PCM 测试（PCM 是结构，不是测试阶段）

**PCM/TEG（Process Control Monitor / Test Element Group，工艺监控结构）**：
放置在 scribe line 中、用于 WAT 测量的测试结构。
_Avoid_：test key、测试键

**FT（Final Test，成品测试）**：
封装后对单颗成品进行的电性测试；V1 不生成，计划于 V2 支持。
_Avoid_：终测

**YMS（Yield Management System，良率管理系统）**：
SiliconDraft 的验证对象；消费 CP/WAT 数据并提供良率、bin、空间模式、SPC 与相关性分析。
_Avoid_：良率系统

### 测试与数据

**Test item（测试项）**：
一个具名的电性测量，具有单位、规格上下限和明确业务含义，属于某个测试阶段（V1：CP 或 WAT）。
_Avoid_：test parameter、测试参数（在指代定义本身时）

**Unit（单位）**：
测试项测量的物理单位；导出时使用 ASCII SI 记法（如 `uA`、`um`、`ohm/sq`、`A/cm2`、`angstrom`），不使用 `µ`、`Ω`、`Å`、`²` 等非 ASCII 符号。
_Avoid_：SI 排版符号（`µA`、`Ω`、`Å`）

**Test item catalog（测试项目录）**：
可用的 CP/WAT 测试项集合，每项带单位、规格限与业务含义；场景从中选择并可按需覆盖。
_Avoid_：test program（见 Test program；测试程序是完整的测试流程，不只是项目录）

**Test program（测试程序）**：
一次生成运行所使用的完整、具名的测试流程/程序，对应 STDF MIR 的 `JOB_NAM`；它规定测试项的选择与顺序，区别于只描述可选测试项集合的 Test item catalog。
_Avoid_：用 test program 指代 Test item catalog

**Scenario（场景）**：
一次生成运行的完整、可复现配置：产品、wafer 几何、lot、测试项、空间模式、联动关系、导出选项与随机种子。
_Avoid_：config file（文件是场景的载体，不是概念本身）

**Scenario preset（场景预设）**：
一组命名的 scenario 默认片段（`quick`、`trend`、`demo`），在加载时深合并到显式 YAML 之下；标量与映射可被覆盖，列表整体替换。
_Avoid_：template file、config preset

**Systematic spatial pattern（系统性空间模式）**：
在 wafer 上呈现确定性、空间连续分布的良率或测试项偏移，如 center-high、edge-low、ring；由生成器主动注入，区别于随机缺陷。
_Avoid_：defect pattern、缺陷（在指代该类模式时）

**Random defect（随机缺陷）**：
由颗粒或工艺缺陷导致的、位置随机且带空间聚集性的单 die 失效；区别于系统性空间模式。
_Avoid_：缺陷特征（语义模糊）

**Defect cluster（缺陷簇）**：
在空间上聚集的一组随机缺陷失效 die，由簇心、半径与成员 die 描述；其位置进入 ground truth。
_Avoid_：defect blob

**Latent process factor（潜在工艺因子）**：
一个不可直接观测的工艺特性（如阈值电压、迁移率、接触电阻），被 WAT 与 CP 测量项共同反映；它是跨阶段联动的共同原因。
_Avoid_：hidden variable、共享变量

**Linkage（联动）**：
相关测试项在不同测试阶段之间呈现的统计依赖（V1：WAT↔CP）；由共享潜在工艺因子产生，而不是直接给相关系数赋值。
_Avoid_：correlation（correlation 是可观测结果，不是生成关系）

**Achieved correlation（达成相关系数）**：
标定后的 latent 模型对一对 WAT↔CP 测试项隐含的总体 Pearson 相关系数；生成报告据此对照目标 r 与容差。
_Avoid_：target correlation（那是配置输入）

**Observed correlation（观测相关系数）**：
按 WAT 站点与最近 die 配对、从一次生成的数据中计算的样本 Pearson 相关系数；随 wafer 与站点数波动。
_Avoid_：actual correlation（语义模糊）

**Ground truth manifest（真值清单）**：
生成器输出的机器可读记录，描述其注入的意图真相：空间模式、潜在因子、目标相关系数与每颗 die 的真实 pass/fail；用于评估 YMS 的检测与相关性结果。
_Avoid_：report、结果报告（过于宽泛）

**Pattern ID（模式标识）**：
ground truth 中注入模式的稳定标识（`pattern_1`、`pattern_2`…），用于把每 die 真值与模式清单 join；同一 die 命中多个模式时以 `|` 分隔。
_Avoid_：pattern name

**Outlier wafer（异常 wafer）**：
被 wafer 级（`scope: wafer`）空间模式选中的单张异常 wafer；manifest 记录其 lot/wafer 与命中的模式。
_Avoid_：bad wafer

**Wafer map（晶圆图）**：
把 die 级结果按 wafer 坐标进行的空间可视化。
_Avoid_：wafer chart、wafer 图

**STDF（Standard Test Data Format）**：
半导体测试数据的二进制标准格式；本项目按 STDF V4 导出 CP 数据。
_Avoid_：STDF5、STDF V5

### Wafer 几何与 CP 结果

**Hard bin（硬 bin）**：
记录给每颗 die 的最终 pass/fail 类别，用于良率计算。
_Avoid_：bin（单独使用时有歧义）

**Soft bin（软 bin）**：
记录给每颗 die 的细粒度失效类别，并映射到一个 hard bin。
_Avoid_：sub-bin

**Test site（测试站点）**：
多站点并测时实际测试某颗 die 的探针卡站点编号；一颗 die 只属于一个 site。
_Avoid_：site（单独使用时有歧义）

**Edge exclusion（边缘排除）**：
wafer 边缘不生成、不测试 die 的环状区域，以距 wafer 边缘的距离定义。
_Avoid_：edge ring

**Grid index（网格索引）**：
STDF PRR 中 X_COORD/Y_COORD 使用的整数 die 坐标，相对 wafer 网格原点。
_Avoid_：die coordinate（与以 mm 表示的 die 中心坐标混淆）

<details>
<summary>English</summary>

# SiliconDraft Domain Glossary

SiliconDraft generates reproducible synthetic CP and WAT test data (FT is planned for V2) to validate yield management system functions such as data import, yield/bin analysis, wafer maps, SPC, and correlation analysis.

## Language

### Objects and phases

**Wafer**:
A semiconductor substrate carrying multiple dies; the basic unit for spatial patterns and wafer-level statistics.
_Avoid_: slice, disc

**Die**:
A single unpackaged integrated circuit on a wafer; the basic unit for CP testing and yield statistics.
_Avoid_: chip (when referring to the pre-package object)

**Lot**:
A group of wafers processed together and sharing a lot ID; the grouping level above wafers for trend and wafer-level correlation analysis.
_Avoid_: batch

**CP (Circuit Probe)**:
Electrical test of every die on a wafer before packaging; each die produces one test result.
_Avoid_: wafer sort, probe test

**WAT (Wafer Acceptance Test)**:
Electrical measurements on PCM/TEG structures to monitor the process; measured at a small number of sites per wafer, not per die.
_Avoid_: PCM test (PCM is a structure, not a test phase)

**PCM/TEG (Process Control Monitor / Test Element Group)**:
Test structures placed in scribe lines for WAT measurements.
_Avoid_: test key

**FT (Final Test)**:
Electrical test of a packaged unit after assembly; not generated in V1, planned for V2.
_Avoid_: final electrical test

**YMS (Yield Management System)**:
The system under validation; consumes CP/WAT data and provides yield, bin, spatial-pattern, SPC, and correlation analysis.
_Avoid_: yield system

### Test and data

**Test item**:
A named electrical measurement with a unit, spec limits, and explicit business meaning, belonging to a test phase (CP or WAT in V1).
_Avoid_: test parameter (when referring to the definition itself)

**Unit**:
The physical unit of a test-item measurement; exports use ASCII SI notation (e.g. `uA`, `um`, `ohm/sq`, `A/cm2`, `angstrom`) rather than non-ASCII symbols such as `µ`, `Ω`, `Å`, and `²`.
_Avoid_: typographic SI symbols (`µA`, `Ω`, `Å`)

**Test item catalog**:
The set of available CP/WAT test items, each with a unit, spec limits, and business meaning; a scenario selects from it and may override entries.
_Avoid_: test program (see Test program; a test program is a complete test flow, not just a catalog)

**Test program**:
The complete, named test flow/program used for one generation run, corresponding to `JOB_NAM` in STDF MIR; it defines the selection and order of test items and is distinct from the Test item catalog, which only describes the available items.
_Avoid_: using "test program" for the Test item catalog

**Scenario**:
A complete, reproducible configuration for one generation run: product, wafer geometry, lots, test items, spatial patterns, linkage, export options, and random seed.
_Avoid_: config file (the file carries the scenario; it is not the concept)

**Scenario preset**:
A named fragment of scenario defaults (`quick`, `trend`, `demo`) deep-merged under an explicit YAML document at load time; scalars and mappings may be overridden, while lists replace wholesale.
_Avoid_: template file, config preset

**Systematic spatial pattern**:
A deterministic, spatially continuous deviation in yield or test-item values across a wafer, such as center-high, edge-low, or ring; deliberately injected and distinct from a random defect.
_Avoid_: defect pattern, defect (when referring to this class of pattern)

**Random defect**:
A die failure caused by particles or process defects, located stochastically and spatially clustered; distinct from a systematic spatial pattern.
_Avoid_: defect feature (ambiguous)

**Defect cluster**:
A spatially concentrated group of random-defect failure dies, described by a centre, radius, and member dies; its locations enter ground truth.
_Avoid_: defect blob

**Latent process factor**:
An unobserved process characteristic (e.g., threshold voltage, mobility, contact resistance) reflected jointly by WAT and CP measurements; the common cause of cross-stage linkage.
_Avoid_: hidden variable, shared variable

**Linkage**:
The statistical dependence between related test items across test phases (WAT↔CP in V1), produced by shared latent process factors rather than by directly assigning correlation coefficients.
_Avoid_: correlation (correlation is an observed result, not the generative relationship)

**Achieved correlation**:
The population Pearson correlation implied by the calibrated latent model for a WAT↔CP item pair; the generation report compares it with the target r and tolerance.
_Avoid_: target correlation (that is the configuration input)

**Observed correlation**:
The sample Pearson correlation computed from one generation run's data, pairing WAT sites with their nearest die; it fluctuates with the wafer and site counts.
_Avoid_: actual correlation (ambiguous)

**Ground truth manifest**:
A machine-readable record of the generator's intended truths — injected spatial patterns, latent factors, target correlations, and per-die pass/fail — used to evaluate a YMS's detection and correlation results.
_Avoid_: report (too broad)

**Pattern ID**:
A stable identifier for an injected spatial pattern in ground truth (`pattern_1`, `pattern_2`, …), used to join per-die truth to the pattern manifest; multiple hits on one die are separated by `|`.
_Avoid_: pattern name

**Outlier wafer**:
The single excursion wafer selected by a wafer-scoped (`scope: wafer`) spatial pattern; the manifest records its lot/wafer and the patterns that hit it.
_Avoid_: bad wafer

**Wafer map**:
A spatial visualization of die-level results on a wafer.
_Avoid_: wafer chart

**STDF (Standard Test Data Format)**:
The binary standard format for semiconductor test data; this project exports CP data as STDF V4.
_Avoid_: STDF5, STDF V5

### Wafer geometry and CP results

**Hard bin**:
The final pass/fail category recorded for a die and used for yield calculation.
_Avoid_: bin (ambiguous on its own)

**Soft bin**:
The detailed failure category recorded for a die and mapped to a hard bin.
_Avoid_: sub-bin

**Test site**:
The probe-card site index that tested a die in multi-site probing; each die belongs to exactly one site.
_Avoid_: site (ambiguous on its own)

**Edge exclusion**:
The annular region at the wafer edge where dies are neither generated nor tested, defined by a distance from the wafer edge.
_Avoid_: edge ring

**Grid index**:
Integer die coordinates used by STDF PRR X_COORD/Y_COORD, relative to the wafer grid origin.
_Avoid_: die coordinate (confused with die-centre coordinates in millimetres)

</details>

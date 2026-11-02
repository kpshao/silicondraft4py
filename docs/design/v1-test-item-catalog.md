# SiliconDraft V1 测试项目录（草案）

> 状态：已确认作为 V1 默认预设（2026-11-02）。默认预设为通用 55nm CMOS 逻辑工艺；典型值与规格限均可在 scenario 中覆盖；若后续有真实测试程序清单，以其为准。

## 1. 约定

- **阶段**：WAT 在 PCM 站点测量（默认每片 9 点）；CP 对每颗 die 测量。
- **规范标识**：导出文件中的测试项 ID 一律使用英文，不随 UI 语言变化；中文名称仅用于文档与界面显示。
- **规格限**：`LSL` / `USL` 为规格上下限；单边测试用 `—` 表示不适用。
- **分布**：`normal`、`lognormal`、`bernoulli`。漏电类项在对数域生成，天然为正值且右偏。
- **默认测试条件**：25 °C；core VDD 1.2 V，IO VDD 1.8 V。
- **测试号**：WAT 1001–1015，CP 2001–2021；用于 STDF PTR 的 `TEST_NUM`。

## 2. WAT 测试项（15 项）

| TEST_NUM | ID | 业务含义 | 单位 | 典型值 | LSL | USL | 分布 |
|---:|---|---|---|---:|---:|---:|---|
| 1001 | `WAT_VTN` | NMOS 饱和区阈值电压；反映沟道掺杂与栅控能力 | V | 0.35 | 0.28 | 0.42 | normal |
| 1002 | `WAT_VTP` | PMOS 饱和区阈值电压（带符号） | V | -0.35 | -0.42 | -0.28 | normal |
| 1003 | `WAT_IDSATN` | NMOS 饱和驱动电流；反映迁移率、CD 与 Vt | µA/µm | 550 | 480 | 620 | normal |
| 1004 | `WAT_IDSATP` | PMOS 饱和驱动电流 | µA/µm | 250 | 210 | 290 | normal |
| 1005 | `WAT_IOFFN` | NMOS 关态漏电 | pA/µm | 100 | — | 1000 | lognormal |
| 1006 | `WAT_IOFFP` | PMOS 关态漏电 | pA/µm | 10 | — | 500 | lognormal |
| 1007 | `WAT_SS` | 亚阈值摆幅；反映界面态与栅控能力 | mV/dec | 85 | — | 100 | normal |
| 1008 | `WAT_DIBL` | 漏致势垒降低；短沟道效应指标 | mV/V | 80 | — | 120 | normal |
| 1009 | `WAT_TOX` | 等效栅氧厚度 | Å | 22 | 21 | 23 | normal |
| 1010 | `WAT_RSHN` | N+ 扩散层方块电阻 | Ω/sq | 8 | 6 | 10 | normal |
| 1011 | `WAT_RSHP` | P+ 扩散层方块电阻 | Ω/sq | 12 | 9 | 15 | normal |
| 1012 | `WAT_RC` | 接触电阻（单个接触） | Ω | 15 | 8 | 25 | normal |
| 1013 | `WAT_RVIA` | 通孔电阻 | Ω | 3 | 1.5 | 5 | normal |
| 1014 | `WAT_IGATE` | 栅漏电流密度 | A/cm² | 1e-3 | — | 1e-2 | lognormal |
| 1015 | `WAT_VBD` | 栅氧击穿电压 | V | 5.0 | 4.0 | — | normal |

## 3. CP 测试项（21 项）

| TEST_NUM | ID | 业务含义 | 单位 | 典型值 | LSL | USL | 分布 |
|---:|---|---|---|---:|---:|---:|---|
| 2001 | `CP_CONT` | 开短路/连续性；引脚间连通电阻，过高判 fail | Ω | 5 | — | 100 | normal |
| 2002 | `CP_FUNC` | 功能测试；1=pass，0=fail | — | 1 | — | — | bernoulli |
| 2003 | `CP_SCAN` | 扫描链测试；1=pass，0=fail | — | 1 | — | — | bernoulli |
| 2004 | `CP_IDDQ` | 静态电源电流；反映漏电与缺陷 | µA | 2 | — | 50 | lognormal |
| 2005 | `CP_VTHN` | NMOS 阈值电压 | V | 0.35 | 0.28 | 0.42 | normal |
| 2006 | `CP_VTHP` | PMOS 阈值电压 | V | -0.35 | -0.42 | -0.28 | normal |
| 2007 | `CP_IONN` | NMOS 驱动电流 | µA | 600 | 500 | — | normal |
| 2008 | `CP_IONP` | PMOS 驱动电流 | µA | 250 | 200 | — | normal |
| 2009 | `CP_IOFFN` | NMOS 关态电流 | nA | 1 | — | 50 | lognormal |
| 2010 | `CP_IOFFP` | PMOS 关态电流 | nA | 0.5 | — | 20 | lognormal |
| 2011 | `CP_IGATE` | 栅漏电流 | nA | 5 | — | 100 | lognormal |
| 2012 | `CP_IIL` | 输入低电平漏电流 | µA | 0.01 | — | 1 | lognormal |
| 2013 | `CP_IIH` | 输入高电平漏电流 | µA | 0.01 | — | 1 | lognormal |
| 2014 | `CP_IOZ` | 输出三态漏电流 | µA | 0.05 | — | 5 | lognormal |
| 2015 | `CP_VIL` | 输入低电平上限 | V | 0.35 | — | 0.54 | normal |
| 2016 | `CP_VIH` | 输入高电平下限 | V | 1.50 | 1.26 | — | normal |
| 2017 | `CP_VOL` | 输出低电平 | V | 0.20 | — | 0.40 | normal |
| 2018 | `CP_VOH` | 输出高电平 | V | 1.60 | 1.40 | — | normal |
| 2019 | `CP_FRO` | 环形振荡器频率；速度代理 | MHz | 800 | 700 | 900 | normal |
| 2020 | `CP_RCONT` | 接触电阻 | Ω | 15 | — | 30 | normal |
| 2021 | `CP_VDDMIN` | 最低工作电压；越低越好 | V | 0.90 | — | 1.00 | normal |

### 3.1 CP soft bin 归类

失败项的 soft bin 归类如下；未列出的项归入 207 other parametric。自定义 CP 项按分布归类：`bernoulli` 归 206 functional/scan，其余归 207。

| soft bin | 名称 | 测试项 |
|---:|---|---|
| 201 | continuity | `CP_CONT`、`CP_RCONT` |
| 202 | leakage | `CP_IOFFN`、`CP_IOFFP`、`CP_IGATE`、`CP_IIL`、`CP_IIH`、`CP_IOZ` |
| 203 | Iddq | `CP_IDDQ` |
| 204 | Vth | `CP_VTHN`、`CP_VTHP` |
| 205 | frequency | `CP_FRO` |
| 206 | functional/scan | `CP_FUNC`、`CP_SCAN` |
| 207 | other parametric | `CP_IONN`、`CP_IONP`、`CP_VIL`、`CP_VIH`、`CP_VOL`、`CP_VOH`、`CP_VDDMIN` 及其余自定义项 |

hard bin 映射：100 → 1 pass；201 → 4 continuity/contact；206 → 3 functional/structural；202/203/204/205/207 → 2 parametric。一颗 die 同时有多个失败项时，按 hard bin 严重度（continuity → functional → parametric），再按 soft bin 号（202 → 203 → 204 → 205 → 207）选取。

## 4. 默认 WAT↔CP 联动表

目标相关系数为默认值，可在 scenario 中逐对覆盖；生成报告会输出实际达成值。

| WAT | CP | 预期符号 | 目标 r | 说明 |
|---|---|---|---:|---|
| `WAT_VTN` | `CP_VTHN` | + | 0.80 | 同一阈值电压因子 |
| `WAT_VTN` | `CP_IDDQ` | − | 0.50 | Vt 越高，静态漏电越低 |
| `WAT_VTN` | `CP_FRO` | − | 0.45 | Vt 越高，速度越低 |
| `WAT_VTP` | `CP_VTHP` | + | 0.80 | 同一阈值电压因子 |
| `WAT_VTP` | `CP_IDDQ` | − | 0.45 | 同上 |
| `WAT_VTP` | `CP_FRO` | − | 0.40 | 同上 |
| `WAT_IDSATN` | `CP_IONN` | + | 0.75 | 同一迁移率/驱动因子 |
| `WAT_IDSATN` | `CP_FRO` | + | 0.60 | 驱动电流越高，速度越快 |
| `WAT_IDSATP` | `CP_IONP` | + | 0.75 | 同上 |
| `WAT_IDSATP` | `CP_FRO` | + | 0.55 | 同上 |
| `WAT_IOFFN` | `CP_IOFFN` | + | 0.70 | 同一漏电因子 |
| `WAT_IOFFN` | `CP_IDDQ` | + | 0.55 | 同上 |
| `WAT_IOFFP` | `CP_IOFFP` | + | 0.70 | 同上 |
| `WAT_IOFFP` | `CP_IDDQ` | + | 0.50 | 同上 |
| `WAT_SS` | `CP_IOFFN` | + | 0.50 | 栅控变差，漏电上升 |
| `WAT_SS` | `CP_VDDMIN` | + | 0.45 | 栅控变差，最低工作电压上升 |
| `WAT_DIBL` | `CP_IOFFN` | + | 0.55 | 短沟道效应加剧漏电 |
| `WAT_DIBL` | `CP_VDDMIN` | + | 0.45 | 同上 |
| `WAT_TOX` | `CP_IGATE` | − | 0.60 | 栅氧越厚，栅漏越小 |
| `WAT_TOX` | `CP_VTHN` | + | 0.40 | 栅氧越厚，Vt 越高 |
| `WAT_TOX` | `CP_FRO` | − | 0.40 | 栅氧越厚，速度越低 |
| `WAT_RSHN` | `CP_RCONT` | + | 0.50 | 扩散层电阻与接触电阻同源 |
| `WAT_RSHP` | `CP_RCONT` | + | 0.50 | 同上 |
| `WAT_RC` | `CP_RCONT` | + | 0.70 | 同一接触电阻因子 |
| `WAT_RC` | `CP_CONT` | + | 0.50 | 接触电阻高，连续性电阻高 |
| `WAT_RVIA` | `CP_CONT` | + | 0.45 | 通孔电阻高，连续性电阻高 |
| `WAT_IGATE` | `CP_IGATE` | + | 0.65 | 同一栅漏因子 |
| `WAT_VBD` | `CP_IGATE` | − | 0.45 | 击穿电压低，栅漏大 |

## 5. 非联动项与随机性

- `CP_FUNC`、`CP_SCAN` 由随机缺陷和系统性空间模式驱动，不由 latent factor 直接驱动；默认总失败率 1%，可在 scenario 覆盖。
- `CP_IIL`、`CP_IIH`、`CP_IOZ`、`CP_VIL`、`CP_VIH`、`CP_VOL`、`CP_VOH` 以独立测试噪声和规格边界为主，弱关联工艺因子；如后续需要，可补充弱联动。
- 所有项都保留测量噪声；相关性校准只调整共享因子的载荷，不伪造不可能的强相关。

## 6. 设计草案：latent factor

默认六个共享因子，作用于 WAT 与 CP 的相关项：

| 因子 | 含义 | 主要载荷项 |
|---|---|---|
| `F_VT` | 阈值电压/沟道掺杂 | `WAT_VTN/VTP`、`CP_VTHN/VTHP`、`CP_IDDQ`、`CP_FRO` |
| `F_MOB` | 迁移率/驱动能力 | `WAT_IDSATN/IDSATP`、`CP_IONN/IONP`、`CP_FRO` |
| `F_TOX` | 栅氧厚度 | `WAT_TOX`、`CP_IGATE`、`CP_VTHN/VTHP`、`CP_FRO` |
| `F_RC` | 接触/通孔电阻 | `WAT_RC/RVIA/RSHN/RSHP`、`CP_RCONT/CONT` |
| `F_LEAK` | 结漏电/栅漏电 | `WAT_IOFFN/IOFFP/IGATE`、`CP_IOFFN/IOFFP/IGATE/IDDQ` |
| `F_SC` | 短沟道效应 | `WAT_SS/DIBL`、`CP_IOFFN/IOFFP/VDDMIN` |

## 7. 后续可调项（不阻塞 V1 开工）

1. 测试项集合是否覆盖你的验证场景？需要补充/删除哪些项（例如 MIM 电容、well 方块电阻、poly CD、SRAM Vmin）？
2. 默认值/规格限是否合理？是否需要改为 28nm 或其他工艺预设？
3. 默认联动对的符号与目标相关系数是否符合你的领域经验？
4. 功能/扫描测试的默认失败率目标（例如 0.5%–2%）是否合适？

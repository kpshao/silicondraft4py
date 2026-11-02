# 用 latent factor 因果模型生成 WAT↔CP 联动

**Status:** accepted (2026-11-02)

WAT 与 CP 的相关测试项需要呈现可解释、可控的相关性，以支持 wafer 级和 die 级分析。我们决定用共享的 latent process factor（`F_VT`、`F_MOB`、`F_TOX`、`F_RC`、`F_LEAK`、`F_SC`）驱动 WAT 与 CP 测量值，通过灵敏度矩阵与测量噪声产生相关性；目标相关系数作为校准输入，生成报告输出实际达成值。没有采用直接为每对测试项赋相关系数的方式，因为它无法保证符号、量级与跨项一致性；也没有采用 SPICE/器件级仿真，因为超出 V1 范围。

<details>
<summary>English</summary>

# Generate WAT↔CP linkage with a latent-factor causal model

**Status:** accepted (2026-11-02)

Related WAT and CP test items must show explainable, controllable correlation to support wafer-level and die-level analysis. We use shared latent process factors (`F_VT`, `F_MOB`, `F_TOX`, `F_RC`, `F_LEAK`, `F_SC`) to drive WAT and CP measurements, producing correlation through a sensitivity matrix and measurement noise. Target correlations are calibration inputs, and the generation report states the achieved values. We rejected assigning a correlation coefficient to each item pair directly because it cannot guarantee sign, magnitude, and cross-item consistency; we rejected SPICE/device-level simulation as out of scope for V1.

</details>

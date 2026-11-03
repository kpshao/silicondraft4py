# WAT 站点按最近 die 配对，并分别报告模型达成 r 与样本观测 r

**Status:** accepted (2026-11-03)

WAT 只在少量 PCM 站点测量，CP 对每颗 die 测量；两者要呈现目标相关性，必须先定义“哪两个观测配对”。我们决定让每个 WAT 站点采样其**最近 CP die** 的 latent factor 向量（按 die 中心欧氏距离，平局取布局顺序最早的 die），并据此计算 WAT↔CP 相关。因子仍按 lot/wafer/die 三层标准化分量合成（权重 0.25/0.25/约 0.935）；同一配对同时共享三层分量，因此分解权重不影响模型相关性。

生成报告为每对 WAT↔CP 输出三个值：`target_r` 是配置目标；`achieved_r` 是标定后模型隐含的总体 Pearson 相关，先按 lognormal 边缘分布把目标映射到 latent 空间，再用交替最小二乘拟合 WAT communality 与 CP 灵敏度，最后解析换算回原始尺度；`observed_r` 是按上述配对对本次生成数据计算的样本 Pearson 相关，`sample_count` 为配对数。容差（目标 r ≥ 0.5 时绝对误差 ≤ 0.05，否则 ≤ 0.08）针对 `achieved_r`；`observed_r` 随 wafer 数与站点数波动，小场景不应据此判定失败。

**考虑的其他方案**

- WAT 站点独立抽取 die 分量：会衰减可达相关性，需要在标定中额外补偿。
- 按 wafer 均值配对 WAT 与 CP：样本数等于 wafer 数，小场景下噪声过大。
- 为每对单独设置 latent factor：ADR-0001 已拒绝，因为无法保证跨项一致性。

**后果**

- 小规模生成（例如 1 lot × 1 wafer）的 `observed_r` 可能远离目标；这是抽样噪声，`achieved_r` 仍是标定契约。
- 默认 1 lot × 25 wafers × 9 sites 只有 225 个配对，`±0.05` 的样本误差在此规模下统计上不可达；要按 spec 容差检查生成数据本身，请使用至少 10 lots × 25 wafers × 21 sites（本仓库的相关性测试即用此规模）。
- YMS 的相关性分析需要足够多的 wafer，估计值才会接近报告的达成值。
- 最近 die 配对是建模简化：PCM 结构位于 scribe line，最近 die 只是局部工艺条件的代理。

<details>
<summary>English</summary>

# Pair WAT sites with their nearest die and report model-achieved and sample-observed r separately

**Status:** accepted (2026-11-03)

WAT is measured at a few PCM sites while CP measures every die, so a target correlation first needs a definition of which observations pair. We let each WAT site sample the latent factor vector of its **nearest CP die** (Euclidean distance between centres, ties broken by layout order) and compute WAT↔CP correlation on those pairs. Factors still combine standardized lot/wafer/die components (weights 0.25/0.25/about 0.935); a pair shares all three components, so the decomposition weights do not affect the model-implied correlation.

For every WAT↔CP pair the generation report exposes three values. `target_r` is the configured target. `achieved_r` is the population Pearson correlation implied by the calibrated model: the target is mapped into latent space through the lognormal marginals, WAT communalities and CP sensitivities are fitted by alternating least squares, and the result is mapped back to the raw scale analytically. `observed_r` is the sample Pearson correlation over this run's generated values under the pairing above, with `sample_count` reporting the number of pairs. The tolerance contract (absolute error ≤ 0.05 for target r ≥ 0.5, otherwise ≤ 0.08) applies to `achieved_r`; `observed_r` fluctuates with the wafer and site counts, so small runs must not be judged against it.

**Considered Options**

- Draw an independent die-level component for each WAT site: this attenuates the achievable correlation and needs extra compensation in calibration.
- Pair wafer means of WAT and CP: the sample size equals the wafer count, which is too noisy for small scenarios.
- Give every pair its own latent factor: already rejected in ADR-0001 because it cannot guarantee cross-item consistency.

**Consequences**

- Small runs (for example 1 lot x 1 wafer) can show an `observed_r` far from the target; that is sampling noise, and `achieved_r` remains the calibration contract.
- The schema default of 1 lot x 25 wafers x 9 sites provides only 225 paired observations, where a `±0.05` sample error is statistically unreachable; to check the generated data itself against the spec tolerance, use at least 10 lots x 25 wafers x 21 sites (the size used by this repository's correlation test).
- A YMS correlation analysis needs enough wafers before its estimates approach the reported achieved values.
- Nearest-die pairing is a modelling simplification: PCM structures sit in scribe lines, so the nearest die is only a proxy for local process conditions.

</details>

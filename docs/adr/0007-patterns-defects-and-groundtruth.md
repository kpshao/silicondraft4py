# 空间模式与随机缺陷只改测量值,ground truth 记录注入真相

**Status:** accepted (2026-11-03)

系统性空间模式与随机缺陷都必须能被 YMS 从导出的 CP 数据中重新发现,因此生成器不能直接给 die 写 bin,只能修改测量值,让 bin 继续由 spec limits 与 bin 规则推导。我们把每个模式实现为 wafer 上的确定性空间权重场 `w(x, y) ∈ [0, 1]`:center/local-spot 从一点向外线性衰减,edge 从可用半径向内线性增强,ring 在指定半径处 peaked,radial-gradient 从中心到可用边缘线性增长。`center_low` / `edge_low` 取负号,`ring` / `radial_gradient` / `local_spot` 直接使用有符号幅度。模式可同时指定 `target: yield` 与 `target_item`。

作用域方面,`scope: lot` 对 lot 内每片 wafer 应用同一模式;`scope: wafer` 在每个 lot 只作用于一张由 seed 派生的 wafer,并在 manifest 中记为 outlier wafer。对 yield 目标,负幅度按 `-amplitude * w` 的概率让该 die 的 `CP_FUNC`(缺失时用 `CP_SCAN`)失败;正幅度不制造失败,而是按同一比例降低该 die 的随机缺陷失败概率,否则在 100% 基线良率下 `center_high` 一类模式永远不可见。对 item 目标,`add` 按 `typical` 的比例平移测量值,`multiply` 按 `1 + delta` 或 `exp(delta)` 缩放;模式从不改写 bin。

随机缺陷在模式之后注入。默认 `clustered` 模型按 `failure_rate × die_count / cluster_size` 放置若干簇心,用高斯核抬高附近 die 的失败概率并归一化到目标失败率;`poisson` 模型令所有 die 独立同概率失败。两者都乘以 `1 - recovery`,以体现正幅度 yield 模式的保护作用。缺陷命中后让 `target_items` 中轮转选中的 CP 项失败:bernoulli 项置 0,连续项推到 spec limit 之外。默认 `failure_rate: 0.01`、`target_items: [CP_FUNC, CP_SCAN]`,因此默认总失败率接近 1%。由于概率裁剪与有限样本,实际失败率围绕目标波动。

Ground truth 输出每个 lot 一个 JSON manifest 和一个(默认开启的)每 die CSV.GZ。manifest 包含完整 scenario 与 `scenario_sha256`、seed、每 lot/wafer 良率、latent factor 均值、模式清单与各自贡献(实际失败数、item 平均相对偏移、recovery 概率和)、随机缺陷簇与位置、目标/达成/观测 r、outlier wafer 以及 die 真值文件名。模式使用稳定 ID `pattern_1`、`pattern_2`……;每 die 的 `pattern_ids` 用 `|` 分隔,避免与 CSV 逗号冲突。die 真值列为 `lot_id, wafer_id, die_x_mm, die_y_mm, grid_x, grid_y, test_site, true_pass, true_hard_bin, true_soft_bin, F_VT, F_MOB, F_TOX, F_RC, F_LEAK, F_SC, pattern_ids`。gzip 写入固定 `mtime=0`,使同一 scenario + seed 的 die 真值字节级一致;manifest 只排除 `generated_at` 与文件名时间戳。`--no-die-truth` 只跳过每 die 文件,manifest 仍然写出。

**考虑的其他方案**

- 模式直接写 hard/soft bin:实现简单,但导出数据不再自洽,YMS 可以从测量值推出与 bin 矛盾的结论。
- 只为 yield 实现模式,item 模式留到 V2:无法验证参数 wafer map,与 issue #7 的验收标准冲突。
- 用精确数量放置缺陷簇:失败率精确,但概率模型不自然,且正幅度 yield 模式无法通过降低概率起作用。
- 高良率模式不做任何事:在 100% 基线良率下 `center_high` / `edge_high` 不可观测,模式目录的一半形同虚设。
- 用随机 UUID 作为模式 ID:难以在文档与测试中引用,也无法直观判断叠加顺序。

**后果**

- scenario schema 新增 `defects` 节;禁用或删除 `CP_FUNC` / `CP_SCAN` 时,yield 模式与默认缺陷目标需要同步调整,语义校验会拒绝不可失败的 target。
- 正幅度 yield 模式的可见性依赖随机缺陷;若 `defects.enabled: false`,它们基本不改变数据。
- 默认场景现在约有 1% 的功能性失败,binning 与相关性测试需要显式关闭缺陷来隔离被测行为。
- 每 die 真值文件随 lot 数增长;大数据集可用 `--no-die-truth` 只保留 manifest。
- manifest 中的缺陷簇与 wafer 级模式列表会随 wafer 数增长,但规模远小于每 die 数据。

<details>
<summary>English</summary>

# Spatial patterns and random defects only change measurements; ground truth records the injected truth

**Status:** accepted (2026-11-03)

Both systematic spatial patterns and random defects must be rediscoverable by a YMS from the exported CP data, so the generator must not write bin codes directly. It only modifies measurements and lets binning stay derived from spec limits and bin rules. Each pattern is a deterministic spatial weight field `w(x, y) ∈ [0, 1]`: center and local-spot patterns decay linearly from a point, edge patterns ramp inward from the usable radius, rings peak at a radius, and radial gradients grow from the centre to the usable edge. `center_low` / `edge_low` negate the amplitude, while `ring` / `radial_gradient` / `local_spot` use their signed amplitude directly. A pattern may set both `target: yield` and `target_item`.

For scope, `scope: lot` applies the same pattern to every wafer in the lot, while `scope: wafer` applies it to one seed-derived wafer per lot and records that wafer as an outlier. For a yield target, a negative amplitude fails the die's `CP_FUNC` (or `CP_SCAN` when absent) with probability `-amplitude * w`; a positive amplitude creates no failures but reduces the die's random-defect failure probability by the same fraction, because `center_high`-style patterns would otherwise be invisible at a 100% baseline. For an item target, `add` shifts the measurement by a fraction of `typical`, and `multiply` scales by `1 + delta` or `exp(delta)`. Patterns never rewrite bins.

Random defects are injected after patterns. The default `clustered` model places `failure_rate × die_count / cluster_size` centres, raises nearby die failure probabilities with Gaussian kernels, and normalizes them to the target rate; the `poisson` model gives every die the same independent probability. Both multiply by `1 - recovery` so positive-amplitude yield patterns protect against defects. A defect event fails the CP item selected round-robin from `target_items`: Bernoulli items are set to 0, and continuous items are pushed outside their spec limits. The defaults are `failure_rate: 0.01` and `target_items: [CP_FUNC, CP_SCAN]`, so the default total failure rate is near 1%. Probability clipping and finite sampling make the realized rate fluctuate around the target.

Ground truth emits one JSON manifest per lot plus, by default, one per-die CSV.GZ. The manifest carries the full scenario and `scenario_sha256`, seed, per-lot/per-wafer yields, latent-factor means, the pattern manifest with each pattern's contribution (realized failures, mean relative item shift, and recovery probability sum), random-defect clusters and locations, target/achieved/observed correlations, outlier wafers, and die-truth file names. Patterns use stable IDs `pattern_1`, `pattern_2`, ...; a die's `pattern_ids` are joined with `|` to avoid colliding with the CSV comma. The die-truth columns are `lot_id, wafer_id, die_x_mm, die_y_mm, grid_x, grid_y, test_site, true_pass, true_hard_bin, true_soft_bin, F_VT, F_MOB, F_TOX, F_RC, F_LEAK, F_SC, pattern_ids`. Gzip writes with a fixed `mtime=0`, so the same scenario + seed yields byte-identical die truth; the manifest is reproducible except for `generated_at` and file-name timestamps. `--no-die-truth` skips only the per-die files, and the manifest is still written.

**Considered Options**

- Have patterns write hard/soft bins directly: simple, but the exported data would no longer be self-consistent, and a YMS could derive conclusions that contradict the bins.
- Implement only yield patterns and defer item patterns to V2: this cannot validate parametric wafer maps and conflicts with issue #7's acceptance criteria.
- Place an exact number of defects per cluster: the rate would be exact, but the model would be unnatural, and positive-amplitude yield patterns could not act by lowering probabilities.
- Let high-yield patterns do nothing: at a 100% baseline, `center_high` / `edge_high` would be unobservable, making half the pattern catalog hollow.
- Use random UUIDs as pattern IDs: they are hard to reference in docs and tests and do not reveal composition order.

**Consequences**

- The scenario schema gains a `defects` section; disabling or removing `CP_FUNC` / `CP_SCAN` requires adjusting yield-pattern and default defect targets, and semantic validation rejects targets that cannot fail.
- The visibility of positive-amplitude yield patterns depends on random defects; with `defects.enabled: false` they barely change the data.
- Default scenarios now have roughly 1% functional failures, so binning and correlation tests must disable defects explicitly to isolate the behavior under test.
- Per-die truth grows with the lot count; large runs can keep only the manifest via `--no-die-truth`.
- Defect clusters and wafer-scoped pattern lists in the manifest grow with the wafer count but stay much smaller than the per-die data.

</details>

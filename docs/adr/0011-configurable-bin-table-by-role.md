# Bin 表按语义角色配置，而不是自由改写失效分类

**Status:** accepted (2026-11-05)

YMS 通常使用自己的 hard/soft bin 编码与名称，而 V1 最初把内置 bin 表写死在 `binning.py` 中，scenario 无法把导出的 bin 码对齐到目标 YMS。我们给 scenario 增加可选的 `bins` 节，按语义角色覆盖 hard/soft bin 的 `code`、`name` 与 `description`：hard 角色为 `pass`、`parametric`、`functional`、`continuity`，soft 角色为 `pass`、`continuity`、`leakage`、`iddq`、`vth`、`frequency`、`functional`、`other_parametric`。未覆盖的角色保留内置默认值；soft 角色到 hard 角色的映射与失败优先级（continuity → functional → leakage → iddq → vth → frequency → other_parametric）保持固定。角色只改导出身份，不改失效语义：`pass` 角色仍决定 die pass，连续性失败仍优先于功能失败，功能失败仍优先于参数失败。

```yaml
bins:
  hard:
    continuity:
      code: 40
      name: CT_FAIL
      description: Contact failure
  soft:
    continuity:
      code: 1201
      name: CONTACT
```

解析后的表同时驱动生成与导出：`classify_bins` 使用角色码写入 dataset，`die_pass` 与 `CPWafer.passed` 使用 `pass` 角色的 hard 码，CP long CSV 的 `hard_bin_name`/`soft_bin_name`、blocks CSV 的 `[BIN_DEFINITIONS]`、STDF 的 HBR/SBR 以及 GUI wafer map 的颜色与 tooltip 都读取同一张表。同一张 hard 或 soft 表内的 code 必须唯一，且落在 STDF `U*2` 的 1–65534 范围内（65535 是 STDF missing code）；语义校验对重复 code 报告 `DUPLICATE_BIN_CODE`，结构校验拒绝未知角色与非 ASCII 名称。自定义 CP 测试项可在 `items.overrides` 中设置 `soft_bin_role` 选择失效类别；WAT 项不能设置该字段。

**考虑的其他方案**

- 允许用户提供完全自由格式的 bin 表（任意条目、任意 soft→hard 映射）：最灵活，但会破坏「bin 由 spec limits 与固定规则推导」的不变量，YMS 可能从测量值推出与 bin 矛盾的结论。
- 按 CP item 指定 soft bin 码：能覆盖自定义测试项，但把测试项目录与 bin 表耦合起来，且无法表达同一 item 在不同场景下复用同一失效类别。
- 只支持 bin 别名（code 固定、只改名称）：实现最小，但无法满足「bin 码匹配我的 YMS」这一主要诉求。
- 不支持配置，要求用户后处理导出文件：把一致性负担推给下游，且 STDF 的 HBR/SBR 已带 bin 名，后处理容易遗漏。
- 把 `bins` 做成预设整体替换而不是逐角色补丁：用户必须重写全部角色，且未来新增角色会破坏旧文件。

**后果**

- `schema_version` 保持 1；`bins` 是可选分节，旧 scenario 行为不变。JSON Schema 自动暴露 hard/soft 角色枚举与 `code` 范围。
- 修改 `pass` 角色码会同步改变 dataset、CSV 的 `die_pass` 与 STDF 的 PASS 判定；这是有意行为，测试覆盖了自定义 pass 码。
- 重复 code 在语义校验阶段被拒绝；`resolve_bin_table` 不再负责去重。
- ground truth manifest 的 `scenario` 字段包含 `bins`，因此 `scenario_sha256` 会随 bin 配置变化。
- GUI 不再使用静态 bin 颜色表；颜色按角色映射，未知码仍显示为灰色。

<details>
<summary>English</summary>

# Configure bins by semantic role instead of allowing arbitrary failure classifications

**Status:** accepted (2026-11-05)

A YMS usually has its own hard/soft bin codes and names, but V1 initially hard-coded the built-in bin table in `binning.py`, so the scenario could not align exported bin codes with the target YMS. We add an optional `bins` section that overrides `code`, `name`, and `description` for semantic hard/soft roles. The hard roles are `pass`, `parametric`, `functional`, and `continuity`; the soft roles are `pass`, `continuity`, `leakage`, `iddq`, `vth`, `frequency`, `functional`, and `other_parametric`. Roles that are not overridden keep their built-in defaults. The soft-to-hard role mapping and the failure precedence (continuity → functional → leakage → iddq → vth → frequency → other_parametric) stay fixed. A role only changes the exported identity, never the failure semantics: the `pass` role still determines die pass, continuity failures still outrank functional failures, and functional failures still outrank parametric failures.

```yaml
bins:
  hard:
    continuity:
      code: 40
      name: CT_FAIL
      description: Contact failure
  soft:
    continuity:
      code: 1201
      name: CONTACT
```

The resolved table drives generation and export: `classify_bins` writes role codes into the dataset, `die_pass` and `CPWafer.passed` use the `pass` role's hard code, and the CP long CSV's `hard_bin_name`/`soft_bin_name`, the blocks CSV `[BIN_DEFINITIONS]`, STDF HBR/SBR, and the GUI wafer map's colours and tooltips all read the same table. Codes must be unique within the hard table and within the soft table, and must fall in the STDF `U*2` range 1–65534 (65535 is the STDF missing code); semantic validation reports `DUPLICATE_BIN_CODE` for duplicates, while structural validation rejects unknown roles and non-ASCII names. Custom CP items can set `soft_bin_role` in `items.overrides` to choose their failure category; WAT items cannot set it.

**Considered Options**

- Let users supply a completely free-form bin table (arbitrary entries and soft-to-hard mappings): the most flexible option, but it breaks the invariant that bins are derived from spec limits and fixed rules, and a YMS could derive conclusions that contradict the bins.
- Let each CP item name its soft bin code: it would cover custom items but couples the test item catalog to the bin table and cannot express one failure category shared by several items.
- Support aliases only (fixed codes, configurable names): the smallest implementation, but it does not satisfy the primary requirement of matching the YMS's bin codes.
- Do not support configuration and require post-processing: it pushes consistency work downstream, and the STDF HBR/SBR records already carry bin names, so post-processing is easy to get wrong.
- Make `bins` a wholesale preset replacement instead of per-role patches: users would have to rewrite every role, and adding a future role would break old files.

**Consequences**

- `schema_version` stays 1; `bins` is an optional section, so existing scenarios behave exactly as before. The JSON Schema exposes the hard/soft role enums and the `code` range automatically.
- Changing the `pass` role's code also changes the dataset, CSV `die_pass`, and STDF pass classification; this is intentional and covered by tests with custom pass codes.
- Duplicate codes are rejected during semantic validation; `resolve_bin_table` is not responsible for de-duplication.
- The ground truth manifest's `scenario` field includes `bins`, so `scenario_sha256` changes with the bin configuration.
- The GUI no longer uses static bin colour tables; colours map by role, and unknown codes still render grey.

</details>

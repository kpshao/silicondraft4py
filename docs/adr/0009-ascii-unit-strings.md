# 导出数据中的单位使用 ASCII SI 记法

**Status:** accepted (2026-11-03)

默认 `export.encoding: utf-8` 不写 BOM，Excel 双击打开时会按本地 ANSI 编码解析 `unit` 列中的 `µ`、`Ω`、`Å`、`²` 等符号并产生乱码；即使提供 `utf-8-sig`，WPS、部分脚本与下游工具仍可能不尊重 BOM。同时，半导体测试数据（如 STDF）本身以 ASCII 单位串为惯例。因此内置 catalog 的单位字面量改为 ASCII SI 记法：`µA`→`uA`、`µA/µm`→`uA/um`、`pA/µm`→`pA/um`、`Ω`→`ohm`、`Ω/sq`→`ohm/sq`、`A/cm²`→`A/cm2`、`Å`→`angstrom`。`resolve_catalog` 对解析后的每个单位执行 `str.isascii()` 校验，非 ASCII 单位报 `ITEM_UNIT_NOT_ASCII` 语义错误，并在错误信息中给出建议写法。默认编码保持 `utf-8`；`utf-8-sig` 仍作为包含非 ASCII 元数据时的可选方案。`csv_format_version` 保持 `2`，因为块布局与列结构未变。

**考虑的其他方案**

- 只把默认 `export.encoding` 改为 `utf-8-sig`：依赖查看器尊重 BOM，WPS 与部分脚本仍会误读，也不解决未来 STDF/下游解析的同一问题。
- catalog 保留 SI 符号、仅在 CSV 导出时转写：API 与导出出现两套词表，且转写规则对自定义单位不封闭，无法保证 `unit` 列纯 ASCII。
- 只改内置 catalog、不校验 override：用户写回 `µA` 时乱码会复发，验收标准无法满足。
- 用 `A` 表示 `Å`：与安培（ampere）冲突，放弃。

**后果**

- 下游若按 SI 符号解析单位字符串，需要迁移到 ASCII 记法；这是有意的一次性迁移。
- 现有在 `items.overrides[].unit` 中使用非 ASCII 单位的 scenario 会在校验阶段失败，错误信息给出建议写法。
- 未来 STDF writer 直接使用同一套 catalog 字符串，无需额外转写。
- 测试项目录中的单位表与导出数据保持一致；README 的 Excel 说明改为仅针对非 ASCII 元数据。

<details>
<summary>English</summary>

# Use ASCII SI notation for units in exported data

**Status:** accepted (2026-11-03)

The default `export.encoding: utf-8` writes no BOM, so double-clicking the CSV in Excel makes Excel decode `µ`, `Ω`, `Å`, and `²` in the `unit` column with the local ANSI codepage, producing mojibake; even with `utf-8-sig`, WPS, some scripts, and downstream tools may ignore the BOM. Semiconductor test data (such as STDF) also conventionally uses ASCII unit strings. The built-in catalog's unit literals therefore become ASCII SI notation: `µA`→`uA`, `µA/µm`→`uA/um`, `pA/µm`→`pA/um`, `Ω`→`ohm`, `Ω/sq`→`ohm/sq`, `A/cm²`→`A/cm2`, and `Å`→`angstrom`. `resolve_catalog` validates every resolved unit with `str.isascii()` and reports a non-ASCII unit as the semantic error `ITEM_UNIT_NOT_ASCII`, including the suggested spelling in the message. The default encoding stays `utf-8`; `utf-8-sig` remains available for non-ASCII metadata. `csv_format_version` stays `2` because the block layout and column structure are unchanged.

**Considered Options**

- Changing only the default `export.encoding` to `utf-8-sig`: relies on viewers honouring the BOM; WPS and some scripts still misread it, and it does not address the same problem for STDF or downstream parsers.
- Keeping SI symbols in the catalog and transliterating only at CSV export: leaves two unit vocabularies between the API and the export, and the transliteration is not closed over custom units, so a pure-ASCII `unit` column cannot be guaranteed.
- Changing only the built-in catalog without validating overrides: a user writing `µA` would reintroduce mojibake, so the acceptance criterion would not hold.
- Using `A` for `Å`: conflicts with ampere; rejected.

**Consequences**

- Downstream code that parses SI symbols must migrate to ASCII notation; this is a deliberate, one-time migration.
- Scenarios that use non-ASCII units in `items.overrides[].unit` now fail validation, with the suggested spelling in the error message.
- A future STDF writer uses the same catalog strings with no extra transliteration.
- The unit table in the test-item catalog stays consistent with exported data; the README's Excel note now covers non-ASCII metadata only.

</details>

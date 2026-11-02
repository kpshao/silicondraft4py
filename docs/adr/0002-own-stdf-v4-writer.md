# 自研 STDF V4 writer

**Status:** accepted (2026-11-02)

CP 数据必须导出为 STDF V4，而现有 Python 库要么停更（`semi-ate-stdf` PyPI 0.1.28，2022）、要么只读（`pystdf`）、要么不完整或实验性（`pystdf4`、`stdfast`）。我们决定自研 STDF V4 writer，以 Semi-ATE 的 MIT 记录定义为字段布局参考；`pystdf` 仅作为测试期独立解析器，`stdfast` 作为可选第二 oracle。这样可完全控制记录覆盖、缺失值编码、确定性与性能，并避免运行时依赖停更库或 GPL 代码。

<details>
<summary>English</summary>

# Build our own STDF V4 writer

**Status:** accepted (2026-11-02)

CP data must be exported as STDF V4, but the available Python libraries are stale (`semi-ate-stdf` PyPI 0.1.28, 2022), read-only (`pystdf`), or incomplete/experimental (`pystdf4`, `stdfast`). We will implement our own STDF V4 writer, using Semi-ATE's MIT-licensed record definitions as the field-layout reference; `pystdf` is a test-only independent parser and `stdfast` an optional second oracle. This gives full control over record coverage, missing-value encoding, determinism, and performance, and avoids a runtime dependency on a dormant or GPL-licensed package.

</details>

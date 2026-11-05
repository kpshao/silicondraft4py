"""Hard- and soft-bin roles shared by the schema and the binning engine.

This module is dependency-free so both the Pydantic scenario models and the
NumPy-free parts of the engine can import it without creating a package cycle.
"""

from typing import Literal

HardBinRole = Literal["pass", "parametric", "functional", "continuity"]
SoftBinRole = Literal[
    "pass",
    "continuity",
    "leakage",
    "iddq",
    "vth",
    "frequency",
    "functional",
    "other_parametric",
]

#: Hard-bin roles in generation order; the pass role is always first.
HARD_BIN_ROLES: tuple[HardBinRole, ...] = ("pass", "parametric", "functional", "continuity")
#: Soft-bin roles in generation order; the pass role is always first.
SOFT_BIN_ROLES: tuple[SoftBinRole, ...] = (
    "pass",
    "continuity",
    "leakage",
    "iddq",
    "vth",
    "frequency",
    "functional",
    "other_parametric",
)

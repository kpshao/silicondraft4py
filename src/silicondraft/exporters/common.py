"""Shared formatting and identity helpers for exported artifacts."""

import hashlib
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Protocol

from ..errors import ExportError
from ..i18n import _
from ..scenario.models import Scenario

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


class CsvWriter(Protocol):
    """The subset of ``csv.writer`` used by the exporters."""

    def writerow(self, row: Sequence[object]) -> object: ...


def ensure_output_path(path: Path, *, overwrite: bool) -> None:
    """Refuse to replace an existing artifact unless ``overwrite`` is set."""
    if path.exists() and not overwrite:
        raise ExportError(
            _(
                "output file already exists: {path}; "
                "use the overwrite option (--overwrite) to replace it"
            ).format(path=path)
        )


def format_float(value: float) -> str:
    """Format a measurement with the CSV's compact dot-decimal convention."""
    return format(value, ".10g")


def format_optional_float(value: float | None) -> str:
    """Format an optional measurement, using an empty cell for missing values."""
    return "" if value is None else format_float(value)


def format_timestamp(value: datetime) -> str:
    """Format a timestamp as ISO 8601 in UTC."""
    return value.astimezone(UTC).isoformat()


def timestamp_token(value: datetime) -> str:
    """Format a timestamp token for use in file names."""
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def scenario_sha256(scenario: Scenario) -> str:
    """Return the SHA-256 of the canonical scenario JSON."""
    canonical = json.dumps(
        scenario.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def engine_version() -> str:
    """Return the installed engine version, or a placeholder in a source tree."""
    try:
        return package_version("silicondraft")
    except PackageNotFoundError:  # pragma: no cover - running from an unpacked tree
        return "0.0.0"


def safe_filename_part(value: str) -> str:
    """Make a product, lot, or wafer ID safe for a file name."""
    return _UNSAFE_FILENAME_CHARS.sub("_", value).strip("_") or "unnamed"

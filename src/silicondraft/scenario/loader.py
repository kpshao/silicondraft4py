"""Loading and structurally validating scenario YAML."""

from collections.abc import Sequence
from os import PathLike
from pathlib import Path
from typing import NoReturn

import yaml
from pydantic import ValidationError

from ..errors import ScenarioError, ValidationIssue
from .models import Scenario
from .presets import expand_preset

_ERROR_CODES: dict[str, str] = {
    "missing": "REQUIRED",
    "extra_forbidden": "UNKNOWN_FIELD",
    "literal_error": "INVALID_VALUE",
    "string_type": "INVALID_TYPE",
    "string_parsing": "INVALID_TYPE",
    "int_type": "INVALID_TYPE",
    "int_parsing": "INVALID_TYPE",
    "float_type": "INVALID_TYPE",
    "float_parsing": "INVALID_TYPE",
    "finite_number": "INVALID_VALUE",
    "bool_type": "INVALID_TYPE",
    "bool_parsing": "INVALID_TYPE",
    "list_type": "INVALID_TYPE",
    "tuple_type": "INVALID_TYPE",
    "dict_type": "INVALID_TYPE",
    "model_type": "INVALID_TYPE",
    "datetime_type": "INVALID_TYPE",
    "datetime_parsing": "INVALID_TYPE",
    "datetime_from_date_parsing": "INVALID_TYPE",
    "greater_than": "OUT_OF_RANGE",
    "greater_than_equal": "OUT_OF_RANGE",
    "less_than": "OUT_OF_RANGE",
    "less_than_equal": "OUT_OF_RANGE",
    "string_too_short": "OUT_OF_RANGE",
    "string_too_long": "OUT_OF_RANGE",
    "too_short": "OUT_OF_RANGE",
    "too_long": "OUT_OF_RANGE",
    "string_pattern_mismatch": "INVALID_VALUE",
}


def read_scenario_data(path: str | PathLike[str]) -> object:
    """Read a YAML file and return its raw document."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        _raise_scenario_error(
            "FILE_NOT_FOUND",
            "<file>",
            f"scenario file not found: {file_path}",
            exc,
        )
    except UnicodeDecodeError as exc:
        _raise_scenario_error(
            "FILE_ENCODING_ERROR",
            "<file>",
            f"scenario file {file_path} is not valid UTF-8: {exc}",
            exc,
        )
    except OSError as exc:
        _raise_scenario_error(
            "FILE_READ_ERROR",
            "<file>",
            f"cannot read scenario file {file_path}: {exc}",
            exc,
        )
    return parse_yaml_document(text)


def parse_yaml_document(text: str) -> object:
    """Parse scenario YAML text into a raw document with locatable parse errors."""
    try:
        data: object = yaml.safe_load(text)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        if mark is None:
            message = f"YAML parse error: {exc.problem or exc}"
        else:
            message = (
                f"YAML parse error at line {mark.line + 1}, column {mark.column + 1}: "
                f"{exc.problem or 'invalid YAML'}"
            )
        _raise_scenario_error("YAML_PARSE_ERROR", "<document>", message, exc)
    except yaml.YAMLError as exc:
        _raise_scenario_error(
            "YAML_PARSE_ERROR",
            "<document>",
            f"YAML parse error: {exc}",
            exc,
        )

    if data is None:
        _raise_scenario_error("SCENARIO_EMPTY", "<document>", "scenario document is empty")
    if not isinstance(data, dict):
        _raise_scenario_error(
            "SCENARIO_NOT_MAPPING",
            "<document>",
            "scenario document must be a mapping of sections",
        )
    return data


def _raise_scenario_error(
    code: str, path: str, message: str, cause: BaseException | None = None
) -> NoReturn:
    error = ScenarioError([ValidationIssue(code=code, path=path, message=message)])
    if cause is None:
        raise error
    raise error from cause


def parse_scenario(data: object) -> Scenario:
    """Validate a raw scenario document against the v1 structure."""
    try:
        return Scenario.model_validate(expand_preset(data))
    except ValidationError as exc:
        raise ScenarioError(issues_from_validation_error(exc)) from exc


def parse_scenario_text(text: str) -> Scenario:
    """Parse and structurally validate a scenario YAML document held in memory."""
    return parse_scenario(parse_yaml_document(text))


def issues_from_validation_error(exc: ValidationError) -> tuple[ValidationIssue, ...]:
    """Convert Pydantic errors into stable, locatable issues."""
    issues: list[ValidationIssue] = []
    for error in exc.errors():
        error_type = str(error["type"])
        issues.append(
            ValidationIssue(
                code=_ERROR_CODES.get(error_type, "INVALID_VALUE"),
                path=_format_location(error["loc"]),
                message=str(error["msg"]),
            )
        )
    return tuple(issues)


def _format_location(loc: Sequence[str | int]) -> str:
    if not loc:
        return "<document>"
    first, *rest = loc
    path = str(first)
    for part in rest:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


__all__ = [
    "issues_from_validation_error",
    "parse_scenario",
    "parse_scenario_text",
    "parse_yaml_document",
    "read_scenario_data",
]

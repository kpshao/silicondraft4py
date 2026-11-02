from typing import Any

import yaml
from jsonschema import Draft202012Validator

from silicondraft import scenario_schema

_SECTIONS = {
    "schema_version",
    "product",
    "wafer",
    "lots",
    "items",
    "patterns",
    "linkage",
    "export",
    "seed",
    "metadata",
}


def test_schema_is_valid_json_schema_2020_12() -> None:
    schema = scenario_schema()

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_schema_covers_every_v1_section() -> None:
    schema = scenario_schema()

    assert set(schema["properties"]) == _SECTIONS
    assert set(schema["required"]) == {"schema_version", "product", "seed"}
    assert schema["properties"]["schema_version"]["const"] == 1


def test_schema_accepts_a_minimal_scenario() -> None:
    document: Any = yaml.safe_load(
        "schema_version: 1\nproduct:\n  name: GEN55LOGIC\nseed: 20260105\n"
    )

    Draft202012Validator(scenario_schema()).validate(document)


def test_schema_rejects_an_unknown_section() -> None:
    document: Any = yaml.safe_load(
        "schema_version: 1\nproduct:\n  name: GEN55LOGIC\nseed: 20260105\nunknown_section: {}\n"
    )

    errors = list(Draft202012Validator(scenario_schema()).iter_errors(document))

    assert len(errors) == 1
    assert errors[0].validator == "additionalProperties"
    assert "unknown_section" in errors[0].message

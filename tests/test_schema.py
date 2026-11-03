import json
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
    "defects",
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


def test_schema_exposes_the_random_defect_settings() -> None:
    schema = scenario_schema()

    defects = schema["$defs"]["Defects"]
    assert defects["properties"]["model"]["enum"] == ["clustered", "poisson"]
    assert defects["properties"]["failure_rate"]["default"] == 0.01
    assert defects["properties"]["target_items"]["type"] == "array"
    assert "defects" not in schema["required"]


def test_schema_exposes_an_optional_product_test_program() -> None:
    schema = scenario_schema()

    product = schema["$defs"]["Product"]
    assert "test_program" in product["properties"]
    assert product["properties"]["test_program"]["type"] == "string"
    assert "test_program" not in product.get("required", [])


def test_schema_does_not_expose_split_by_wafer() -> None:
    schema = scenario_schema()

    assert "split_by_wafer" not in json.dumps(schema)
    document: Any = yaml.safe_load(
        "schema_version: 1\nproduct:\n  name: GEN55LOGIC\n"
        "export:\n  split_by_wafer: true\nseed: 1\n"
    )

    errors = list(Draft202012Validator(schema).iter_errors(document))

    assert len(errors) == 1
    assert errors[0].validator == "additionalProperties"
    assert "split_by_wafer" in errors[0].message


def test_schema_rejects_an_unknown_section() -> None:
    document: Any = yaml.safe_load(
        "schema_version: 1\nproduct:\n  name: GEN55LOGIC\nseed: 20260105\nunknown_section: {}\n"
    )

    errors = list(Draft202012Validator(scenario_schema()).iter_errors(document))

    assert len(errors) == 1
    assert errors[0].validator == "additionalProperties"
    assert "unknown_section" in errors[0].message

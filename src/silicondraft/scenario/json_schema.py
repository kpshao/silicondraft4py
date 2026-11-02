"""JSON Schema export for scenario v1."""

from typing import Any

from .models import Scenario

_JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def scenario_schema() -> dict[str, Any]:
    """Return the JSON Schema for scenario v1."""
    schema = Scenario.model_json_schema(mode="validation")
    schema["$schema"] = _JSON_SCHEMA_DIALECT
    return schema

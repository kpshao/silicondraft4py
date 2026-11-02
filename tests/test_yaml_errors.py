from pathlib import Path

from silicondraft import validate_scenario


def test_yaml_syntax_error_reports_line_and_column(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text("schema_version: [\n", encoding="utf-8")

    result = validate_scenario(path)

    assert result.ok is False
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.code == "YAML_PARSE_ERROR"
    assert issue.path == "<document>"
    assert "line " in issue.message
    assert "column " in issue.message


def test_empty_document_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text("", encoding="utf-8")

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("SCENARIO_EMPTY", "<document>")
    ]


def test_non_mapping_document_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text("- schema_version\n- 1\n", encoding="utf-8")

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("SCENARIO_NOT_MAPPING", "<document>")
    ]


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    result = validate_scenario(tmp_path / "absent.yaml")

    assert result.ok is False
    assert [(issue.code, issue.path) for issue in result.issues] == [("FILE_NOT_FOUND", "<file>")]


def test_schema_version_must_be_one(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "schema_version: 2\nproduct:\n  name: GEN55LOGIC\nseed: 1\n",
        encoding="utf-8",
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("INVALID_VALUE", "schema_version")
    ]


def test_seed_is_required(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "schema_version: 1\nproduct:\n  name: GEN55LOGIC\n",
        encoding="utf-8",
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [("REQUIRED", "seed")]


def test_non_utf8_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_bytes(b"\xff\xfe\x00\x00")

    result = validate_scenario(path)

    assert result.ok is False
    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("FILE_ENCODING_ERROR", "<file>")
    ]

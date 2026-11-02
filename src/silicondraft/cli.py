"""Command line interface for SiliconDraft."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from . import (
    ValidationIssue,
    __version__,
    export,
    generate,
    load_scenario,
    scenario_schema,
    validate_scenario,
)
from .errors import ExportError, ScenarioError


class _ArgumentParser(argparse.ArgumentParser):
    """Parser that treats usage errors as configuration errors (exit 1)."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = _ArgumentParser(
        prog="silicondraft",
        description="Generate reproducible synthetic CP/WAT test data.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    generate_parser = subparsers.add_parser("generate", help="generate data and write CP wide CSV")
    generate_parser.add_argument(
        "-c",
        "--config",
        required=True,
        type=Path,
        metavar="SCENARIO",
        help="path to the scenario YAML file",
    )
    generate_parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        metavar="DIR",
        help="directory for exported files",
    )

    validate_parser = subparsers.add_parser("validate", help="validate a scenario YAML file")
    validate_parser.add_argument(
        "-c",
        "--config",
        required=True,
        type=Path,
        metavar="SCENARIO",
        help="path to the scenario YAML file",
    )

    subparsers.add_parser("schema", help="print the scenario JSON Schema")
    subparsers.add_parser("version", help="print the SiliconDraft version")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    match args.command:
        case "generate":
            return _generate(args.config, args.output)
        case "validate":
            return _validate(args.config)
        case "schema":
            return _schema()
        case "version":
            return _version()
        case _:
            parser.print_help()
            return 1


def _generate(scenario_path: Path, output_dir: Path) -> int:
    try:
        scenario = load_scenario(scenario_path)
    except ScenarioError as exc:
        _print_invalid(scenario_path, exc.issues)
        return 1

    try:
        result = generate(scenario)
    except ScenarioError as exc:
        _print_invalid(scenario_path, exc.issues)
        return 1
    except Exception as exc:
        print(f"generation failed: {exc}", file=sys.stderr)
        return 2

    try:
        paths = export(result, output_dir)
    except ExportError as exc:
        print(f"export failed: {exc}", file=sys.stderr)
        return 3

    wafers = sum(len(lot.wafers) for lot in result.lots)
    dies = sum(wafer.die_count for lot in result.lots for wafer in lot.wafers)
    print(f"scenario: OK ({scenario_path})")
    print(f"generated: {len(result.lots)} lot(s), {wafers} wafer(s), {dies} die(s)")
    for path in paths:
        print(f"exported: {path}")
    return 0


def _validate(scenario_path: Path) -> int:
    result = validate_scenario(scenario_path)
    if not result.ok:
        _print_invalid(scenario_path, result.issues)
        return 1

    summary = result.summary
    if summary is None:  # pragma: no cover - guarded by ValidationResult contract
        print("scenario: INVALID: validation produced no summary", file=sys.stderr)
        return 1

    print(f"scenario: OK ({scenario_path})")
    print(f"  product: {summary.product}")
    print(f"  schema_version: {summary.schema_version}")
    print(f"  lots: {summary.lots}")
    print(f"  wafers_per_lot: {summary.wafers_per_lot}")
    print(f"  wafers: {summary.wafers}")
    print(f"  dies_per_wafer: {summary.dies_per_wafer}")
    print(f"  dies_total: {summary.dies_total}")
    print(f"  cp_items: {summary.cp_items}")
    print(f"  wat_items: {summary.wat_items}")
    print(f"  items_total: {summary.items_total}")
    return 0


def _print_invalid(scenario_path: Path, issues: Sequence[ValidationIssue]) -> None:
    print(f"scenario: INVALID ({scenario_path})", file=sys.stderr)
    for issue in issues:
        print(
            f"  {issue.path}: {issue.message} [{issue.code}]",
            file=sys.stderr,
        )


def _schema() -> int:
    print(json.dumps(scenario_schema(), indent=2, ensure_ascii=False))
    return 0


def _version() -> int:
    print(f"silicondraft {__version__}")
    return 0

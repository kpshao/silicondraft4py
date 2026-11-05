"""Command line interface for SiliconDraft."""

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from . import (
    ValidationIssue,
    __version__,
    generate_to_directory,
    load_scenario,
    scenario_schema,
    validate_scenario,
)
from .errors import ExportError, ScenarioError
from .i18n import DEFAULT_LANGUAGE, _, install, reset
from .scenario.models import EXPORT_FORMATS, MAX_SEED
from .scenario.validation import ScenarioSummary, validate_scenario_model

LANGUAGE_CHOICES = ("en", "zh")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
DEFAULT_LOG_LEVEL = "WARNING"

logger = logging.getLogger("silicondraft.cli")


class _ArgumentParser(argparse.ArgumentParser):
    """Parser that treats usage errors as configuration errors (exit 1)."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _add_language_argument(parser: argparse.ArgumentParser, *, default: str | None) -> None:
    """Add ``--lang`` to ``parser``, suppressing the default when ``default`` is None.

    Subparsers suppress their default so a language given before the command
    is not overwritten, while ``generate --lang zh`` still works.
    """
    parser.add_argument(
        "--lang",
        choices=LANGUAGE_CHOICES,
        default=argparse.SUPPRESS if default is None else default,
        help=_("message language: en or zh"),
    )


def _add_log_level_argument(parser: argparse.ArgumentParser, *, default: str | None) -> None:
    """Add ``--log-level``, suppressing subparser defaults like ``--lang``."""
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=LOG_LEVELS,
        default=argparse.SUPPRESS if default is None else default,
        help=_("log verbosity: DEBUG, INFO, WARNING, ERROR, or CRITICAL"),
    )


def _configure_logging(level_name: str) -> None:
    """Configure English logging for this CLI entry point.

    The CLI owns the process, so configuring the root handler is intentional.
    Pinning both the package and CLI logger levels makes ``--log-level`` win
    over a host application's or test harness's logger level.
    """
    level = getattr(logging, level_name)
    logging.getLogger("silicondraft").setLevel(level)
    logger.setLevel(level)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _seed_value(value: str) -> int:
    """Parse a ``--seed`` override and enforce the scenario seed range."""
    try:
        seed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(_("seed must be an integer")) from exc
    if not 0 <= seed <= MAX_SEED:
        raise argparse.ArgumentTypeError(
            _("seed must be between 0 and {maximum}").format(maximum=MAX_SEED)
        )
    return seed


def _export_formats(value: str) -> tuple[str, ...]:
    """Parse a comma-separated ``--formats`` value."""
    requested = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    supported = ", ".join(EXPORT_FORMATS)
    if not requested:
        raise argparse.ArgumentTypeError(
            _("no export format requested; supported: {formats}").format(formats=supported)
        )
    unsupported = sorted(set(requested) - set(EXPORT_FORMATS))
    if unsupported:
        raise argparse.ArgumentTypeError(
            _("unsupported export format(s): {formats}; supported: {supported}").format(
                formats=", ".join(unsupported), supported=supported
            )
        )
    return requested


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser in the currently installed language."""
    parser = _ArgumentParser(
        prog="silicondraft",
        description=_("Generate reproducible synthetic CP/WAT test data."),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    _add_language_argument(parser, default=DEFAULT_LANGUAGE)
    _add_log_level_argument(parser, default=DEFAULT_LOG_LEVEL)
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    generate_parser = subparsers.add_parser(
        "generate", help=_("generate data and write STDF, CSV, and ground truth")
    )
    _add_language_argument(generate_parser, default=None)
    _add_log_level_argument(generate_parser, default=None)
    generate_parser.add_argument(
        "-c",
        "--config",
        required=True,
        type=Path,
        metavar="SCENARIO",
        help=_("path to the scenario YAML file"),
    )
    generate_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="DIR",
        help=_("directory for exported files (required unless --dry-run is used)"),
    )
    generate_parser.add_argument(
        "--formats",
        type=_export_formats,
        default=None,
        metavar="FORMATS",
        help=_("comma-separated export formats: stdf, csv"),
    )
    generate_parser.add_argument(
        "--seed",
        type=_seed_value,
        default=None,
        metavar="SEED",
        help=_("override the scenario seed for this run"),
    )
    generate_parser.add_argument(
        "--no-die-truth",
        action="store_true",
        help=_("skip the per-die ground truth CSV.GZ (the JSON manifest is still written)"),
    )
    generate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help=_("validate the scenario and print its summary without generating or writing files"),
    )
    generate_parser.add_argument(
        "--overwrite",
        action="store_true",
        help=_("replace output files that already exist"),
    )

    validate_parser = subparsers.add_parser("validate", help=_("validate a scenario YAML file"))
    _add_language_argument(validate_parser, default=None)
    _add_log_level_argument(validate_parser, default=None)
    validate_parser.add_argument(
        "-c",
        "--config",
        required=True,
        type=Path,
        metavar="SCENARIO",
        help=_("path to the scenario YAML file"),
    )

    schema_parser = subparsers.add_parser("schema", help=_("print the scenario JSON Schema"))
    _add_language_argument(schema_parser, default=None)
    _add_log_level_argument(schema_parser, default=None)
    version_parser = subparsers.add_parser("version", help=_("print the SiliconDraft version"))
    _add_language_argument(version_parser, default=None)
    _add_log_level_argument(version_parser, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    arguments = list(argv) if argv is not None else sys.argv[1:]
    install(_requested_language(arguments))
    try:
        parser = build_parser()
        args = parser.parse_args(arguments)
        _configure_logging(args.log_level)

        match args.command:
            case "generate":
                if args.dry_run:
                    return _dry_run(
                        args.config,
                        seed=args.seed,
                        formats=args.formats,
                        include_die_truth=False if args.no_die_truth else None,
                        overwrite=args.overwrite,
                    )
                if args.output is None:
                    parser.error(_("--output is required unless --dry-run is used"))
                return _generate(
                    args.config,
                    args.output,
                    include_die_truth=False if args.no_die_truth else None,
                    formats=args.formats,
                    seed=args.seed,
                    overwrite=args.overwrite,
                )
            case "validate":
                return _validate(args.config)
            case "schema":
                return _schema()
            case "version":
                return _version()
            case _:
                parser.print_help()
                return 1
    finally:
        reset()


def _requested_language(arguments: Sequence[str]) -> str:
    """Find ``--lang`` before parsing so help and errors use that language."""
    for index, argument in enumerate(arguments):
        if argument == "--lang" and index + 1 < len(arguments):
            return arguments[index + 1]
        if argument.startswith("--lang="):
            return argument.partition("=")[2]
    return DEFAULT_LANGUAGE


def _generate(
    scenario_path: Path,
    output_dir: Path,
    *,
    include_die_truth: bool | None = None,
    formats: Sequence[str] | None = None,
    seed: int | None = None,
    overwrite: bool = False,
) -> int:
    try:
        scenario = load_scenario(scenario_path)
    except ScenarioError as exc:
        _print_invalid(scenario_path, exc.issues)
        return 1
    if seed is not None:
        scenario = scenario.model_copy(update={"seed": seed})

    logger.info(
        "generating scenario=%s seed=%d output=%s", scenario_path, scenario.seed, output_dir
    )
    try:
        summary, paths = generate_to_directory(
            scenario,
            output_dir,
            include_die_truth=include_die_truth,
            formats=formats,
            overwrite=overwrite,
        )
    except ScenarioError as exc:
        _print_invalid(scenario_path, exc.issues)
        return 1
    except ExportError as exc:
        print(_("export failed: {error}").format(error=exc), file=sys.stderr)
        return 3
    except Exception as exc:
        print(_("generation failed: {error}").format(error=exc), file=sys.stderr)
        return 2

    print(_("scenario: OK ({path})").format(path=scenario_path))
    print(
        _("generated: {lots} lot(s), {wafers} wafer(s), {dies} die(s)").format(
            lots=summary.lot_count,
            wafers=summary.wafer_count,
            dies=summary.die_count,
        )
    )
    logger.info(
        "generated lots=%d wafers=%d dies=%d output=%s",
        summary.lot_count,
        summary.wafer_count,
        summary.die_count,
        output_dir,
    )
    for entry in summary.linkage_report:
        print(
            _(
                "linkage: {wat} -> {cp} factor={factor} "
                "target_r={target:.3f} achieved_r={achieved:.3f} "
                "observed_r={observed:.3f}"
            ).format(
                wat=entry.wat_item,
                cp=entry.cp_item,
                factor=entry.factor,
                target=entry.target_r,
                achieved=entry.achieved_r,
                observed=entry.observed_r,
            )
        )
    for path in paths:
        print(_("exported: {path}").format(path=path))
        logger.debug("exported %s", path)
    return 0


def _validate(scenario_path: Path) -> int:
    result = validate_scenario(scenario_path)
    if not result.ok:
        _print_invalid(scenario_path, result.issues)
        return 1

    summary = result.summary
    if summary is None:  # pragma: no cover - guarded by ValidationResult contract
        print(
            _("scenario: INVALID: validation produced no summary"),
            file=sys.stderr,
        )
        return 1

    _print_validation_summary(scenario_path, summary)
    logger.debug("validated scenario %s", scenario_path)
    return 0


def _dry_run(
    scenario_path: Path,
    *,
    seed: int | None,
    formats: Sequence[str] | None,
    include_die_truth: bool | None,
    overwrite: bool,
) -> int:
    """Validate the effective run, print its options, and write nothing."""
    try:
        scenario = load_scenario(scenario_path)
    except ScenarioError as exc:
        _print_invalid(scenario_path, exc.issues)
        return 1
    if seed is not None:
        scenario = scenario.model_copy(update={"seed": seed})

    result = validate_scenario_model(scenario)
    if not result.ok:
        _print_invalid(scenario_path, result.issues)
        return 1
    summary = result.summary
    if summary is None:  # pragma: no cover - guarded by ValidationResult contract
        print(
            _("scenario: INVALID: validation produced no summary"),
            file=sys.stderr,
        )
        return 1

    _print_validation_summary(scenario_path, summary)
    requested = scenario.export.enabled_formats() if formats is None else tuple(formats)
    write_die_truth = (
        scenario.export.include_die_truth if include_die_truth is None else include_die_truth
    )
    print(_("dry-run: seed={seed}").format(seed=scenario.seed))
    print(_("dry-run: formats={formats}").format(formats=", ".join(requested) or "-"))
    print(
        _("dry-run: per-die truth={state}").format(state=_("on") if write_die_truth else _("off"))
    )
    print(_("dry-run: overwrite={state}").format(state=_("on") if overwrite else _("off")))
    print(_("dry-run: no files written"))
    logger.debug("dry-run validated scenario %s", scenario_path)
    return 0


def _print_validation_summary(scenario_path: Path, summary: ScenarioSummary) -> None:
    print(_("scenario: OK ({path})").format(path=scenario_path))
    print(_("  product: {value}").format(value=summary.product))
    print(_("  schema_version: {value}").format(value=summary.schema_version))
    if summary.preset is not None:
        print(_("  preset: {value}").format(value=summary.preset))
    print(_("  lots: {value}").format(value=summary.lots))
    print(_("  wafers_per_lot: {value}").format(value=summary.wafers_per_lot))
    print(_("  wafers: {value}").format(value=summary.wafers))
    print(_("  dies_per_wafer: {value}").format(value=summary.dies_per_wafer))
    print(_("  dies_total: {value}").format(value=summary.dies_total))
    print(_("  cp_items: {value}").format(value=summary.cp_items))
    print(_("  wat_items: {value}").format(value=summary.wat_items))
    print(_("  items_total: {value}").format(value=summary.items_total))


def _print_invalid(scenario_path: Path, issues: Sequence[ValidationIssue]) -> None:
    print(_("scenario: INVALID ({path})").format(path=scenario_path), file=sys.stderr)
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

"""Qt application entry point."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

from .. import __version__
from ..dataset import GenerationResult
from ..i18n import install as install_engine_translation
from .i18n import language_manager
from .main_window import MainWindow

APPLICATION_NAME = "SiliconDraft"


@dataclass(frozen=True, slots=True)
class SmokeTestOptions:
    """Paths supplied to the hidden ``--smoke-test`` packaging hook."""

    scenario: Path
    output: Path
    timeout_seconds: float = 300.0


def parse_smoke_test_options(
    arguments: Sequence[str],
) -> tuple[SmokeTestOptions | None, list[str]]:
    """Split the hidden smoke-test flags from the arguments Qt should see."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--output", type=Path)
    known, remaining = parser.parse_known_args(arguments)
    if not known.smoke_test:
        return None, list(arguments)
    if known.scenario is None or known.output is None:
        parser.error("--smoke-test requires --scenario and --output")
    return SmokeTestOptions(scenario=known.scenario, output=known.output), remaining


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Return the process-wide :class:`QApplication`, creating it if needed."""
    existing = QApplication.instance()
    if existing is not None:
        if not isinstance(existing, QApplication):  # pragma: no cover - Qt guarantee
            raise RuntimeError("a non-GUI Qt application already exists")
        return existing
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName(APPLICATION_NAME)
    app.setOrganizationName(APPLICATION_NAME)
    app.setApplicationVersion(__version__)
    return app


def run_smoke_test(
    app: QApplication,
    window: MainWindow,
    options: SmokeTestOptions,
) -> int:
    """Load, generate, and export in a frozen GUI process, then exit.

    This is the packaging smoke test, not a user-facing mode. It proves the
    bundle contains the engine, Qt platform plugin, and both translation
    catalogs. The caller must have shown ``window`` already.

    A ``smoke-report.json`` is written to ``options.output`` so the packaging
    script can report startup and generation timing without parsing stdout.
    """
    exit_code = 1
    shown_unix_ns: int | None = None
    report: dict[str, object] = {"ok": False, "error": None, "exported": []}

    def finish(code: int, *, error: str | None = None) -> None:
        nonlocal exit_code
        exit_code = code
        if error is not None:
            _emit(f"smoke: {error}", error=True)
        report.update(
            ok=code == 0,
            error=error,
            window_shown_unix_ns=shown_unix_ns,
            finished_unix_ns=time.time_ns(),
        )
        _write_smoke_report(options.output, report)
        app.quit()

    def fail(message: str) -> None:
        finish(1, error=message)

    def on_succeeded(result: GenerationResult) -> None:
        def export_when_idle() -> None:
            if window.generation_running:
                QTimer.singleShot(10, export_when_idle)
                return
            if not window.export_to_directory(options.output):
                fail(f"export failed: {window.last_error}")
                return
            paths = window.last_export_paths
            missing = [path for path in paths if not path.is_file()]
            if not paths or missing:
                fail(f"export produced no files or missing files: {missing}")
                return
            die_count = sum(lot.die_count for lot in result.lots)
            report.update(
                lots=len(result.lots),
                dies=die_count,
                exported=[str(path) for path in paths],
            )
            _emit(f"smoke: generated lots={len(result.lots)} dies={die_count}")
            for path in paths:
                _emit(f"smoke: exported {path}")
            _emit("smoke: ok")
            finish(0)

        QTimer.singleShot(0, export_when_idle)

    window.generation_succeeded.connect(on_succeeded)
    window.generation_invalid.connect(lambda issues: fail(f"scenario rejected: {issues}"))
    window.generation_error.connect(lambda message: fail(f"generation failed: {message}"))
    window.generation_cancelled.connect(lambda: fail("generation cancelled"))

    if not install_engine_translation("zh_CN"):
        fail("gettext catalog is missing from the bundle")
        return exit_code
    manager = language_manager()
    if not manager.set_language("zh_CN", persist=False):
        fail("Qt translation catalog is missing from the bundle")
        return exit_code
    install_engine_translation("en")
    manager.set_language("en", persist=False)

    if not window.load_path(options.scenario):
        fail(f"cannot load scenario: {options.scenario}")
        return exit_code

    app.processEvents()
    shown_unix_ns = time.time_ns()
    _emit("smoke: started")

    def watchdog() -> None:
        fail(f"timed out after {options.timeout_seconds:.0f}s")

    QTimer.singleShot(int(options.timeout_seconds * 1000), watchdog)
    QTimer.singleShot(0, window.start_generation)
    app.exec()
    return exit_code


def _emit(message: str, *, error: bool = False) -> None:
    """Print when a stream exists.

    Windows GUI-subsystem executables may run without attached stdout/stderr,
    so the smoke test must not depend on printing.
    """
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        print(message, file=stream, flush=True)


def _write_smoke_report(output: Path, report: dict[str, object]) -> None:
    """Write the machine-readable smoke result next to the exported files."""
    try:
        output.mkdir(parents=True, exist_ok=True)
        path = output / "smoke-report.json"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:  # pragma: no cover - diagnostics are best effort
        _emit(f"smoke: cannot write report: {exc}", error=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the desktop application and return its exit code."""
    arguments = list(sys.argv if argv is None else argv)
    smoke_options, qt_arguments = parse_smoke_test_options(arguments)
    app = create_application(qt_arguments)
    settings = QSettings()
    language_manager(app).restore(settings)
    window = MainWindow(settings=settings)
    window.show()
    if smoke_options is not None:
        return run_smoke_test(app, window, smoke_options)
    return int(app.exec())

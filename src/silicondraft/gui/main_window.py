"""Single-window GUI backbone: scenario tree, load/save, generate and cancel."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QProgressBar,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..api import GenerationProgress, generate
from ..dataset import GenerationResult
from ..errors import ScenarioError, ValidationIssue
from ..scenario import (
    PRESET_NAMES,
    Scenario,
    load_scenario,
    save_scenario,
    scenario_from_preset,
)
from .scenario_tree import ScenarioTree
from .worker import GenerateFn, GenerationWorker

DEFAULT_SEED = 20260105


class MainWindow(QMainWindow):
    """The main window; generation runs in a :class:`GenerationWorker` thread."""

    generation_progress = Signal(object)
    generation_succeeded = Signal(object)
    generation_invalid = Signal(object)
    generation_error = Signal(str)
    generation_cancelled = Signal()

    def __init__(
        self,
        *,
        generate_fn: GenerateFn = generate,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._generate_fn = generate_fn
        self._scenario: Scenario | None = None
        self._scenario_path: Path | None = None
        self._worker: GenerationWorker | None = None
        self._worker_settled = False
        self._last_result: GenerationResult | None = None
        self._last_issues: tuple[ValidationIssue, ...] = ()

        self._build_ui()
        self._update_actions()
        self._update_title()

    # -- read-only state exposed to tests and later tickets -----------------

    @property
    def scenario(self) -> Scenario | None:
        """The scenario currently held by the window."""
        return self._scenario

    @property
    def scenario_path(self) -> Path | None:
        """The file the current scenario was loaded from or saved to."""
        return self._scenario_path

    @property
    def generation_running(self) -> bool:
        """Whether a generation worker is active."""
        return self._worker is not None

    @property
    def last_result(self) -> GenerationResult | None:
        """The result of the most recent successful run, if any."""
        return self._last_result

    @property
    def last_issues(self) -> tuple[ValidationIssue, ...]:
        """The issues from the most recent load, save, or generation failure."""
        return self._last_issues

    # -- scenario state -----------------------------------------------------

    def load_path(self, path: str | Path) -> bool:
        """Load and validate a scenario file, showing any issues."""
        if self._worker is not None:
            return False
        file_path = Path(path)
        try:
            scenario = load_scenario(file_path)
        except ScenarioError as exc:
            self._show_issues(
                exc.issues,
                self.tr("Could not load scenario: {path}").format(path=file_path),
            )
            return False
        self.set_scenario(scenario, file_path)
        self.statusBar().showMessage(self.tr("Loaded scenario: {path}").format(path=file_path))
        return True

    def save_to_path(self, path: str | Path) -> bool:
        """Save the current scenario as fully expanded YAML."""
        if self._scenario is None or self._worker is not None:
            return False
        file_path = Path(path)
        try:
            save_scenario(self._scenario, file_path)
        except ScenarioError as exc:
            self._show_issues(
                exc.issues,
                self.tr("Could not save scenario: {path}").format(path=file_path),
            )
            return False
        except OSError as exc:
            self._show_error(self.tr("Could not save scenario: {message}").format(message=exc))
            return False
        self._scenario_path = file_path
        self._clear_issues()
        self._update_title()
        self.statusBar().showMessage(self.tr("Saved scenario: {path}").format(path=file_path))
        return True

    def set_scenario(self, scenario: Scenario, path: str | Path | None = None) -> None:
        """Replace the current scenario and refresh the tree and actions.

        Any result from the previous scenario is discarded so later preview or
        export steps cannot attribute stale data to the new scenario.
        """
        self._scenario = scenario
        self._scenario_path = Path(path) if path is not None else None
        self._last_result = None
        self._clear_issues()
        self.tree.set_scenario(scenario)
        self._sync_preset_combo()
        self._update_title()
        self._update_actions()

    def apply_preset(self, name: str) -> bool:
        """Replace the scenario with a fresh scenario built from ``name``."""
        if self._worker is not None or name not in PRESET_NAMES:
            self._sync_preset_combo()
            return False
        seed = self._scenario.seed if self._scenario is not None else DEFAULT_SEED
        try:
            scenario = scenario_from_preset(name, seed)
        except ScenarioError as exc:
            self._show_issues(
                exc.issues,
                self.tr("Could not apply preset: {name}").format(name=name),
            )
            self._sync_preset_combo()
            return False
        self.set_scenario(scenario)
        self.statusBar().showMessage(self.tr("Applied preset: {name}").format(name=name))
        return True

    # -- generation ---------------------------------------------------------

    def start_generation(self) -> bool:
        """Start generating the current scenario in a worker thread."""
        if self._scenario is None or self._worker is not None:
            return False
        self._clear_issues()
        self._last_result = None
        self._worker_settled = False
        self.progress_bar.setRange(0, self._scenario.lots.wafer_count)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        worker = GenerationWorker(self._scenario, self._generate_fn, self)
        worker.progress.connect(self._on_progress)
        worker.succeeded.connect(self._on_succeeded)
        worker.invalid.connect(self._on_invalid)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self._update_actions()
        self.statusBar().showMessage(self.tr("Generating..."))
        worker.start()
        return True

    def cancel_generation(self) -> None:
        """Ask the active worker to stop before the next wafer."""
        if self._worker is None or self._worker_settled:
            return
        self.cancel_action.setEnabled(False)
        self.statusBar().showMessage(self.tr("Cancelling..."))
        self._worker.cancel()

    # -- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        self.tree = ScenarioTree(self)

        self.issues_label = QLabel(self.tr("Configuration issues"), self)
        self.issues_list = QListWidget(self)
        issues_panel = QWidget(self)
        issues_layout = QVBoxLayout(issues_panel)
        issues_layout.addWidget(self.issues_label)
        issues_layout.addWidget(self.issues_list)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.tree)
        splitter.addWidget(issues_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        self.open_action = QAction(self.tr("Open..."), self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._open_scenario)

        self.save_action = QAction(self.tr("Save"), self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._save_scenario)

        self.save_as_action = QAction(self.tr("Save As..."), self)
        self.save_as_action.triggered.connect(self._save_scenario_as)

        self.generate_action = QAction(self.tr("Generate"), self)
        self.generate_action.triggered.connect(self.start_generation)

        self.cancel_action = QAction(self.tr("Cancel"), self)
        self.cancel_action.triggered.connect(self.cancel_generation)

        toolbar = QToolBar(self.tr("Main"), self)
        toolbar.setMovable(False)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.save_as_action)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel(self.tr("Preset:"), toolbar))
        self.preset_combo = QComboBox(toolbar)
        self.preset_combo.addItem(self.tr("Custom"), None)
        for name in PRESET_NAMES:
            self.preset_combo.addItem(name, name)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        toolbar.addWidget(self.preset_combo)
        toolbar.addSeparator()
        toolbar.addAction(self.generate_action)
        toolbar.addAction(self.cancel_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        file_menu = self.menuBar().addMenu(self.tr("&File"))
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        exit_action = QAction(self.tr("Exit"), self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setFormat(self.tr("%v / %m"))
        self.progress_bar.setMaximumWidth(280)
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.statusBar().showMessage(self.tr("Ready"))

        self.resize(1000, 700)
        self._sync_preset_combo()

    # -- worker signal handlers ---------------------------------------------

    def _on_progress(self, progress: GenerationProgress) -> None:
        self.progress_bar.setRange(0, progress.total_wafers)
        self.progress_bar.setValue(progress.completed_wafers)
        self.statusBar().showMessage(
            self.tr("Generating {lot_id} / {wafer_id}: {completed} of {total} wafers").format(
                lot_id=progress.lot_id,
                wafer_id=progress.wafer_id,
                completed=progress.completed_wafers,
                total=progress.total_wafers,
            )
        )
        self.generation_progress.emit(progress)

    def _on_succeeded(self, result: GenerationResult) -> None:
        self._worker_settled = True
        self._last_result = result
        wafer_count = sum(len(lot.wafers) for lot in result.lots)
        die_count = sum(lot.die_count for lot in result.lots)
        self.statusBar().showMessage(
            self.tr("Generation complete: {lots} lot(s), {wafers} wafer(s), {dies} die(s)").format(
                lots=len(result.lots), wafers=wafer_count, dies=die_count
            )
        )
        self.generation_succeeded.emit(result)

    def _on_invalid(self, issues: tuple[ValidationIssue, ...]) -> None:
        self._worker_settled = True
        self._show_issues(
            issues,
            self.tr("Generation failed: the scenario has {count} issue(s)").format(
                count=len(issues)
            ),
        )
        self.generation_invalid.emit(issues)

    def _on_failed(self, message: str) -> None:
        self._worker_settled = True
        self._show_error(self.tr("Generation failed: {message}").format(message=message))
        self.generation_error.emit(message)

    def _on_cancelled(self) -> None:
        self._worker_settled = True
        self.statusBar().showMessage(self.tr("Generation cancelled."))
        self.generation_cancelled.emit()

    def _on_worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self.progress_bar.setVisible(False)
        self._update_actions()

    # -- dialogs and state --------------------------------------------------

    def _open_scenario(self) -> None:
        start_dir = str(self._scenario_path.parent) if self._scenario_path else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Open Scenario"),
            start_dir,
            self.tr("Scenario YAML (*.yaml *.yml);;All files (*)"),
        )
        if path:
            self.load_path(path)

    def _save_scenario(self) -> None:
        if self._scenario_path is not None:
            self.save_to_path(self._scenario_path)
        else:
            self._save_scenario_as()

    def _save_scenario_as(self) -> None:
        suggested = str(self._scenario_path) if self._scenario_path else "scenario.yaml"
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Scenario"),
            suggested,
            self.tr("Scenario YAML (*.yaml *.yml);;All files (*)"),
        )
        if path:
            self.save_to_path(path)

    def _on_preset_changed(self, index: int) -> None:
        name = self.preset_combo.itemData(index)
        if not isinstance(name, str):
            self._sync_preset_combo()
            return
        self.apply_preset(name)

    def _sync_preset_combo(self) -> None:
        preset = self._scenario.preset if self._scenario is not None else None
        index = self.preset_combo.findData(preset)
        self.preset_combo.blockSignals(True)
        try:
            self.preset_combo.setCurrentIndex(max(index, 0))
        finally:
            self.preset_combo.blockSignals(False)

    def _show_issues(self, issues: Sequence[ValidationIssue], message: str) -> None:
        self._last_issues = tuple(issues)
        self.issues_list.clear()
        for issue in issues:
            self.issues_list.addItem(f"{issue.path}: {issue.message} [{issue.code}]")
        self.statusBar().showMessage(message)

    def _show_error(self, message: str) -> None:
        self._last_issues = ()
        self.issues_list.clear()
        self.issues_list.addItem(message)
        self.statusBar().showMessage(message)

    def _clear_issues(self) -> None:
        self._last_issues = ()
        self.issues_list.clear()

    def _update_actions(self) -> None:
        running = self._worker is not None
        has_scenario = self._scenario is not None
        self.open_action.setEnabled(not running)
        self.save_action.setEnabled(has_scenario and not running)
        self.save_as_action.setEnabled(has_scenario and not running)
        self.generate_action.setEnabled(has_scenario and not running)
        self.cancel_action.setEnabled(running)
        self.preset_combo.setEnabled(not running)

    def _update_title(self) -> None:
        name = self._scenario_path.name if self._scenario_path else self.tr("Untitled")
        self.setWindowTitle(
            self.tr("SiliconDraft {version} - {name}").format(version=__version__, name=name)
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait()
            self._worker.deleteLater()
            self._worker = None
        super().closeEvent(event)

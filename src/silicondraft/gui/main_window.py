"""Single-window GUI backbone: scenario tree, load/save, generate and cancel."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QProgressBar,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..api import GenerationProgress, export, generate
from ..dataset import GenerationResult
from ..errors import ScenarioError, ValidationIssue
from ..scenario import (
    PRESET_NAMES,
    Scenario,
    load_scenario,
    save_scenario,
    scenario_from_preset,
)
from ..scenario.models import CsvLayout
from .correlation import CorrelationPanel
from .distribution import DistributionPanel
from .export_dialog import ExportDialog
from .i18n import SUPPORTED_LANGUAGES, language_label, language_manager
from .result_table import ResultsPanel
from .scenario_tree import ScenarioTree
from .trend import TrendPanel
from .wafer_map import WaferMapPanel
from .worker import GenerateFn, GenerationWorker
from .yaml_editor import YamlEditorDialog

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
        self._language_manager = language_manager()
        self._language_manager.language_changed.connect(self.retranslate_ui)
        self._generate_fn = generate_fn
        self._scenario: Scenario | None = None
        self._scenario_path: Path | None = None
        self._worker: GenerationWorker | None = None
        self._worker_settled = False
        self._last_result: GenerationResult | None = None
        self._last_issues: tuple[ValidationIssue, ...] = ()
        self._last_export_paths: tuple[Path, ...] = ()
        self._status_factory: Callable[[], str] | None = None
        self._error_factory: Callable[[], str] | None = None

        self._build_ui()
        self._sync_language_actions()
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
        """The issues from the most recent load, save, generation, or export failure."""
        return self._last_issues

    @property
    def last_export_paths(self) -> tuple[Path, ...]:
        """The files written by the most recent successful export."""
        return self._last_export_paths

    @property
    def language(self) -> str:
        """The UI language code currently installed."""
        return self._language_manager.language

    def set_language(self, language: str) -> bool:
        """Switch the UI language live and return whether the catalog loaded."""
        return self._language_manager.set_language(language)

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
                lambda: self.tr("Could not load scenario: {path}").format(path=file_path),
            )
            return False
        self.set_scenario(scenario, file_path)
        self._set_status(lambda: self.tr("Loaded scenario: {path}").format(path=file_path))
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
                lambda: self.tr("Could not save scenario: {path}").format(path=file_path),
            )
            return False
        except OSError as exc:
            error_text = str(exc)

            def save_error() -> str:
                return self.tr("Could not save scenario: {message}").format(message=error_text)

            self._show_error(save_error)
            return False
        self._scenario_path = file_path
        self._clear_issues()
        self._update_title()
        self._set_status(lambda: self.tr("Saved scenario: {path}").format(path=file_path))
        return True

    def set_scenario(self, scenario: Scenario, path: str | Path | None = None) -> None:
        """Replace the current scenario and refresh the tree and actions.

        Any result from the previous scenario is discarded so later preview or
        export steps cannot attribute stale data to the new scenario.
        """
        self._scenario = scenario
        self._scenario_path = Path(path) if path is not None else None
        self._last_result = None
        self._last_export_paths = ()
        self._set_preview_result(None)
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
                lambda: self.tr("Could not apply preset: {name}").format(name=name),
            )
            self._sync_preset_combo()
            return False
        self.set_scenario(scenario)
        self._set_status(lambda: self.tr("Applied preset: {name}").format(name=name))
        return True

    # -- generation ---------------------------------------------------------

    def start_generation(self) -> bool:
        """Start generating the current scenario in a worker thread."""
        if self._scenario is None or self._worker is not None:
            return False
        self._clear_issues()
        self._last_result = None
        self._last_export_paths = ()
        self._set_preview_result(None)
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
        self._set_status(lambda: self.tr("Generating..."))
        worker.start()
        return True

    def cancel_generation(self) -> None:
        """Ask the active worker to stop before the next wafer."""
        if self._worker is None or self._worker_settled:
            return
        self.cancel_action.setEnabled(False)
        self._set_status(lambda: self.tr("Cancelling..."))
        self._worker.cancel()

    # -- export -------------------------------------------------------------

    def export_to_directory(
        self,
        out_dir: str | Path,
        *,
        cp_csv_layout: CsvLayout | None = None,
        include_ground_truth: bool | None = None,
        include_die_truth: bool | None = None,
    ) -> bool:
        """Export the current result's CSV files and report the outcome.

        The keyword overrides apply to this export run only; the GUI passes the
        choices from :class:`ExportDialog` without rewriting the scenario.
        """
        result = self._last_result
        if result is None or self._worker is not None:
            return False
        options = result.scenario.export
        if not (options.cp_csv or options.wat_csv):
            self._last_export_paths = ()
            self._show_error(
                lambda: self.tr("Export failed: {message}").format(
                    message=self.tr("the scenario has no CSV export enabled.")
                )
            )
            return False
        try:
            paths = export(
                result,
                out_dir,
                formats=("csv",),
                cp_csv_layout=cp_csv_layout,
                include_ground_truth=include_ground_truth,
                include_die_truth=include_die_truth,
            )
        except Exception as exc:
            self._last_export_paths = ()
            error_text = str(exc)

            def export_error() -> str:
                return self.tr("Export failed: {message}").format(message=error_text)

            self._show_error(export_error)
            return False
        self._last_export_paths = paths
        self._clear_issues()
        self._set_status(
            lambda: self.tr("Exported {count} file(s) to {path}").format(
                count=len(paths), path=out_dir
            )
        )
        return True

    @property
    def _can_export(self) -> bool:
        return self._last_result is not None and self._worker is None

    # -- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        self.tree = ScenarioTree(self)

        self.issues_label = QLabel(self)
        self.issues_list = QListWidget(self)
        self.issues_panel = QWidget(self)
        issues_layout = QVBoxLayout(self.issues_panel)
        issues_layout.addWidget(self.issues_label)
        issues_layout.addWidget(self.issues_list)

        self.wafer_map_panel = WaferMapPanel(self)
        self.distribution_panel = DistributionPanel(self)
        self.correlation_panel = CorrelationPanel(self)
        self.trend_panel = TrendPanel(self)
        self.results_panel = ResultsPanel(self)
        self.preview_tabs = QTabWidget(self)
        for panel in (
            self.wafer_map_panel,
            self.distribution_panel,
            self.correlation_panel,
            self.trend_panel,
            self.results_panel,
            self.issues_panel,
        ):
            self.preview_tabs.addTab(panel, "")

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.preview_tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        self.open_action = QAction(self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._open_scenario)

        self.save_action = QAction(self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._save_scenario)

        self.save_as_action = QAction(self)
        self.save_as_action.triggered.connect(self._save_scenario_as)

        self.yaml_editor_action = QAction(self)
        self.yaml_editor_action.triggered.connect(self._open_yaml_editor)

        self.generate_action = QAction(self)
        self.generate_action.triggered.connect(self.start_generation)

        self.cancel_action = QAction(self)
        self.cancel_action.triggered.connect(self.cancel_generation)

        self.export_action = QAction(self)
        self.export_action.triggered.connect(self._open_export_dialog)

        self.exit_action = QAction(self)
        self.exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.exit_action.triggered.connect(self.close)

        self.toolbar = QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.addAction(self.open_action)
        self.toolbar.addAction(self.save_action)
        self.toolbar.addAction(self.save_as_action)
        self.toolbar.addAction(self.yaml_editor_action)
        self.toolbar.addSeparator()
        self.preset_label = QLabel(self.toolbar)
        self.toolbar.addWidget(self.preset_label)
        self.preset_combo = QComboBox(self.toolbar)
        self.preset_combo.addItem("", None)
        for name in PRESET_NAMES:
            self.preset_combo.addItem(name, name)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.toolbar.addWidget(self.preset_combo)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.generate_action)
        self.toolbar.addAction(self.cancel_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.export_action)
        self.toolbar.addSeparator()
        self.language_label = QLabel(self.toolbar)
        self.toolbar.addWidget(self.language_label)
        self.language_combo = QComboBox(self.toolbar)
        for code in SUPPORTED_LANGUAGES:
            self.language_combo.addItem(language_label(code), code)
        self.language_combo.currentIndexChanged.connect(self._on_language_combo_changed)
        self.toolbar.addWidget(self.language_combo)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.file_menu = self.menuBar().addMenu("")
        self.file_menu.addAction(self.open_action)
        self.file_menu.addAction(self.save_action)
        self.file_menu.addAction(self.save_as_action)
        self.file_menu.addAction(self.yaml_editor_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.exit_action)

        self.settings_menu = self.menuBar().addMenu("")
        self.language_menu = self.settings_menu.addMenu("")
        self.language_action_group = QActionGroup(self)
        self.language_action_group.setExclusive(True)
        self.language_actions: dict[str, QAction] = {}
        for code in SUPPORTED_LANGUAGES:
            action = QAction(language_label(code), self)
            action.setCheckable(True)
            action.setData(code)
            action.triggered.connect(
                lambda _checked=False, language=code: self._activate_language(language)
            )
            self.language_action_group.addAction(action)
            self.language_menu.addAction(action)
            self.language_actions[code] = action

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMaximumWidth(280)
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self._set_status(lambda: self.tr("Ready"))

        self.resize(1000, 700)
        self._sync_preset_combo()
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Re-apply every user-visible string in the current language."""
        self.open_action.setText(self.tr("Open..."))
        self.save_action.setText(self.tr("Save"))
        self.save_as_action.setText(self.tr("Save As..."))
        self.yaml_editor_action.setText(self.tr("YAML Editor..."))
        self.generate_action.setText(self.tr("Generate"))
        self.cancel_action.setText(self.tr("Cancel"))
        self.export_action.setText(self.tr("Export..."))
        self.exit_action.setText(self.tr("Exit"))
        self.toolbar.setWindowTitle(self.tr("Main"))
        self.preset_label.setText(self.tr("Preset:"))
        self.language_label.setText(self.tr("Language:"))
        self.preset_combo.setItemText(0, self.tr("Custom"))
        self.file_menu.setTitle(self.tr("&File"))
        self.settings_menu.setTitle(self.tr("&Settings"))
        self.language_menu.setTitle(self.tr("Language"))
        self.issues_label.setText(self.tr("Configuration issues"))
        self.progress_bar.setFormat("%v / %m")
        tab_titles = (
            self.tr("Wafer Map"),
            self.tr("Distribution"),
            self.tr("Correlation"),
            self.tr("Trend"),
            self.tr("Results"),
            self.tr("Issues"),
        )
        for index, title in enumerate(tab_titles):
            self.preview_tabs.setTabText(index, title)
        self.tree.retranslate_ui()
        self.wafer_map_panel.retranslate_ui()
        self.distribution_panel.retranslate_ui()
        self.correlation_panel.retranslate_ui()
        self.trend_panel.retranslate_ui()
        self.results_panel.retranslate_ui()
        if self._last_issues:
            self._fill_issue_list()
        elif self._error_factory is not None:
            self._fill_error(self._error_factory())
        self._refresh_status()
        self._sync_language_actions()
        self._update_title()

    def _sync_language_actions(self) -> None:
        for code, action in self.language_actions.items():
            action.setChecked(code == self.language)
        index = self.language_combo.findData(self.language)
        if index >= 0:
            self.language_combo.blockSignals(True)
            try:
                self.language_combo.setCurrentIndex(index)
            finally:
                self.language_combo.blockSignals(False)

    def _on_language_combo_changed(self, index: int) -> None:
        code = self.language_combo.itemData(index)
        if isinstance(code, str):
            self._activate_language(code)
        else:
            self._sync_language_actions()

    def _activate_language(self, language: str) -> None:
        if not self.set_language(language):
            self._sync_language_actions()

    # -- worker signal handlers ---------------------------------------------

    def _on_progress(self, progress: GenerationProgress) -> None:
        self.progress_bar.setRange(0, progress.total_wafers)
        self.progress_bar.setValue(progress.completed_wafers)
        self._set_status(
            lambda: self.tr(
                "Generating {lot_id} / {wafer_id}: {completed} of {total} wafers"
            ).format(
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
        self._set_preview_result(result)
        self.preview_tabs.setCurrentWidget(self.wafer_map_panel)
        self._set_status(
            lambda: self.tr(
                "Generation complete: {lots} lot(s), {wafers} wafer(s), {dies} die(s)"
            ).format(lots=len(result.lots), wafers=wafer_count, dies=die_count)
        )
        self.generation_succeeded.emit(result)

    def _on_invalid(self, issues: tuple[ValidationIssue, ...]) -> None:
        self._worker_settled = True
        self._show_issues(
            issues,
            lambda: self.tr("Generation failed: the scenario has {count} issue(s)").format(
                count=len(issues)
            ),
        )
        self.generation_invalid.emit(issues)

    def _on_failed(self, message: str) -> None:
        self._worker_settled = True
        self._show_error(lambda: self.tr("Generation failed: {message}").format(message=message))
        self.generation_error.emit(message)

    def _on_cancelled(self) -> None:
        self._worker_settled = True
        self._set_status(lambda: self.tr("Generation cancelled."))
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

    def _open_yaml_editor(self) -> None:
        if self._scenario is None or self._worker is not None:
            return
        dialog = YamlEditorDialog(self._scenario, self._scenario_path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        saved_path = dialog.saved_path
        if saved_path is not None and self.load_path(saved_path):
            return
        if dialog.saved_scenario is not None:
            self.set_scenario(dialog.saved_scenario, saved_path)

    def _open_export_dialog(self) -> None:
        if not self._can_export:
            return
        result = self._last_result
        if result is None:  # pragma: no cover - guarded by _can_export
            return
        dialog = ExportDialog(
            self._default_export_dir(), self, export_options=result.scenario.export
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        out_dir = dialog.output_dir()
        if out_dir is not None:
            self.export_to_directory(
                out_dir,
                cp_csv_layout=dialog.cp_csv_layout(),
                include_ground_truth=dialog.include_ground_truth(),
                include_die_truth=dialog.include_die_truth(),
            )

    def _default_export_dir(self) -> Path:
        if self._scenario_path is not None:
            return self._scenario_path.parent
        return Path.cwd()

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

    def _show_issues(self, issues: Sequence[ValidationIssue], message: Callable[[], str]) -> None:
        self._last_issues = tuple(issues)
        self._error_factory = None
        self._fill_issue_list()
        self.preview_tabs.setCurrentWidget(self.issues_panel)
        self._set_status(message)

    def _show_error(self, message: Callable[[], str]) -> None:
        self._last_issues = ()
        self._error_factory = message
        self._fill_error(message())
        self.preview_tabs.setCurrentWidget(self.issues_panel)
        self._set_status(message)

    def _fill_issue_list(self) -> None:
        self.issues_list.clear()
        for issue in self._last_issues:
            self.issues_list.addItem(f"{issue.path}: {issue.message} [{issue.code}]")

    def _fill_error(self, message: str) -> None:
        self.issues_list.clear()
        self.issues_list.addItem(message)

    def _set_status(self, message: Callable[[], str]) -> None:
        self._status_factory = message
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self._status_factory is not None:
            self.statusBar().showMessage(self._status_factory())

    def _clear_issues(self) -> None:
        self._last_issues = ()
        self._error_factory = None
        self.issues_list.clear()

    def _set_preview_result(self, result: GenerationResult | None) -> None:
        self.wafer_map_panel.set_result(result)
        self.distribution_panel.set_result(result)
        self.correlation_panel.set_result(result)
        self.trend_panel.set_result(result)
        self.results_panel.set_result(result)

    def _update_actions(self) -> None:
        running = self._worker is not None
        has_scenario = self._scenario is not None
        self.open_action.setEnabled(not running)
        self.save_action.setEnabled(has_scenario and not running)
        self.save_as_action.setEnabled(has_scenario and not running)
        self.yaml_editor_action.setEnabled(has_scenario and not running)
        self.generate_action.setEnabled(has_scenario and not running)
        self.cancel_action.setEnabled(running)
        self.export_action.setEnabled(self._can_export and not running)
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

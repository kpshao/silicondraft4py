"""Dialog for editing the full scenario YAML with in-place validation."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from PySide6.QtGui import QColor, QFontDatabase, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..errors import ScenarioError, ValidationIssue
from ..scenario import Scenario, save_scenario, validate_scenario_text
from ..scenario.loader import parse_scenario_text
from ..scenario.writer import scenario_yaml

_YAML_PARSE_LOCATION = re.compile(r"line (\d+), column (\d+)")
_ARRAY_INDEX = re.compile(r"\[\d+\]$")


@dataclass(frozen=True, slots=True)
class IssueLocation:
    """A one-based line and column in the edited YAML text."""

    line: int
    column: int


def locate_issue(text: str, issue: ValidationIssue) -> IssueLocation | None:
    """Map a validation issue path onto the line holding that field.

    YAML parse errors carry their own line and column in the message. Semantic
    issues are mapped by composing the text into a node tree and recording the
    start mark of each dotted path, falling back to the closest enclosing path
    (or the document root) when the exact field is absent.
    """
    match = _YAML_PARSE_LOCATION.search(issue.message)
    if issue.code == "YAML_PARSE_ERROR" and match is not None:
        return IssueLocation(int(match.group(1)), int(match.group(2)))

    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        return None
    if root is None:
        return None

    marks: dict[str, tuple[int, int]] = {}
    _collect_marks(root, "", marks)
    path = issue.path
    while path and path not in marks:
        path = _parent_path(path)
    if path not in marks:
        path = ""
    line, column = marks[path]
    return IssueLocation(line + 1, column + 1)


def _parent_path(path: str) -> str:
    array_match = _ARRAY_INDEX.search(path)
    if array_match is not None:
        return path[: array_match.start()]
    if "." in path:
        return path.rsplit(".", 1)[0]
    return ""


def _collect_marks(node: yaml.Node, path: str, marks: dict[str, tuple[int, int]]) -> None:
    marks[path] = (node.start_mark.line, node.start_mark.column)
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            key = str(key_node.value)
            _collect_marks(value_node, f"{path}.{key}" if path else key, marks)
    elif isinstance(node, yaml.SequenceNode):
        for index, child in enumerate(node.value):
            _collect_marks(child, f"{path}[{index}]", marks)


class YamlEditorDialog(QDialog):
    """Edit, validate, and save the complete scenario as YAML.

    The editor starts from the fully expanded scenario with ``preset`` cleared,
    so an edit that deletes a preset-derived section is authoritative instead
    of being merged back on load. Saving validates first, writes the fully
    expanded scenario, and only then closes the dialog, so a file accepted
    here always loads in the GUI and the CLI.
    """

    def __init__(
        self,
        scenario: Scenario,
        path: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Scenario YAML Editor"))
        self._path = Path(path) if path is not None else None
        self._saved_scenario: Scenario | None = None
        self._issues: tuple[ValidationIssue, ...] = ()

        self.editor = QPlainTextEdit(self)
        self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.editor.setTabStopDistance(32)
        self.editor.setPlainText(scenario_yaml(scenario, include_preset=False))

        self.issues_label = QLabel(self.tr("Issues"), self)
        self.issues_list = QListWidget(self)
        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)

        self.validate_button = QPushButton(self.tr("Validate"), self)
        self.save_button = QPushButton(self.tr("Save"), self)
        self.cancel_button = QPushButton(self.tr("Cancel"), self)
        self.validate_button.clicked.connect(self.validate)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.issues_label)
        layout.addWidget(self.issues_list)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)
        self.resize(760, 680)

    # -- read-only state ----------------------------------------------------

    @property
    def issues(self) -> tuple[ValidationIssue, ...]:
        """Issues from the most recent validation."""
        return self._issues

    @property
    def saved_scenario(self) -> Scenario | None:
        """The scenario written by the last successful save."""
        return self._saved_scenario

    @property
    def saved_path(self) -> Path | None:
        """The file written by the last successful save."""
        return self._path if self._saved_scenario is not None else None

    # -- editing ------------------------------------------------------------

    def text(self) -> str:
        """The YAML text currently in the editor."""
        return self.editor.toPlainText()

    def set_text(self, text: str) -> None:
        """Replace the editor contents and clear stale validation feedback."""
        self.editor.setPlainText(text)
        self.editor.setExtraSelections([])
        self._issues = ()
        self.issues_list.clear()
        self.status_label.clear()

    def validate(self) -> bool:
        """Validate the edited text and move the cursor to the first issue."""
        result = validate_scenario_text(self.text())
        self._issues = result.issues
        self._show_issues(result.issues)
        if result.ok:
            self.editor.setExtraSelections([])
            self.status_label.setText(self.tr("Scenario is valid."))
            return True
        self.status_label.setText(
            self.tr("Scenario has {count} issue(s).").format(count=len(result.issues))
        )
        if result.issues:
            self._locate_issue(result.issues[0])
        return False

    def save_to_path(self, path: str | Path) -> bool:
        """Validate and write the fully expanded scenario to ``path``."""
        self._saved_scenario = None
        if not self.validate():
            return False
        try:
            scenario = parse_scenario_text(self.text())
            saved_path = save_scenario(scenario, path)
        except ScenarioError as exc:
            self._issues = exc.issues
            self._show_issues(exc.issues)
            self.status_label.setText(self.tr("Could not save the scenario."))
            return False
        except OSError as exc:
            self._issues = ()
            self.issues_list.clear()
            message = self.tr("Could not save scenario: {message}").format(message=exc)
            self.issues_list.addItem(message)
            self.status_label.setText(message)
            return False
        self._saved_scenario = scenario
        self._path = saved_path
        self.status_label.setText(self.tr("Saved scenario: {path}").format(path=saved_path))
        return True

    # -- dialog actions -----------------------------------------------------

    def _show_issues(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues_list.clear()
        for issue in issues:
            self.issues_list.addItem(f"{issue.path}: {issue.message} [{issue.code}]")

    def _save(self) -> None:
        path = self._path
        if path is None:
            chosen, _ = QFileDialog.getSaveFileName(
                self,
                self.tr("Save Scenario"),
                "scenario.yaml",
                self.tr("Scenario YAML (*.yaml *.yml);;All files (*)"),
            )
            if not chosen:
                return
            path = Path(chosen)
        if self.save_to_path(path):
            self.accept()

    def _locate_issue(self, issue: ValidationIssue) -> None:
        location = locate_issue(self.text(), issue)
        if location is None:
            return
        document = self.editor.document()
        block = document.findBlockByNumber(location.line - 1)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + min(location.column - 1, len(block.text())))
        self.editor.setTextCursor(cursor)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(QColor("#fff59d"))
        selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        self.editor.setExtraSelections([selection])
        self.editor.ensureCursorVisible()


__all__ = ["IssueLocation", "YamlEditorDialog", "locate_issue"]

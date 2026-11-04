"""Dialog collecting the output directory and per-run export options."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..scenario.models import CsvLayout, ExportOptions


class ExportDialog(QDialog):
    """Let the user choose where the current result is written.

    V1 exports CSV only, so the format is shown but not selectable; the format
    picker arrives with the STDF writer. The dialog validates its inputs
    itself so an empty directory leaves it open with a readable message.

    The CSV layout and ground-truth choices start from the scenario's export
    options and override them for this export run only.
    """

    def __init__(
        self,
        output_dir: str | Path = "",
        parent: QWidget | None = None,
        *,
        export_options: ExportOptions | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export Data"))
        options = export_options if export_options is not None else ExportOptions()

        self.directory_edit = QLineEdit(str(output_dir), self)
        self.directory_edit.setPlaceholderText(self.tr("Output directory"))
        browse_button = QPushButton(self.tr("Browse..."), self)
        browse_button.clicked.connect(self._browse)

        directory_row = QHBoxLayout()
        directory_row.addWidget(self.directory_edit)
        directory_row.addWidget(browse_button)

        self.format_label = QLabel(self.tr("CSV"), self)

        self.layout_combo = QComboBox(self)
        for label, layout_name in (
            (self.tr("One CSV per lot (long)"), "long"),
            (self.tr("One CSV per wafer (blocks)"), "blocks"),
            (self.tr("Both layouts"), "both"),
        ):
            self.layout_combo.addItem(label, layout_name)
        self.set_cp_csv_layout(options.cp_csv_layout)

        self.ground_truth_checkbox = QCheckBox(self.tr("Write ground truth"), self)
        self.ground_truth_checkbox.setChecked(options.ground_truth)
        self.ground_truth_checkbox.toggled.connect(self._sync_truth_controls)
        self.die_truth_checkbox = QCheckBox(self.tr("Write per-die ground truth"), self)
        self.die_truth_checkbox.setChecked(options.ground_truth and options.include_die_truth)
        self._sync_truth_controls()

        self.error_label = QLabel("", self)
        self.error_label.setWordWrap(True)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        export_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if export_button is not None:
            export_button.setText(self.tr("Export"))
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        content_layout = QVBoxLayout(self)
        content_layout.addWidget(QLabel(self.tr("Output directory"), self))
        content_layout.addLayout(directory_row)
        content_layout.addWidget(QLabel(self.tr("Format"), self))
        content_layout.addWidget(self.format_label)
        content_layout.addWidget(QLabel(self.tr("CP CSV layout"), self))
        content_layout.addWidget(self.layout_combo)
        content_layout.addWidget(self.ground_truth_checkbox)
        content_layout.addWidget(self.die_truth_checkbox)
        content_layout.addWidget(self.error_label)
        content_layout.addWidget(self._buttons)

    def output_dir(self) -> Path | None:
        """The chosen directory, or ``None`` when the field is empty."""
        text = self.directory_edit.text().strip()
        return Path(text) if text else None

    def set_output_dir(self, path: str | Path) -> None:
        """Fill the directory field."""
        self.directory_edit.setText(str(path))

    def cp_csv_layout(self) -> CsvLayout:
        """The CP CSV layout selected for this run."""
        data = self.layout_combo.currentData()
        if data in ("long", "blocks", "both"):
            return cast(CsvLayout, data)
        return "long"

    def set_cp_csv_layout(self, layout: str) -> bool:
        """Select a CP CSV layout; reject values the scenario schema does not know."""
        index = self.layout_combo.findData(layout)
        if index < 0:
            return False
        self.layout_combo.setCurrentIndex(index)
        return True

    def include_ground_truth(self) -> bool:
        """Whether the ground truth manifest is written for this run."""
        return self.ground_truth_checkbox.isChecked()

    def set_include_ground_truth(self, enabled: bool) -> None:
        """Enable or disable ground truth output."""
        self.ground_truth_checkbox.setChecked(enabled)
        self._sync_truth_controls()

    def include_die_truth(self) -> bool:
        """Whether per-die truth files are written for this run."""
        return self.include_ground_truth() and self.die_truth_checkbox.isChecked()

    def set_include_die_truth(self, enabled: bool) -> None:
        """Enable or disable per-die truth output, enabling ground truth as needed."""
        if enabled:
            self.ground_truth_checkbox.setChecked(True)
        self.die_truth_checkbox.setChecked(enabled)
        self._sync_truth_controls()

    def accept(self) -> None:
        """Accept only a non-empty output directory."""
        if self.output_dir() is None:
            self.error_label.setText(self.tr("Choose an output directory."))
            return
        self.error_label.clear()
        super().accept()

    def _sync_truth_controls(self) -> None:
        self.die_truth_checkbox.setEnabled(self.include_ground_truth())

    def _browse(self) -> None:
        start_dir = str(self.output_dir() or "")
        chosen = QFileDialog.getExistingDirectory(
            self, self.tr("Select Output Directory"), start_dir
        )
        if chosen:
            self.set_output_dir(chosen)

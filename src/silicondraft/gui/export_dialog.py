"""Dialog collecting the output directory and per-run export options."""

from __future__ import annotations

from collections.abc import Sequence
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

from ..scenario.models import (
    CSV_LAYOUTS,
    EXPORT_FORMATS,
    CsvLayout,
    ExportFormat,
    ExportOptions,
)
from .i18n import language_manager


class ExportDialog(QDialog):
    """Let the user choose where the current result is written.

    The format, CSV layout, and ground-truth choices start from the scenario's
    export options and override them for this export run only; a format the
    scenario disables can still be enabled here. The dialog validates its
    inputs itself so an empty directory or an empty format selection leaves it
    open with a readable message.
    """

    def __init__(
        self,
        output_dir: str | Path = "",
        parent: QWidget | None = None,
        *,
        export_options: ExportOptions | None = None,
    ) -> None:
        super().__init__(parent)
        self._language_manager = language_manager()
        self._language_manager.language_changed.connect(self.retranslate_ui)
        options = export_options if export_options is not None else ExportOptions()

        self.directory_edit = QLineEdit(str(output_dir), self)
        self.browse_button = QPushButton(self)
        self.browse_button.clicked.connect(self._browse)

        directory_row = QHBoxLayout()
        directory_row.addWidget(self.directory_edit)
        directory_row.addWidget(self.browse_button)

        self.output_label = QLabel(self)
        self.format_caption = QLabel(self)
        enabled_formats = set(options.enabled_formats())
        self.stdf_checkbox = QCheckBox(self)
        self.stdf_checkbox.setChecked("stdf" in enabled_formats)
        self.csv_checkbox = QCheckBox(self)
        self.csv_checkbox.setChecked("csv" in enabled_formats)
        self.layout_caption = QLabel(self)

        self.layout_combo = QComboBox(self)
        for layout_name in ("long", "blocks", "both"):
            self.layout_combo.addItem("", layout_name)
        self.set_cp_csv_layout(options.cp_csv_layout)

        self.ground_truth_checkbox = QCheckBox(self)
        self.ground_truth_checkbox.setChecked(options.ground_truth)
        self.ground_truth_checkbox.toggled.connect(self._sync_truth_controls)
        self.die_truth_checkbox = QCheckBox(self)
        self.die_truth_checkbox.setChecked(options.ground_truth and options.include_die_truth)
        self._sync_truth_controls()

        self.error_label = QLabel("", self)
        self.error_label.setWordWrap(True)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        content_layout = QVBoxLayout(self)
        content_layout.addWidget(self.output_label)
        content_layout.addLayout(directory_row)
        content_layout.addWidget(self.format_caption)
        content_layout.addWidget(self.stdf_checkbox)
        content_layout.addWidget(self.csv_checkbox)
        content_layout.addWidget(self.layout_caption)
        content_layout.addWidget(self.layout_combo)
        content_layout.addWidget(self.ground_truth_checkbox)
        content_layout.addWidget(self.die_truth_checkbox)
        content_layout.addWidget(self.error_label)
        content_layout.addWidget(self._buttons)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Re-apply every user-visible string in the current language."""
        self.setWindowTitle(self.tr("Export Data"))
        self.directory_edit.setPlaceholderText(self.tr("Output directory"))
        self.browse_button.setText(self.tr("Browse..."))
        self.output_label.setText(self.tr("Output directory"))
        self.format_caption.setText(self.tr("Format"))
        self.stdf_checkbox.setText(self.tr("STDF"))
        self.csv_checkbox.setText(self.tr("CSV"))
        self.layout_caption.setText(self.tr("CP CSV layout"))
        layout_labels = {
            "long": self.tr("One CSV per lot (long)"),
            "blocks": self.tr("One CSV per wafer (blocks)"),
            "both": self.tr("Both layouts"),
        }
        for index in range(self.layout_combo.count()):
            layout_name = self.layout_combo.itemData(index)
            if isinstance(layout_name, str) and layout_name in layout_labels:
                self.layout_combo.setItemText(index, layout_labels[layout_name])
        self.ground_truth_checkbox.setText(self.tr("Write ground truth"))
        self.die_truth_checkbox.setText(self.tr("Write per-die ground truth"))
        export_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if export_button is not None:
            export_button.setText(self.tr("Export"))
        cancel_button = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText(self.tr("Cancel"))

    def output_dir(self) -> Path | None:
        """The chosen directory, or ``None`` when the field is empty."""
        text = self.directory_edit.text().strip()
        return Path(text) if text else None

    def set_output_dir(self, path: str | Path) -> None:
        """Fill the directory field."""
        self.directory_edit.setText(str(path))

    def formats(self) -> tuple[ExportFormat, ...]:
        """The export formats selected for this run, in canonical order."""
        selected = {
            "stdf": self.stdf_checkbox.isChecked(),
            "csv": self.csv_checkbox.isChecked(),
        }
        return tuple(format_name for format_name in EXPORT_FORMATS if selected[format_name])

    def set_formats(self, formats: Sequence[str]) -> bool:
        """Select formats, rejecting values outside the schema."""
        requested = {format_name.lower() for format_name in formats}
        if not requested or not requested <= set(EXPORT_FORMATS):
            return False
        self.stdf_checkbox.setChecked("stdf" in requested)
        self.csv_checkbox.setChecked("csv" in requested)
        return True

    def set_include_stdf(self, enabled: bool) -> None:
        """Enable or disable STDF output for this run."""
        self.stdf_checkbox.setChecked(enabled)

    def set_include_csv(self, enabled: bool) -> None:
        """Enable or disable CSV output for this run."""
        self.csv_checkbox.setChecked(enabled)

    def cp_csv_layout(self) -> CsvLayout:
        """The CP CSV layout selected for this run."""
        data = self.layout_combo.currentData()
        if data in CSV_LAYOUTS:
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
        """Accept only a non-empty directory and at least one export format."""
        if self.output_dir() is None:
            self.error_label.setText(self.tr("Choose an output directory."))
            return
        if not self.formats():
            self.error_label.setText(self.tr("Choose at least one export format."))
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

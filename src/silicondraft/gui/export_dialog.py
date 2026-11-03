"""Dialog collecting the output directory for an export run."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
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


class ExportDialog(QDialog):
    """Let the user choose where the current result is written.

    V1 exports CSV only, so the format is shown but not selectable; the format
    picker arrives with the STDF writer. The dialog validates its inputs
    itself so an empty directory leaves it open with a readable message.
    """

    def __init__(self, output_dir: str | Path = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export Data"))

        self.directory_edit = QLineEdit(str(output_dir), self)
        self.directory_edit.setPlaceholderText(self.tr("Output directory"))
        browse_button = QPushButton(self.tr("Browse..."), self)
        browse_button.clicked.connect(self._browse)

        directory_row = QHBoxLayout()
        directory_row.addWidget(self.directory_edit)
        directory_row.addWidget(browse_button)

        self.format_label = QLabel(self.tr("CSV"), self)

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

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Output directory"), self))
        layout.addLayout(directory_row)
        layout.addWidget(QLabel(self.tr("Format"), self))
        layout.addWidget(self.format_label)
        layout.addWidget(self.error_label)
        layout.addWidget(self._buttons)

    def output_dir(self) -> Path | None:
        """The chosen directory, or ``None`` when the field is empty."""
        text = self.directory_edit.text().strip()
        return Path(text) if text else None

    def set_output_dir(self, path: str | Path) -> None:
        """Fill the directory field."""
        self.directory_edit.setText(str(path))

    def accept(self) -> None:
        """Accept only a non-empty output directory."""
        if self.output_dir() is None:
            self.error_label.setText(self.tr("Choose an output directory."))
            return
        self.error_label.clear()
        super().accept()

    def _browse(self) -> None:
        start_dir = str(self.output_dir() or "")
        chosen = QFileDialog.getExistingDirectory(
            self, self.tr("Select Output Directory"), start_dir
        )
        if chosen:
            self.set_output_dir(chosen)

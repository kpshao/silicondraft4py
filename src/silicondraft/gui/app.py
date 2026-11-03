"""Qt application entry point."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from .. import __version__
from .main_window import MainWindow

APPLICATION_NAME = "SiliconDraft"


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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the desktop application and return its exit code."""
    app = create_application(argv)
    window = MainWindow()
    window.show()
    return int(app.exec())

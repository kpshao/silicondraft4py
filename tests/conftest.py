"""Shared pytest configuration."""

import os
from collections.abc import Iterator

import pytest

# Qt needs a platform plugin in headless CI; offscreen works on every OS.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _reset_language() -> Iterator[None]:
    """Return the process to English after every test.

    GUI and CLI language selection are process-wide, so a test that switches to
    Chinese must not leak into the tests that follow it.
    """
    yield
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        return
    from silicondraft.gui.i18n import language_manager

    language_manager().set_language("en")

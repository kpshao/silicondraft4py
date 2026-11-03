"""Worker thread that runs the generation engine away from the UI thread."""

from __future__ import annotations

import threading
from typing import Protocol

from PySide6.QtCore import QObject, QThread, Signal

from ..api import CancelCheck, ProgressCallback, generate
from ..dataset import GenerationResult
from ..errors import GenerationCancelled, ScenarioError
from ..scenario.models import Scenario


class GenerateFn(Protocol):
    """The generation callable the worker drives (injectable for tests)."""

    def __call__(
        self,
        scenario: Scenario,
        *,
        progress: ProgressCallback | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> GenerationResult: ...


class GenerationWorker(QThread):
    """Run :func:`silicondraft.generate` and report progress over signals.

    ``progress`` carries :class:`~silicondraft.GenerationProgress`; ``invalid``
    carries the locatable issues of a rejected scenario; ``failed`` carries a
    message for unexpected engine errors.
    """

    progress = Signal(object)
    succeeded = Signal(object)
    invalid = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        scenario: Scenario,
        generate_fn: GenerateFn = generate,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._scenario = scenario
        self._generate_fn = generate_fn
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Ask the engine to stop before the next wafer."""
        self._cancel.set()

    def run(self) -> None:
        """Generate, mapping every outcome to a signal."""
        try:
            result = self._generate_fn(
                self._scenario,
                progress=self.progress.emit,
                should_cancel=self._cancel.is_set,
            )
        except GenerationCancelled:
            self.cancelled.emit()
        except ScenarioError as exc:
            self.invalid.emit(exc.issues)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(result)

"""Stable validation errors shared by the engine and CLI."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One locatable scenario problem.

    ``path`` is a dotted field path with array indices, for example
    ``patterns[0].target_item``. ``code`` is stable for translation and tests.
    YAML parse errors also carry one-based ``line`` and ``column`` values so
    the GUI can locate them without parsing the translated message.
    """

    code: str
    path: str
    message: str
    line: int | None = None
    column: int | None = None


class ScenarioError(ValueError):
    """Raised when a scenario cannot be loaded or validated."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        details = "; ".join(
            f"{issue.path}: {issue.message} [{issue.code}]" for issue in self.issues
        )
        super().__init__(f"invalid scenario: {details}")


class ExportError(RuntimeError):
    """Raised when generated data cannot be exported."""


class GenerationCancelled(Exception):
    """Raised when a caller cancels an in-progress generation.

    The generation loops check ``should_cancel`` between wafers, so no partial
    :class:`~silicondraft.GenerationResult` is returned.
    """

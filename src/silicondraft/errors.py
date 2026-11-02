"""Stable validation errors shared by the engine and CLI."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One locatable scenario problem.

    ``path`` is a dotted field path with array indices, for example
    ``patterns[0].target_item``. ``code`` is stable for translation and tests.
    """

    code: str
    path: str
    message: str


class ScenarioError(ValueError):
    """Raised when a scenario cannot be loaded or validated."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        details = "; ".join(
            f"{issue.path}: {issue.message} [{issue.code}]" for issue in self.issues
        )
        super().__init__(f"invalid scenario: {details}")

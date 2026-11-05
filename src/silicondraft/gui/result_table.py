"""Paged table model over the die-level records of a generation result."""

from __future__ import annotations

from bisect import bisect_right

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..dataset import CPWafer, GenerationResult

IndexLike = QModelIndex | QPersistentModelIndex

BASE_COLUMNS = (
    "lot_id",
    "wafer_id",
    "grid_x",
    "grid_y",
    "die_x_mm",
    "die_y_mm",
    "test_site",
    "hard_bin",
    "soft_bin",
    "die_pass",
)
DEFAULT_PAGE_SIZE = 200


def _format_number(value: float) -> str:
    """Format a measurement compactly for display in the table."""
    return format(value, ".10g")


class ResultTableModel(QAbstractTableModel):
    """Expose a :class:`GenerationResult` as die-level rows, one page at a time.

    Rows follow lot, then wafer, then die order. Item value columns follow the
    result's enabled CP items. Only the current page is materialised by
    :meth:`data`, so memory stays bounded regardless of the run size.
    """

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        super().__init__(parent)
        self._result: GenerationResult | None = None
        self._page_size = max(1, page_size)
        self._page = 0
        self._total_rows = 0
        self._wafer_ends: list[int] = []
        self._rows: list[tuple[str, CPWafer]] = []

    # -- read-only state ----------------------------------------------------

    @property
    def page(self) -> int:
        """Zero-based index of the page being shown."""
        return self._page

    @property
    def page_count(self) -> int:
        """Number of pages; always at least one, even with no result."""
        if self._total_rows == 0:
            return 1
        return (self._total_rows + self._page_size - 1) // self._page_size

    @property
    def total_rows(self) -> int:
        """Total die-level rows across every lot and wafer."""
        return self._total_rows

    @property
    def page_size(self) -> int:
        """Maximum number of rows shown per page."""
        return self._page_size

    # -- population ---------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Repaint translated cells such as the pass/fail column."""
        self.beginResetModel()
        self.endResetModel()

    def set_result(self, result: GenerationResult | None) -> None:
        """Show ``result`` from the first page, or clear the table for ``None``."""
        self.beginResetModel()
        self._result = result
        self._page = 0
        self._wafer_ends = []
        self._rows = []
        rows = 0
        if result is not None:
            for lot in result.lots:
                for wafer in lot.wafers:
                    rows += wafer.die_count
                    self._wafer_ends.append(rows)
                    self._rows.append((lot.lot_id, wafer))
        self._total_rows = rows
        self.endResetModel()

    def set_page_size(self, page_size: int) -> None:
        """Change the page size and return to the first page."""
        new_size = max(1, page_size)
        if new_size == self._page_size:
            return
        self.beginResetModel()
        self._page_size = new_size
        self._page = 0
        self.endResetModel()

    def set_page(self, page: int) -> bool:
        """Show page ``page``, clamped to the valid range.

        Returns whether the visible page changed.
        """
        clamped = min(max(0, page), self.page_count - 1)
        if clamped == self._page:
            return False
        self.beginResetModel()
        self._page = clamped
        self.endResetModel()
        return True

    # -- Qt model interface -------------------------------------------------

    def rowCount(self, parent: IndexLike | None = None) -> int:
        """Rows on the current page."""
        if parent is not None and parent.isValid():
            return 0
        first_row = self._page * self._page_size
        return max(0, min(self._page_size, self._total_rows - first_row))

    def columnCount(self, parent: IndexLike | None = None) -> int:
        """Fixed die columns followed by one column per enabled CP item."""
        if parent is not None and parent.isValid():
            return 0
        return len(BASE_COLUMNS) + self._item_count

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        """Column names and one-based global row numbers."""
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if section < len(BASE_COLUMNS):
                return BASE_COLUMNS[section]
            return self._item_ids[section - len(BASE_COLUMNS)]
        return str(self._page * self._page_size + section + 1)

    def data(
        self,
        index: IndexLike,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        """Format one cell for display."""
        if role != Qt.ItemDataRole.DisplayRole or not index.isValid():
            return None
        global_row = self._page * self._page_size + index.row()
        lot_id, wafer, die = self._locate(global_row)
        if index.column() < len(BASE_COLUMNS):
            return self._base_cell(lot_id, wafer, die, BASE_COLUMNS[index.column()])
        item_id = self._item_ids[index.column() - len(BASE_COLUMNS)]
        return _format_number(float(wafer.values[item_id][die]))

    # -- internals ----------------------------------------------------------

    @property
    def _item_ids(self) -> tuple[str, ...]:
        if self._result is None:
            return ()
        return tuple(item.id for item in self._result.items)

    @property
    def _item_count(self) -> int:
        if self._result is None:
            return 0
        return len(self._result.items)

    def _locate(self, global_row: int) -> tuple[str, CPWafer, int]:
        wafer_index = bisect_right(self._wafer_ends, global_row)
        start = self._wafer_ends[wafer_index - 1] if wafer_index > 0 else 0
        lot_id, wafer = self._rows[wafer_index]
        return lot_id, wafer, global_row - start

    def _base_cell(self, lot_id: str, wafer: CPWafer, die: int, column: str) -> str:
        match column:
            case "lot_id":
                return lot_id
            case "wafer_id":
                return wafer.wafer_id
            case "grid_x":
                return str(int(wafer.grid_x[die]))
            case "grid_y":
                return str(int(wafer.grid_y[die]))
            case "die_x_mm":
                return _format_number(float(wafer.x_mm[die]))
            case "die_y_mm":
                return _format_number(float(wafer.y_mm[die]))
            case "test_site":
                return str(int(wafer.test_site[die]))
            case "hard_bin":
                return str(int(wafer.hard_bin[die]))
            case "soft_bin":
                return str(int(wafer.soft_bin[die]))
            case _:
                return self.tr("Pass") if bool(wafer.passed[die]) else self.tr("Fail")


class ResultsPanel(QWidget):
    """A read-only table of die-level results with page controls."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        super().__init__(parent)
        self._model = ResultTableModel(self, page_size=page_size)

        self.table = QTableView(self)
        self.table.setModel(self._model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.previous_button = QPushButton(self)
        self.next_button = QPushButton(self)
        self.page_label = QLabel(self)
        self.previous_button.clicked.connect(lambda: self._turn_page(-1))
        self.next_button.clicked.connect(lambda: self._turn_page(1))

        controls = QHBoxLayout()
        controls.addWidget(self.previous_button)
        controls.addWidget(self.page_label)
        controls.addStretch(1)
        controls.addWidget(self.next_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(controls)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Re-apply every user-visible string in the current language."""
        self.previous_button.setText(self.tr("Previous"))
        self.next_button.setText(self.tr("Next"))
        self._model.retranslate_ui()
        self._sync_pagination()

    @property
    def model(self) -> ResultTableModel:
        """The table model backing this panel."""
        return self._model

    def set_result(self, result: GenerationResult | None) -> None:
        """Show ``result`` from its first page, or clear the table."""
        self._model.set_result(result)
        self._sync_pagination()

    def set_page_size(self, page_size: int) -> None:
        """Change how many die rows fit on one page."""
        self._model.set_page_size(page_size)
        self._sync_pagination()

    def _turn_page(self, offset: int) -> None:
        self._model.set_page(self._model.page + offset)
        self._sync_pagination()

    def _sync_pagination(self) -> None:
        page = self._model.page
        page_count = self._model.page_count
        self.page_label.setText(
            self.tr("Page {page} of {count}").format(page=page + 1, count=page_count)
        )
        self.previous_button.setEnabled(page > 0)
        self.next_button.setEnabled(page < page_count - 1)

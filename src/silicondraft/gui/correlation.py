"""Correlation scatter for one WAT/CP linkage pair.

Each WAT site is paired with its nearest CP die through the engine's layout
helper, matching the pairing used by the generation report (see ADR-0006).
The panel plots those pairs and annotates the configured target correlation.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..catalog import CatalogItem
from ..dataset import (
    CPWafer,
    FloatArray,
    GenerationResult,
    IntArray,
    LinkageReportEntry,
    WatWafer,
)
from ..geometry import DieLayout, WatSiteLayout
from ..geometry import nearest_die_indices as layout_nearest_die_indices
from .sampling import sample_indices

DEFAULT_MAX_SCATTER_POINTS = 20_000


@dataclass(frozen=True, slots=True)
class WaferLinkage:
    """One wafer's paired WAT-site and nearest-CP-die columns."""

    lot_id: str
    wat_wafer: WatWafer
    cp_wafer: CPWafer
    wat_values: FloatArray
    cp_values: FloatArray


@dataclass(frozen=True, slots=True)
class LinkageSamples:
    """Every paired WAT/CP observation behind one linkage scatter."""

    wat_values: FloatArray
    cp_values: FloatArray

    @property
    def sample_count(self) -> int:
        """Number of site/die pairs."""
        return int(self.wat_values.size)


def nearest_die_indices(wat_wafer: WatWafer, cp_wafer: CPWafer) -> IntArray:
    """Index of the nearest CP die for every WAT site on one wafer.

    Delegates to the engine layout helper so tie-breaking matches the report.
    """
    if wat_wafer.site_count == 0 or cp_wafer.die_count == 0:
        return np.empty(0, dtype=np.int64)
    wat_sites = WatSiteLayout(
        site_number=wat_wafer.site_number,
        x_mm=wat_wafer.x_mm,
        y_mm=wat_wafer.y_mm,
    )
    dies = DieLayout(
        x_mm=cp_wafer.x_mm,
        y_mm=cp_wafer.y_mm,
        grid_x=cp_wafer.grid_x,
        grid_y=cp_wafer.grid_y,
        test_site=cp_wafer.test_site,
    )
    return layout_nearest_die_indices(wat_sites, dies)


def iter_wafer_linkages(
    result: GenerationResult,
    wat_item: str,
    cp_item: str,
) -> Iterator[WaferLinkage]:
    """Yield the paired columns of every aligned WAT/CP wafer.

    A length mismatch would silently truncate the preview and break its
    agreement with the generation report, so misaligned results yield nothing.
    """
    if len(result.wat_lots) != len(result.lots):
        return
    for wat_lot, cp_lot in zip(result.wat_lots, result.lots, strict=True):
        if len(wat_lot.wafers) != len(cp_lot.wafers):
            return
        for wat_wafer, cp_wafer in zip(wat_lot.wafers, cp_lot.wafers, strict=True):
            if wat_item not in wat_wafer.values or cp_item not in cp_wafer.values:
                continue
            nearest = nearest_die_indices(wat_wafer, cp_wafer)
            if nearest.size == 0:
                continue
            yield WaferLinkage(
                lot_id=cp_lot.lot_id,
                wat_wafer=wat_wafer,
                cp_wafer=cp_wafer,
                wat_values=wat_wafer.values[wat_item],
                cp_values=cp_wafer.values[cp_item][nearest],
            )


def collect_linkage_samples(
    result: GenerationResult,
    wat_item: str,
    cp_item: str,
) -> LinkageSamples | None:
    """Collect every WAT-site/nearest-CP-die pair for one linkage pair."""
    wat_chunks: list[FloatArray] = []
    cp_chunks: list[FloatArray] = []
    for linkage in iter_wafer_linkages(result, wat_item, cp_item):
        wat_chunks.append(linkage.wat_values)
        cp_chunks.append(linkage.cp_values)
    if not wat_chunks:
        return None
    return LinkageSamples(
        wat_values=np.concatenate(wat_chunks),
        cp_values=np.concatenate(cp_chunks),
    )


class CorrelationPanel(QWidget):
    """A WAT-versus-CP scatter for one linkage pair, with target r annotated."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        max_points: int = DEFAULT_MAX_SCATTER_POINTS,
    ) -> None:
        super().__init__(parent)
        self._max_points = max(1, max_points)
        self._result: GenerationResult | None = None
        self._entries: dict[tuple[str, str], LinkageReportEntry] = {}
        self._pair: tuple[str, str] | None = None
        self._linkage: LinkageSamples | None = None
        self._displayed_points = 0
        self._scatter_x = np.empty(0, dtype=np.float64)
        self._scatter_y = np.empty(0, dtype=np.float64)

        self.pair_combo = QComboBox(self)
        self.pair_label = QLabel(self)
        self.target_label = QLabel(self)
        self.summary_label = QLabel(self)
        self.message_label = QLabel(self)
        self.message_label.setWordWrap(True)
        self.plot = pg.PlotWidget(self)
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.getAxis("left").enableAutoSIPrefix(False)
        self.plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.annotation = pg.TextItem(color="#333333", anchor=(0.0, 1.0))
        self.scatter_item = pg.ScatterPlotItem(size=5, pen=None, brush=pg.mkBrush("#4c72b0"))
        self.plot.addItem(self.scatter_item)
        self.plot.addItem(self.annotation)

        self.pair_combo.currentIndexChanged.connect(self._on_pair_changed)

        controls = QHBoxLayout()
        controls.addWidget(self.pair_label)
        controls.addWidget(self.pair_combo)
        controls.addWidget(self.target_label)
        controls.addWidget(self.summary_label)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.message_label)
        layout.addWidget(self.plot, 1)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Re-apply every user-visible string in the current language."""
        self.pair_label.setText(self.tr("Pair:"))
        self._refresh()

    # -- read-only state ----------------------------------------------------

    @property
    def pair_keys(self) -> tuple[tuple[str, str], ...]:
        """Configured WAT/CP linkage pairs, in report order."""
        return tuple(self._entries)

    @property
    def pair(self) -> tuple[str, str] | None:
        """The linkage pair currently shown."""
        return self._pair

    @property
    def linkage(self) -> LinkageSamples | None:
        """The collected scatter data, or ``None`` without WAT data."""
        return self._linkage

    @property
    def target_r(self) -> float | None:
        """The configured target correlation of the shown pair."""
        entry = self._entry()
        return entry.target_r if entry is not None else None

    @property
    def achieved_r(self) -> float | None:
        """The calibrated model's achieved correlation of the shown pair."""
        entry = self._entry()
        return entry.achieved_r if entry is not None else None

    @property
    def observed_r(self) -> float | None:
        """The sample correlation of the shown pair, from the generation report."""
        if self._linkage is None:
            return None
        entry = self._entry()
        return entry.observed_r if entry is not None else None

    @property
    def displayed_point_count(self) -> int:
        """Number of points drawn after downsampling."""
        return self._displayed_points

    @property
    def scatter_x(self) -> FloatArray:
        """The WAT values actually plotted, after downsampling."""
        return self._scatter_x

    @property
    def scatter_y(self) -> FloatArray:
        """The paired CP values actually plotted, after downsampling."""
        return self._scatter_y

    @property
    def sample_count(self) -> int:
        """Number of pairs before downsampling."""
        return self._linkage.sample_count if self._linkage is not None else 0

    @property
    def empty_message(self) -> str | None:
        """Why the plot is empty, or ``None`` when it has data."""
        if self._result is None:
            return self.tr("No generation result yet.")
        if not self._entries:
            return self.tr("No WAT linkage data to preview.")
        if self._linkage is None:
            return self.tr("No WAT data for this pair.")
        return None

    # -- population ---------------------------------------------------------

    def set_result(self, result: GenerationResult | None) -> None:
        """Fill the pair selector from ``result``, or clear the panel for ``None``."""
        self._result = result
        self._entries = {
            (entry.wat_item, entry.cp_item): entry
            for entry in (result.linkage_report if result is not None else ())
        }
        previous = self._pair
        self.pair_combo.blockSignals(True)
        try:
            self.pair_combo.clear()
            for wat_item, cp_item in self._entries:
                self.pair_combo.addItem(f"{wat_item} ↔ {cp_item}", _pair_key(wat_item, cp_item))
            target = previous if previous in self._entries else next(iter(self._entries), None)
            index = self.pair_combo.findData(_pair_key(*target)) if target is not None else -1
            self.pair_combo.setCurrentIndex(index)
        finally:
            self.pair_combo.blockSignals(False)
        self._pair = target
        self._refresh()

    def select_pair(self, wat_item: str, cp_item: str) -> bool:
        """Select a configured linkage pair and redraw the scatter."""
        pair = (wat_item, cp_item)
        if pair not in self._entries:
            return False
        index = self.pair_combo.findData(_pair_key(*pair))
        if index >= 0:
            self.pair_combo.blockSignals(True)
            try:
                self.pair_combo.setCurrentIndex(index)
            finally:
                self.pair_combo.blockSignals(False)
        self._pair = pair
        self._refresh()
        return True

    # -- internals ----------------------------------------------------------

    def _on_pair_changed(self, index: int) -> None:
        data = self.pair_combo.itemData(index)
        if isinstance(data, str):
            wat_item, separator, cp_item = data.partition("|")
            self._pair = (wat_item, cp_item) if separator else None
        else:
            self._pair = None
        self._refresh()

    def _entry(self) -> LinkageReportEntry | None:
        if self._pair is None:
            return None
        return self._entries.get(self._pair)

    def _refresh(self) -> None:
        self.plot.clear()
        self.plot.addItem(self.scatter_item)
        self.plot.addItem(self.annotation)
        self.scatter_item.setData(x=[], y=[])
        self.annotation.setText("")
        self._linkage = None
        self._displayed_points = 0
        self._scatter_x = np.empty(0, dtype=np.float64)
        self._scatter_y = np.empty(0, dtype=np.float64)
        self.target_label.clear()
        self.summary_label.clear()
        if self._result is None or self._pair is None:
            self.message_label.setText(self.empty_message or "")
            self.message_label.setVisible(True)
            self.plot.setLabel("bottom", "")
            self.plot.setLabel("left", "")
            return

        wat_item, cp_item = self._pair
        linkage = collect_linkage_samples(self._result, wat_item, cp_item)
        self._linkage = linkage
        self.message_label.setText(self.empty_message or "")
        self.message_label.setVisible(linkage is None)
        if linkage is None:
            self.plot.setLabel("bottom", "")
            self.plot.setLabel("left", "")
            return

        indices = sample_indices(linkage.sample_count, self._max_points)
        x_values = linkage.wat_values[indices]
        y_values = linkage.cp_values[indices]
        self._scatter_x = x_values
        self._scatter_y = y_values
        self._displayed_points = int(indices.size)
        self.scatter_item.setData(x=x_values, y=y_values)
        self._update_labels(linkage)
        self._annotate(linkage)
        self._set_axis_labels()

    def _update_labels(self, linkage: LinkageSamples) -> None:
        entry = self._entry()
        if entry is not None:
            self.target_label.setText(
                self.tr("target r = {value:+.3f}").format(value=entry.target_r)
            )
            self.summary_label.setText(
                self.tr(
                    "achieved r = {achieved:+.3f}   observed r = {observed:+.3f}   n={count}"
                ).format(
                    achieved=entry.achieved_r,
                    observed=entry.observed_r,
                    count=linkage.sample_count,
                )
            )
        else:
            self.summary_label.setText(
                self.tr("No linkage report for this pair (n={count}).").format(
                    count=linkage.sample_count
                )
            )

    def _annotate(self, linkage: LinkageSamples) -> None:
        text = self.target_label.text()
        if not text:
            return
        self.annotation.setText(text)
        x_min = float(np.min(linkage.wat_values))
        x_max = float(np.max(linkage.wat_values))
        y_max = float(np.max(linkage.cp_values))
        x_padding = (x_max - x_min) * 0.02 if x_max > x_min else 1.0
        self.annotation.setPos(x_min + x_padding, y_max)

    def _set_axis_labels(self) -> None:
        if self._result is None or self._pair is None:
            return
        wat_item = self._catalog_item(self._result.wat_items, self._pair[0])
        cp_item = self._catalog_item(self._result.items, self._pair[1])
        self.plot.setLabel("bottom", _axis_label(self._pair[0], wat_item))
        self.plot.setLabel("left", _axis_label(self._pair[1], cp_item))

    @staticmethod
    def _catalog_item(items: tuple[CatalogItem, ...], item_id: str) -> CatalogItem | None:
        for item in items:
            if item.id == item_id:
                return item
        return None


def _pair_key(wat_item: str, cp_item: str) -> str:
    return f"{wat_item}|{cp_item}"


def _axis_label(item_id: str, item: CatalogItem | None) -> str:
    unit = f" [{item.unit}]" if item is not None and item.unit else ""
    return f"{item_id}{unit}"

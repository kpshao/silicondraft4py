"""Distribution histogram for one CP item, with spec limits overlaid."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyqtgraph as pg
from numpy.typing import NDArray
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..catalog import CatalogItem
from ..dataset import GenerationResult
from .sampling import sample_indices

DEFAULT_HISTOGRAM_BINS = 50
MAX_HISTOGRAM_SAMPLES = 200_000


@dataclass(frozen=True, slots=True)
class HistogramData:
    """Binned measurements of one item over every die in the result."""

    counts: NDArray[np.float64]
    edges: NDArray[np.float64]
    sampled_count: int


def compute_histogram(
    values: NDArray[np.float64],
    *,
    bins: int = DEFAULT_HISTOGRAM_BINS,
    max_samples: int = MAX_HISTOGRAM_SAMPLES,
) -> HistogramData | None:
    """Bin finite values, sampling large inputs down to ``max_samples``.

    Sampling is an evenly spaced, deterministic selection so the histogram is
    stable across repaints and bounded in work for very large runs.
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    if finite.size > max_samples:
        finite = finite[sample_indices(finite.size, max_samples)]
    counts, edges = np.histogram(finite, bins=bins)
    return HistogramData(
        counts=counts.astype(np.float64),
        edges=edges.astype(np.float64),
        sampled_count=int(finite.size),
    )


class DistributionPanel(QWidget):
    """A histogram of the selected CP item with its LSL and USL marked."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        bins: int = DEFAULT_HISTOGRAM_BINS,
        max_samples: int = MAX_HISTOGRAM_SAMPLES,
    ) -> None:
        super().__init__(parent)
        self._bins = max(1, bins)
        self._max_samples = max(1, max_samples)
        self._result: GenerationResult | None = None
        self._item: CatalogItem | None = None
        self._histogram: HistogramData | None = None
        self._spec_lines: tuple[pg.InfiniteLine, ...] = ()

        self.item_combo = QComboBox(self)
        self.item_combo.currentIndexChanged.connect(self._on_item_changed)
        self.item_label = QLabel(self)
        self.stats_label = QLabel(self)
        self.plot = pg.PlotWidget(self)
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.2)

        controls = QHBoxLayout()
        controls.addWidget(self.item_label)
        controls.addWidget(self.item_combo)
        controls.addStretch(1)
        controls.addWidget(self.stats_label)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.plot)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Re-apply every user-visible string in the current language."""
        self.item_label.setText(self.tr("Item:"))
        self.plot.setLabel("left", self.tr("Die count"))
        self._recompute()

    # -- read-only state ----------------------------------------------------

    @property
    def item_ids(self) -> tuple[str, ...]:
        """CP items available for the histogram."""
        if self._result is None:
            return ()
        return tuple(item.id for item in self._result.items)

    @property
    def item_id(self) -> str | None:
        """The CP item currently shown."""
        return self._item.id if self._item is not None else None

    @property
    def histogram(self) -> HistogramData | None:
        """The current binned measurements, or ``None`` without data."""
        return self._histogram

    @property
    def spec_limit_values(self) -> tuple[float | None, float | None]:
        """The current item's lower and upper spec limits."""
        if self._item is None:
            return (None, None)
        return (self._item.lsl, self._item.usl)

    @property
    def spec_lines(self) -> tuple[pg.InfiniteLine, ...]:
        """The spec-limit lines currently drawn on the plot."""
        return self._spec_lines

    # -- population ---------------------------------------------------------

    def set_result(self, result: GenerationResult | None) -> None:
        """Show the first item of ``result``, or clear the histogram for ``None``."""
        self._result = result
        self.item_combo.blockSignals(True)
        try:
            self.item_combo.clear()
            if result is not None:
                for item in result.items:
                    self.item_combo.addItem(item.id, item.id)
            self.item_combo.setCurrentIndex(0 if self.item_combo.count() else -1)
        finally:
            self.item_combo.blockSignals(False)
        self._select_item(self.item_ids[0] if self.item_ids else None)

    def set_item(self, item_id: str) -> bool:
        """Select a CP item and redraw its histogram."""
        if item_id not in self.item_ids:
            return False
        index = self.item_combo.findData(item_id)
        if index >= 0:
            self.item_combo.blockSignals(True)
            try:
                self.item_combo.setCurrentIndex(index)
            finally:
                self.item_combo.blockSignals(False)
        self._select_item(item_id)
        return True

    # -- internals ----------------------------------------------------------

    def _on_item_changed(self, index: int) -> None:
        item_id = self.item_combo.itemData(index)
        self._select_item(item_id if isinstance(item_id, str) else None)

    def _select_item(self, item_id: str | None) -> None:
        self._item = self._catalog_item(item_id)
        self._recompute()

    def _catalog_item(self, item_id: str | None) -> CatalogItem | None:
        if self._result is None or item_id is None:
            return None
        for item in self._result.items:
            if item.id == item_id:
                return item
        return None

    def _item_values(self, item_id: str) -> NDArray[np.float64]:
        if self._result is None:
            return np.empty(0, dtype=np.float64)
        columns = [wafer.values[item_id] for lot in self._result.lots for wafer in lot.wafers]
        if not columns:
            return np.empty(0, dtype=np.float64)
        return np.concatenate(columns)

    def _recompute(self) -> None:
        self.plot.clear()
        self._spec_lines = ()
        self._histogram = None
        item = self._item
        if item is None:
            self.stats_label.clear()
            self.plot.setLabel("bottom", "")
            return
        values = self._item_values(item.id)
        histogram = compute_histogram(values, bins=self._bins, max_samples=self._max_samples)
        self._histogram = histogram
        if histogram is not None:
            centres = (histogram.edges[:-1] + histogram.edges[1:]) / 2
            widths = np.diff(histogram.edges)
            self.plot.addItem(
                pg.BarGraphItem(
                    x=centres,
                    height=histogram.counts,
                    width=widths,
                    brush=pg.mkBrush("#4c72b0"),
                    pen=None,
                )
            )
            self.stats_label.setText(
                self.tr("n={count}  mean={mean:.6g}  sd={sd:.6g}").format(
                    count=histogram.sampled_count,
                    mean=float(np.mean(values)) if values.size else 0.0,
                    sd=float(np.std(values)) if values.size else 0.0,
                )
            )
        else:
            self.stats_label.clear()
        self._draw_spec_lines(item)
        unit = f" [{item.unit}]" if item.unit else ""
        self.plot.setLabel("bottom", f"{item.id}{unit}")

    def _draw_spec_lines(self, item: CatalogItem) -> None:
        lines: list[pg.InfiniteLine] = []
        for value, colour, label in (
            (item.lsl, "#c62828", "LSL"),
            (item.usl, "#c62828", "USL"),
        ):
            if value is None:
                continue
            line = pg.InfiniteLine(
                pos=value,
                angle=90,
                pen=pg.mkPen(colour, width=2),
                label=label,
                labelOpts={"position": 0.9},
            )
            self.plot.addItem(line)
            lines.append(line)
        self._spec_lines = tuple(lines)

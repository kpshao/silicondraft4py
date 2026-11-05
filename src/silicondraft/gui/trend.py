"""Lot/wafer trend previews for CP yield and WAT↔CP linkage pairs.

The yield metric reads per-wafer and per-lot pass fractions. Linkage metrics
plot the mean WAT site value and the mean CP value of the paired nearest dies,
standardised as z-scores so different units remain comparable on one plot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..catalog import CatalogItem
from ..dataset import CPLot, CPWafer, FloatArray, GenerationResult
from .correlation import iter_wafer_linkages

TrendView = Literal["lot", "wafer"]
TREND_VIEWS: tuple[TrendView, ...] = ("wafer", "lot")
YIELD_METRIC = "yield"
SERIES_COLOURS = ("#4c72b0", "#ef6c00")


@dataclass(frozen=True, slots=True)
class TrendSeries:
    """One line of a trend chart."""

    name: str
    unit: str
    values: FloatArray
    relative: bool = False

    @property
    def plot_values(self) -> FloatArray:
        """Values as drawn: yield in percent, linkage means as z-scores."""
        if not self.relative:
            return self.values * 100.0
        if self.values.size == 0:
            return self.values
        deviation = self.values - float(np.mean(self.values))
        spread = float(np.std(self.values))
        if spread == 0.0 or not np.isfinite(spread):
            return np.zeros_like(self.values)
        return deviation / spread


@dataclass(frozen=True, slots=True)
class TrendData:
    """Points and series for one metric and one lot/wafer view."""

    labels: tuple[str, ...]
    lot_ids: tuple[str, ...]
    series: tuple[TrendSeries, ...]

    @property
    def point_count(self) -> int:
        """Number of x-axis points."""
        return len(self.labels)


def yield_trend(result: GenerationResult, view: TrendView) -> TrendData | None:
    """Per-wafer or per-lot CP yield, or ``None`` when that view has no points."""
    if not result.lots:
        return None
    if view == "lot":
        if len(result.lots) < 2:
            return None
        labels = tuple(lot.lot_id for lot in result.lots)
        lot_ids = labels
        values = np.array([_lot_yield(lot) for lot in result.lots], dtype=np.float64)
    else:
        labels_list: list[str] = []
        lot_ids_list: list[str] = []
        values_list: list[float] = []
        for lot in result.lots:
            for wafer in lot.wafers:
                labels_list.append(f"{lot.lot_id} / {wafer.wafer_id}")
                lot_ids_list.append(lot.lot_id)
                values_list.append(_wafer_yield(wafer))
        if not values_list:
            return None
        labels = tuple(labels_list)
        lot_ids = tuple(lot_ids_list)
        values = np.array(values_list, dtype=np.float64)
    return TrendData(
        labels=labels,
        lot_ids=lot_ids,
        series=(TrendSeries(name="Yield", unit="", values=values),),
    )


def pair_mean_trend(
    result: GenerationResult,
    wat_item: str,
    cp_item: str,
    view: TrendView,
) -> TrendData | None:
    """Mean WAT and paired CP values by wafer or lot, or ``None`` without data."""
    if not result.wat_lots or not result.lots:
        return None
    if view == "lot":
        if len(result.lots) < 2:
            return None
        order: list[str] = []
        wat_chunks: dict[str, list[FloatArray]] = {}
        cp_chunks: dict[str, list[FloatArray]] = {}
        for linkage in iter_wafer_linkages(result, wat_item, cp_item):
            if linkage.lot_id not in wat_chunks:
                order.append(linkage.lot_id)
                wat_chunks[linkage.lot_id] = []
                cp_chunks[linkage.lot_id] = []
            wat_chunks[linkage.lot_id].append(linkage.wat_values)
            cp_chunks[linkage.lot_id].append(linkage.cp_values)
        if not order:
            return None
        labels = tuple(order)
        lot_ids = labels
        wat_means = [float(np.mean(np.concatenate(wat_chunks[lot_id]))) for lot_id in order]
        cp_means = [float(np.mean(np.concatenate(cp_chunks[lot_id]))) for lot_id in order]
    else:
        labels_list = []
        lot_ids_list = []
        wat_means = []
        cp_means = []
        for linkage in iter_wafer_linkages(result, wat_item, cp_item):
            labels_list.append(f"{linkage.lot_id} / {linkage.cp_wafer.wafer_id}")
            lot_ids_list.append(linkage.lot_id)
            wat_means.append(float(np.mean(linkage.wat_values)))
            cp_means.append(float(np.mean(linkage.cp_values)))
        if not wat_means:
            return None
        labels = tuple(labels_list)
        lot_ids = tuple(lot_ids_list)
    return TrendData(
        labels=labels,
        lot_ids=lot_ids,
        series=(
            TrendSeries(
                name=wat_item,
                unit=_unit(result.wat_items, wat_item),
                values=np.array(wat_means, dtype=np.float64),
                relative=True,
            ),
            TrendSeries(
                name=cp_item,
                unit=_unit(result.items, cp_item),
                values=np.array(cp_means, dtype=np.float64),
                relative=True,
            ),
        ),
    )


class TrendPanel(QWidget):
    """A lot/wafer trend chart for CP yield or one WAT/CP linkage pair."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result: GenerationResult | None = None
        self._metric_key = YIELD_METRIC
        self._view: TrendView = "wafer"
        self._data: TrendData | None = None

        self.metric_combo = QComboBox(self)
        self.view_combo = QComboBox(self)
        self.view_combo.addItem("", "wafer")
        self.view_combo.addItem("", "lot")
        self.metric_label = QLabel(self)
        self.view_label = QLabel(self)
        self.series_label = QLabel(self)
        self.series_label.setTextFormat(Qt.TextFormat.RichText)
        self.message_label = QLabel(self)
        self.message_label.setWordWrap(True)
        self.notice_label = QLabel(self)
        self.notice_label.setWordWrap(True)
        self.plot = pg.PlotWidget(self)
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.getAxis("left").enableAutoSIPrefix(False)
        self.plot.getAxis("bottom").enableAutoSIPrefix(False)

        self.metric_combo.currentIndexChanged.connect(self._on_metric_changed)
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)

        controls = QHBoxLayout()
        controls.addWidget(self.metric_label)
        controls.addWidget(self.metric_combo)
        controls.addWidget(self.view_label)
        controls.addWidget(self.view_combo)
        controls.addStretch(1)
        controls.addWidget(self.series_label)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.message_label)
        layout.addWidget(self.notice_label)
        layout.addWidget(self.plot, 1)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Re-apply every user-visible string in the current language."""
        self.metric_label.setText(self.tr("Metric:"))
        self.view_label.setText(self.tr("View:"))
        view_labels = {"wafer": self.tr("By wafer"), "lot": self.tr("By lot")}
        for index in range(self.view_combo.count()):
            view = self.view_combo.itemData(index)
            if isinstance(view, str) and view in view_labels:
                self.view_combo.setItemText(index, view_labels[view])
        self._rebuild_metric_combo()
        self._refresh()

    # -- read-only state ----------------------------------------------------

    @property
    def metric_keys(self) -> tuple[str, ...]:
        """Selectable metric keys: yield followed by every linkage pair."""
        return tuple(
            self.metric_combo.itemData(index) for index in range(self.metric_combo.count())
        )

    @property
    def metric_key(self) -> str:
        """The metric currently shown."""
        return self._metric_key

    @property
    def view_mode(self) -> TrendView:
        """Whether points are aggregated by lot or per wafer."""
        return self._view

    @property
    def labels(self) -> tuple[str, ...]:
        """X-axis labels for the current points."""
        return self._data.labels if self._data is not None else ()

    @property
    def series(self) -> tuple[TrendSeries, ...]:
        """The lines currently shown."""
        return self._data.series if self._data is not None else ()

    @property
    def point_count(self) -> int:
        """Number of x-axis points currently shown."""
        return self._data.point_count if self._data is not None else 0

    @property
    def y_axis_label(self) -> str:
        """Description of the plotted y values."""
        if self._data is None or not self._data.series:
            return ""
        if self._data.series[0].relative:
            return self.tr("Standardized (z-score)")
        return self.tr("Yield (%)")

    @property
    def notice(self) -> str | None:
        """A note about unavailable WAT trends, shown beside a yield chart."""
        if self._result is None or self._result.linkage_report:
            return None
        return self.tr("No WAT linkage data to trend.")

    @property
    def empty_message(self) -> str | None:
        """Why the chart is empty, or ``None`` when it has data."""
        if self._result is None:
            return self.tr("No generation result yet.")
        if self._data is not None:
            return None
        if self._metric_key == YIELD_METRIC:
            if self._view == "lot" and len(self._result.lots) < 2:
                return self.tr("At least two lots are required for a lot-level trend.")
            return self.tr("No CP yield data to preview.")
        if not self._result.wat_lots:
            return self.tr("No WAT data for this pair.")
        wat_item, _, cp_item = self._metric_key.partition("|")
        if not wat_item or not cp_item:
            return self.tr("No WAT data for this pair.")
        if pair_mean_trend(self._result, wat_item, cp_item, "wafer") is None:
            return self.tr("No WAT data for this pair.")
        if self._view == "lot" and len(self._result.lots) < 2:
            return self.tr("At least two lots are required for a lot-level trend.")
        return self.tr("No WAT data for this pair.")

    # -- population ---------------------------------------------------------

    def set_result(self, result: GenerationResult | None) -> None:
        """Replace the result, keeping the metric when it still exists."""
        self._result = result
        self._rebuild_metric_combo()
        self._refresh()

    def set_metric(self, metric_key: str) -> bool:
        """Select a metric and redraw."""
        index = self.metric_combo.findData(metric_key)
        if index < 0:
            return False
        self.metric_combo.blockSignals(True)
        try:
            self.metric_combo.setCurrentIndex(index)
        finally:
            self.metric_combo.blockSignals(False)
        self._metric_key = metric_key
        self._refresh()
        return True

    def set_view_mode(self, view: str) -> bool:
        """Switch between per-wafer (``wafer``) and per-lot (``lot``) points."""
        if view not in TREND_VIEWS:
            return False
        index = self.view_combo.findData(view)
        if index >= 0:
            self.view_combo.blockSignals(True)
            try:
                self.view_combo.setCurrentIndex(index)
            finally:
                self.view_combo.blockSignals(False)
        self._view = view
        self._refresh()
        return True

    # -- internals ----------------------------------------------------------

    def _rebuild_metric_combo(self) -> None:
        previous = self._metric_key
        self.metric_combo.blockSignals(True)
        try:
            self.metric_combo.clear()
            self.metric_combo.addItem(self.tr("CP Yield"), YIELD_METRIC)
            seen: set[str] = set()
            if self._result is not None:
                for entry in self._result.linkage_report:
                    key = f"{entry.wat_item}|{entry.cp_item}"
                    if key in seen:
                        continue
                    seen.add(key)
                    self.metric_combo.addItem(f"{entry.wat_item} ↔ {entry.cp_item}", key)
            index = self.metric_combo.findData(previous)
            if index < 0:
                index = 0
                previous = YIELD_METRIC
            self.metric_combo.setCurrentIndex(index)
        finally:
            self.metric_combo.blockSignals(False)
        self._metric_key = previous

    def _on_metric_changed(self, index: int) -> None:
        key = self.metric_combo.itemData(index)
        if isinstance(key, str):
            self._metric_key = key
            self._refresh()

    def _on_view_changed(self, index: int) -> None:
        view = self.view_combo.itemData(index)
        if isinstance(view, str):
            self._view = cast(TrendView, view)
            self._refresh()

    def _build_data(self) -> TrendData | None:
        if self._result is None:
            return None
        if self._metric_key == YIELD_METRIC:
            return yield_trend(self._result, self._view)
        wat_item, _, cp_item = self._metric_key.partition("|")
        if not wat_item or not cp_item:
            return None
        return pair_mean_trend(self._result, wat_item, cp_item, self._view)

    def _refresh(self) -> None:
        self.plot.clear()
        self.series_label.clear()
        self._data = self._build_data()
        self.notice_label.setText(self.notice or "")
        self.notice_label.setVisible(self.notice is not None)
        axis = self.plot.getAxis("bottom")
        if self._data is None:
            self.plot.setLabel("left", "")
            axis.setTicks([[]])
            self.message_label.setText(self.empty_message or "")
            self.message_label.setVisible(True)
            return

        self.message_label.clear()
        self.message_label.setVisible(False)
        self.plot.setLabel("left", self.y_axis_label)
        self._draw_series(self._data)
        self._draw_lot_boundaries(self._data)
        self._set_ticks(self._data)
        self.plot.setXRange(-1.5, max(self._data.point_count - 0.5, 0.5) + 1.5, padding=0.0)
        parts = []
        for index, series in enumerate(self._data.series):
            name = series.name if series.relative else self.tr("Yield")
            label = f"{name} [{series.unit}]" if series.unit else name
            colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
            parts.append(f'<span style="color:{colour}">■</span> {label}')
        self.series_label.setText("&nbsp;&nbsp;".join(parts))

    def _draw_series(self, data: TrendData) -> None:
        x_values = np.arange(data.point_count, dtype=np.float64)
        for index, series in enumerate(data.series):
            colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
            self.plot.plot(
                x_values,
                series.plot_values,
                pen=pg.mkPen(colour, width=2),
                symbol="o",
                symbolSize=6,
                symbolBrush=colour,
                symbolPen=None,
                name=series.name,
            )
        if data.series and data.series[0].relative:
            self.plot.addItem(
                pg.InfiniteLine(
                    pos=0.0,
                    angle=0,
                    pen=pg.mkPen("#9e9e9e", width=1, style=Qt.PenStyle.DashLine),
                )
            )

    def _draw_lot_boundaries(self, data: TrendData) -> None:
        if self._view != "wafer":
            return
        for index in range(1, data.point_count):
            if data.lot_ids[index] != data.lot_ids[index - 1]:
                self.plot.addItem(
                    pg.InfiniteLine(
                        pos=index - 0.5,
                        angle=90,
                        pen=pg.mkPen("#bdbdbd", width=1, style=Qt.PenStyle.DashLine),
                    )
                )

    def _set_ticks(self, data: TrendData) -> None:
        if self._view == "lot":
            ticks = [(float(index), label) for index, label in enumerate(data.labels)]
        else:
            ticks = []
            start = 0
            for index in range(1, data.point_count + 1):
                if index == data.point_count or data.lot_ids[index] != data.lot_ids[start]:
                    ticks.append(((start + index - 1) / 2.0, data.lot_ids[start]))
                    start = index
        self.plot.getAxis("bottom").setTicks([ticks])


def _unit(items: tuple[CatalogItem, ...], item_id: str) -> str:
    for item in items:
        if item.id == item_id:
            return item.unit
    return ""


def _wafer_yield(wafer: CPWafer) -> float:
    return wafer.yield_fraction if wafer.die_count else 0.0


def _lot_yield(lot: CPLot) -> float:
    return lot.yield_fraction if lot.die_count else 0.0

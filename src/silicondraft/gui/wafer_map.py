"""Self-drawn QGraphicsView wafer map coloured by bins or a CP item.

One wafer is shown at a time. All dies are painted by a single custom
:class:`QGraphicsItem`, so the scene item count stays constant no matter how
many dies a wafer carries. Very large wafers are sampled down to
:data:`MAX_RENDER_DIES` dies with an evenly spaced, deterministic selection.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSceneHoverEvent,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QStyleOptionGraphicsItem,
    QVBoxLayout,
    QWidget,
)

from ..binning import (
    CONTINUITY_FAIL,
    FUNCTIONAL_FAIL,
    HARD_BIN_DEFINITIONS,
    PARAMETRIC_FAIL,
    PASS,
    SOFT_BIN_DEFINITIONS,
    SOFT_CONTINUITY,
    SOFT_FREQUENCY,
    SOFT_FUNCTIONAL,
    SOFT_IDDQ,
    SOFT_LEAKAGE,
    SOFT_OTHER_PARAMETRIC,
    SOFT_PASS,
    SOFT_VTH,
)
from ..catalog import CatalogItem
from ..dataset import CPWafer, GenerationResult
from ..exporters.common import format_float
from ..patterns import PatternExtent, pattern_extent, pattern_id
from .sampling import sample_indices

ColorMode = Literal["hard_bin", "soft_bin", "item"]
COLOR_MODES: tuple[ColorMode, ...] = ("hard_bin", "soft_bin", "item")
MAX_RENDER_DIES = 20_000

_HARD_BIN_COLOURS: dict[int, QColor] = {
    PASS: QColor("#2e7d32"),
    PARAMETRIC_FAIL: QColor("#ef6c00"),
    FUNCTIONAL_FAIL: QColor("#c62828"),
    CONTINUITY_FAIL: QColor("#6a1b9a"),
}
_SOFT_BIN_COLOURS: dict[int, QColor] = {
    SOFT_PASS: QColor("#2e7d32"),
    SOFT_CONTINUITY: QColor("#6a1b9a"),
    SOFT_LEAKAGE: QColor("#1565c0"),
    SOFT_IDDQ: QColor("#00838f"),
    SOFT_VTH: QColor("#ef6c00"),
    SOFT_FREQUENCY: QColor("#ad1457"),
    SOFT_FUNCTIONAL: QColor("#c62828"),
    SOFT_OTHER_PARAMETRIC: QColor("#5d4037"),
}
_UNKNOWN_BIN_COLOUR = QColor("#9e9e9e")

_HARD_BIN_NAMES = {definition.number: definition.name for definition in HARD_BIN_DEFINITIONS}
_SOFT_BIN_NAMES = {definition.number: definition.name for definition in SOFT_BIN_DEFINITIONS}


def item_colour(fraction: float) -> QColor:
    """Map a normalized measurement to a blue-to-red colour along a hue ramp."""
    clamped = min(max(fraction, 0.0), 1.0)
    return QColor.fromHsvF(0.62 * (1.0 - clamped), 0.85, 0.95)


_OVERLAY_COLOURS: tuple[str, ...] = (
    "#e91e63",
    "#3f51b5",
    "#00897b",
    "#f9a825",
    "#7b1fa2",
    "#d84315",
    "#0277bd",
    "#558b2f",
)


class _OverlayLayer(QGraphicsItem):
    """Draw dashed outlines around the extents of the active patterns."""

    def __init__(self) -> None:
        super().__init__()
        self._paths: tuple[tuple[QColor, QPainterPath], ...] = ()
        self._bounds = QRectF()
        self.setZValue(1.0)

    def set_overlays(
        self,
        overlays: Iterable[PatternExtent],
        wafer_radius_mm: float,
        margin: float,
    ) -> None:
        """Replace the drawn outlines and their scene bounds."""
        self.prepareGeometryChange()
        paths: list[tuple[QColor, QPainterPath]] = []
        for index, overlay in enumerate(overlays):
            colour = QColor(_OVERLAY_COLOURS[index % len(_OVERLAY_COLOURS)])
            centre = QPointF(overlay.center_mm[0], -overlay.center_mm[1])
            path = QPainterPath()
            path.addEllipse(centre, overlay.outer_radius_mm, overlay.outer_radius_mm)
            if overlay.inner_radius_mm > 0.0:
                path.addEllipse(centre, overlay.inner_radius_mm, overlay.inner_radius_mm)
            paths.append((colour, path))
        self._paths = tuple(paths)
        radius = wafer_radius_mm + margin
        self._bounds = QRectF(-radius, -radius, 2 * radius, 2 * radius)
        self.update()

    def boundingRect(self) -> QRectF:
        """The wafer-sized area the outlines can occupy."""
        return self._bounds

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Stroke each pattern's boundary with a distinct dashed colour."""
        if not self._paths:
            return
        width = max(self._bounds.width() * 0.006, 0.8)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for colour, path in self._paths:
            painter.setPen(QPen(colour, width, Qt.PenStyle.DashLine))
            painter.drawPath(path)


class _DieLayer(QGraphicsItem):
    """Paint every rendered die in one item and answer hover tooltips."""

    def __init__(self) -> None:
        super().__init__()
        self._batches: tuple[tuple[QColor, tuple[QRectF, ...]], ...] = ()
        self._tooltips: tuple[tuple[QRectF, str], ...] = ()
        self._bounds = QRectF()
        self.setAcceptHoverEvents(True)

    def set_cells(
        self,
        batches: Iterable[tuple[QColor, Iterable[QRectF]]],
        bounds: QRectF,
        tooltips: Iterable[tuple[QRectF, str]],
    ) -> None:
        """Replace the painted cells."""
        self.prepareGeometryChange()
        self._batches = tuple((colour, tuple(rects)) for colour, rects in batches)
        self._tooltips = tuple(tooltips)
        self._bounds = bounds
        self.update()

    def boundingRect(self) -> QRectF:
        """The union of all painted die rectangles."""
        return self._bounds

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Fill every die rectangle, grouping by colour to limit state changes."""
        painter.setPen(Qt.PenStyle.NoPen)
        for colour, rects in self._batches:
            painter.setBrush(colour)
            for rect in rects:
                painter.drawRect(rect)

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Show the die details under the cursor as a tooltip."""
        position = event.pos()
        for rect, text in self._tooltips:
            if rect.contains(position):
                self.setToolTip(text)
                break
        else:
            self.setToolTip("")
        super().hoverMoveEvent(event)


class WaferMapView(QGraphicsView):
    """Show the dies of one generated wafer, coloured by bin or item value."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        max_render_dies: int = MAX_RENDER_DIES,
    ) -> None:
        super().__init__(parent)
        self._max_render_dies = max(1, max_render_dies)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._die_layer = _DieLayer()
        self._scene.addItem(self._die_layer)
        self._overlay_layer = _OverlayLayer()
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#fafafa"))
        self._scene_rect = QRectF()
        self._wafer_radius_mm = 0.0
        self._die_size_mm = (0.0, 0.0)
        self._result: GenerationResult | None = None
        self._wafers: tuple[CPWafer, ...] = ()
        self._items: tuple[CatalogItem, ...] = ()
        self._item_lookup: dict[str, CatalogItem] = {}
        self._wafer_index = 0
        self._color_mode: ColorMode = "hard_bin"
        self._item_id: str | None = None
        self._item_min = 0.0
        self._item_max = 0.0
        self._render_indices = np.empty(0, dtype=np.int64)
        self._overlay_enabled = False
        self._overlays: tuple[PatternExtent, ...] = ()

    # -- read-only state ----------------------------------------------------

    @property
    def wafer_count(self) -> int:
        """Number of wafers in the current result."""
        return len(self._wafers)

    @property
    def wafer_index(self) -> int:
        """Index of the wafer being shown."""
        return self._wafer_index

    @property
    def wafer_radius_mm(self) -> float:
        """Radius of the drawn wafer outline, or zero when no result is shown."""
        return self._wafer_radius_mm

    @property
    def wafer(self) -> CPWafer | None:
        """The wafer being shown, or ``None`` before a result is set."""
        if not self._wafers:
            return None
        return self._wafers[self._wafer_index]

    @property
    def color_mode(self) -> ColorMode:
        """Whether dies are coloured by hard bin, soft bin, or item value."""
        return self._color_mode

    @property
    def item_id(self) -> str | None:
        """The CP item used when ``color_mode`` is ``item``."""
        return self._item_id

    @property
    def item_ids(self) -> tuple[str, ...]:
        """CP items available for item colouring."""
        return tuple(item.id for item in self._items)

    @property
    def rendered_die_count(self) -> int:
        """Number of dies actually painted for the current wafer."""
        return int(self._render_indices.size)

    @property
    def downsampled(self) -> bool:
        """Whether the current wafer is shown with fewer dies than it has."""
        wafer = self.wafer
        return wafer is not None and self.rendered_die_count < wafer.die_count

    @property
    def ground_truth_overlay(self) -> bool:
        """Whether pattern extents are drawn over the dies."""
        return self._overlay_enabled

    @property
    def pattern_overlays(self) -> tuple[PatternExtent, ...]:
        """Extents of the patterns active on the current wafer."""
        return self._overlays

    @property
    def overlay_text(self) -> str:
        """A short description of the visible pattern overlays."""
        if not self._overlay_enabled or not self._overlays:
            return ""
        return ", ".join(f"{overlay.pattern_id} ({overlay.kind})" for overlay in self._overlays)

    # -- population ---------------------------------------------------------

    def set_result(self, result: GenerationResult | None) -> None:
        """Show the first wafer of ``result``, or clear the map for ``None``."""
        self._result = result
        self._wafers = (
            tuple(wafer for lot in result.lots for wafer in lot.wafers)
            if result is not None
            else ()
        )
        self._items = result.items if result is not None else ()
        self._item_lookup = {item.id: item for item in self._items}
        self._wafer_index = 0
        if result is not None:
            self._wafer_radius_mm = result.scenario.wafer.diameter_mm / 2
            self._die_size_mm = result.scenario.wafer.die_size_mm
        else:
            self._wafer_radius_mm = 0.0
            self._die_size_mm = (0.0, 0.0)
        if self._item_id not in self._item_lookup:
            self._item_id = self._items[0].id if self._items else None
        self._rebuild()

    def set_wafer(self, index: int) -> bool:
        """Show wafer ``index``, clamped to the available wafers."""
        if not self._wafers:
            return False
        clamped = min(max(0, index), len(self._wafers) - 1)
        if clamped != self._wafer_index:
            self._wafer_index = clamped
            self._rebuild()
        return True

    def set_color_mode(self, mode: str) -> bool:
        """Switch colouring between hard bin, soft bin, and item value."""
        if mode not in COLOR_MODES:
            return False
        if mode != self._color_mode:
            self._color_mode = mode
            self._rebuild()
        return True

    def set_item(self, item_id: str) -> bool:
        """Select the CP item used when colouring by item value."""
        if item_id not in self.item_ids:
            return False
        if item_id != self._item_id:
            self._item_id = item_id
            self._rebuild()
        return True

    def set_ground_truth_overlay(self, enabled: bool) -> None:
        """Show or hide the injected-pattern extents on the wafer map."""
        if enabled == self._overlay_enabled:
            return
        self._overlay_enabled = enabled
        self._sync_overlay_layer()

    # -- per-die facts ------------------------------------------------------

    def display_value(self, die_index: int) -> float:
        """The value behind a die's colour: a bin code or the selected item value."""
        wafer = self._wafer_or_raise()
        if self._color_mode == "soft_bin":
            return float(wafer.soft_bin[die_index])
        if self._color_mode == "item" and self._item_id is not None:
            return float(wafer.values[self._item_id][die_index])
        return float(wafer.hard_bin[die_index])

    def die_color(self, die_index: int) -> QColor:
        """The colour of one die under the current colour mode."""
        wafer = self._wafer_or_raise()
        if self._color_mode == "hard_bin":
            return _HARD_BIN_COLOURS.get(int(wafer.hard_bin[die_index]), _UNKNOWN_BIN_COLOUR)
        if self._color_mode == "soft_bin":
            return _SOFT_BIN_COLOURS.get(int(wafer.soft_bin[die_index]), _UNKNOWN_BIN_COLOUR)
        return item_colour(self._fraction(self.display_value(die_index)))

    def die_rect(self, die_index: int) -> QRectF:
        """The scene rectangle of one die, with +Y measured upwards."""
        wafer = self._wafer_or_raise()
        width, height = self._die_size_mm
        x_mm = float(wafer.x_mm[die_index])
        y_mm = float(wafer.y_mm[die_index])
        return QRectF(x_mm - width / 2, -y_mm - height / 2, width, height)

    def die_tooltip(self, die_index: int) -> str:
        """The hover text for one die, using the CSV's number format."""
        wafer = self._wafer_or_raise()
        position = self.tr("x={x}mm y={y}mm").format(
            x=format_float(float(wafer.x_mm[die_index])),
            y=format_float(float(wafer.y_mm[die_index])),
        )
        if self._color_mode == "hard_bin":
            code = int(wafer.hard_bin[die_index])
            name = _HARD_BIN_NAMES.get(code, "?")
            return self.tr("{wafer}  hard_bin={code} ({name})  {position}").format(
                wafer=wafer.wafer_id, code=code, name=name, position=position
            )
        if self._color_mode == "soft_bin":
            code = int(wafer.soft_bin[die_index])
            name = _SOFT_BIN_NAMES.get(code, "?")
            return self.tr("{wafer}  soft_bin={code} ({name})  {position}").format(
                wafer=wafer.wafer_id, code=code, name=name, position=position
            )
        if self._item_id is None:
            return self.tr("{wafer}  {position}").format(wafer=wafer.wafer_id, position=position)
        item = self._item_lookup[self._item_id]
        value = float(wafer.values[item.id][die_index])
        return self.tr("{wafer}  {item}={value} {unit}  {position}").format(
            wafer=wafer.wafer_id,
            item=item.id,
            value=format_float(value),
            unit=item.unit,
            position=position,
        )

    @property
    def legend_text(self) -> str:
        """A short description of the current colour scale."""
        if self._color_mode == "hard_bin":
            return self.tr("Hard bin")
        if self._color_mode == "soft_bin":
            return self.tr("Soft bin")
        if self._item_id is None:
            return self.tr("Item")
        item = self._item_lookup.get(self._item_id)
        unit = f" [{item.unit}]" if item is not None and item.unit else ""
        if self.wafer is None:
            return f"{self._item_id}{unit}"
        return (
            f"{self._item_id}{unit}  "
            f"{format_float(self._item_min)} .. {format_float(self._item_max)}"
        )

    # -- painting -----------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF | QRect) -> None:
        """Paint the wafer outline behind the dies."""
        painter.fillRect(rect, self.backgroundBrush())
        if self._wafer_radius_mm <= 0:
            return
        painter.setPen(QPen(QColor("#9e9e9e"), 0))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(0.0, 0.0), self._wafer_radius_mm, self._wafer_radius_mm)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep the wafer fitted after the view is resized."""
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> None:
        if self._scene_rect.isValid():
            self.fitInView(self._scene_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _rebuild(self) -> None:
        wafer = self.wafer
        self._render_indices = (
            sample_indices(wafer.die_count, self._max_render_dies)
            if wafer is not None
            else np.empty(0, dtype=np.int64)
        )
        self._update_item_range(wafer)
        batches: dict[str, tuple[QColor, list[QRectF]]] = {}
        tooltips: list[tuple[QRectF, str]] = []
        bounds = QRectF()
        for die_index in self._render_indices:
            die = int(die_index)
            rect = self.die_rect(die)
            colour = self.die_color(die)
            key = colour.name()
            if key not in batches:
                batches[key] = (colour, [])
            batches[key][1].append(rect)
            tooltips.append((rect, self.die_tooltip(die)))
            bounds = rect if bounds.isNull() else bounds.united(rect)
        self._die_layer.set_cells(batches.values(), bounds, tooltips)
        margin = max(self._wafer_radius_mm * 0.02, 1.0)
        self._overlays = self._active_pattern_overlays(wafer)
        self._overlay_layer.set_overlays(self._overlays, self._wafer_radius_mm, margin)
        radius = self._wafer_radius_mm + margin
        self._scene_rect = QRectF(-radius, -radius, 2 * radius, 2 * radius)
        self._scene.setSceneRect(self._scene_rect)
        self._sync_overlay_layer()
        self._fit()

    def _active_pattern_overlays(self, wafer: CPWafer | None) -> tuple[PatternExtent, ...]:
        result = self._result
        if result is None or wafer is None:
            return ()
        active = set(wafer.pattern_hits)
        overlays: list[PatternExtent] = []
        for index, pattern in enumerate(result.scenario.patterns):
            if pattern_id(index) not in active:
                continue
            extent = pattern_extent(pattern, index, result.scenario.wafer)
            if extent is not None:
                overlays.append(extent)
        return tuple(overlays)

    def _sync_overlay_layer(self) -> None:
        visible = self._overlay_enabled and bool(self._overlays)
        if visible and self._overlay_layer.scene() is None:
            self._scene.addItem(self._overlay_layer)
        elif not visible and self._overlay_layer.scene() is not None:
            self._scene.removeItem(self._overlay_layer)

    def _update_item_range(self, wafer: CPWafer | None) -> None:
        if wafer is None or self._item_id is None or self._item_id not in wafer.values:
            self._item_min = 0.0
            self._item_max = 0.0
            return
        column = wafer.values[self._item_id]
        if column.size == 0:
            self._item_min = 0.0
            self._item_max = 0.0
            return
        self._item_min = float(np.min(column))
        self._item_max = float(np.max(column))

    def _fraction(self, value: float) -> float:
        span = self._item_max - self._item_min
        if span <= 0.0:
            return 0.5
        return (value - self._item_min) / span

    def _wafer_or_raise(self) -> CPWafer:
        wafer = self.wafer
        if wafer is None:
            raise IndexError("no wafer is displayed")
        return wafer


class WaferMapPanel(QWidget):
    """Wafer map plus the controls that choose the wafer, bin, and item."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        max_render_dies: int = MAX_RENDER_DIES,
    ) -> None:
        super().__init__(parent)
        self.map_view = WaferMapView(self, max_render_dies=max_render_dies)
        self.wafer_combo = QComboBox(self)
        self.color_combo = QComboBox(self)
        self.item_combo = QComboBox(self)
        self.overlay_checkbox = QCheckBox(self.tr("Ground truth"), self)
        self.legend_label = QLabel(self)
        self.overlay_label = QLabel(self)

        for label, mode in (
            (self.tr("Hard bin"), "hard_bin"),
            (self.tr("Soft bin"), "soft_bin"),
            (self.tr("Item"), "item"),
        ):
            self.color_combo.addItem(label, mode)

        self.wafer_combo.currentIndexChanged.connect(self._on_wafer_changed)
        self.color_combo.currentIndexChanged.connect(self._on_color_mode_changed)
        self.item_combo.currentIndexChanged.connect(self._on_item_changed)
        self.overlay_checkbox.toggled.connect(self._on_overlay_toggled)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(self.tr("Wafer:"), self))
        controls.addWidget(self.wafer_combo)
        controls.addWidget(QLabel(self.tr("Colour by:"), self))
        controls.addWidget(self.color_combo)
        controls.addWidget(self.item_combo)
        controls.addWidget(self.overlay_checkbox)
        controls.addStretch(1)
        controls.addWidget(self.overlay_label)
        controls.addWidget(self.legend_label)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.map_view)
        self._sync_controls()

    # -- population ---------------------------------------------------------

    def set_result(self, result: GenerationResult | None) -> None:
        """Fill the controls and map from ``result``, or clear them for ``None``."""
        self.wafer_combo.blockSignals(True)
        try:
            self.wafer_combo.clear()
            if result is not None:
                for lot in result.lots:
                    for wafer in lot.wafers:
                        self.wafer_combo.addItem(f"{lot.lot_id} / {wafer.wafer_id}")
        finally:
            self.wafer_combo.blockSignals(False)

        self.item_combo.blockSignals(True)
        try:
            self.item_combo.clear()
            if result is not None:
                for item in result.items:
                    self.item_combo.addItem(item.id, item.id)
        finally:
            self.item_combo.blockSignals(False)

        self.map_view.set_result(result)
        self._sync_controls()

    def select_color_mode(self, mode: str) -> bool:
        """Switch how dies are coloured."""
        index = self.color_combo.findData(mode)
        if index < 0:
            return False
        self.color_combo.setCurrentIndex(index)
        self.map_view.set_color_mode(mode)
        self._sync_controls()
        return True

    def select_item(self, item_id: str) -> bool:
        """Select the CP item used for item colouring."""
        index = self.item_combo.findData(item_id)
        if index < 0:
            return False
        self.item_combo.setCurrentIndex(index)
        self.map_view.set_item(item_id)
        self._sync_controls()
        return True

    def set_ground_truth_overlay(self, enabled: bool) -> None:
        """Show or hide the injected-pattern extents."""
        self.overlay_checkbox.setChecked(enabled)
        self.map_view.set_ground_truth_overlay(enabled)
        self._sync_controls()

    # -- internals ----------------------------------------------------------

    def _on_wafer_changed(self, index: int) -> None:
        self.map_view.set_wafer(index)
        self._sync_controls()

    def _on_color_mode_changed(self, index: int) -> None:
        mode = self.color_combo.itemData(index)
        if isinstance(mode, str):
            self.map_view.set_color_mode(mode)
        self._sync_controls()

    def _on_item_changed(self, index: int) -> None:
        item_id = self.item_combo.itemData(index)
        if isinstance(item_id, str):
            self.map_view.set_item(item_id)
        self._sync_controls()

    def _on_overlay_toggled(self, checked: bool) -> None:
        self.map_view.set_ground_truth_overlay(checked)
        self._sync_controls()

    def _sync_controls(self) -> None:
        self.item_combo.setEnabled(self.map_view.color_mode == "item")
        self.item_combo.blockSignals(True)
        try:
            self.item_combo.setCurrentIndex(
                self.item_combo.findData(self.map_view.item_id)
                if self.map_view.item_id is not None
                else -1
            )
        finally:
            self.item_combo.blockSignals(False)
        self.wafer_combo.blockSignals(True)
        try:
            self.wafer_combo.setCurrentIndex(
                self.map_view.wafer_index if self.map_view.wafer_count else -1
            )
        finally:
            self.wafer_combo.blockSignals(False)
        self.legend_label.setText(self.map_view.legend_text if self.map_view.wafer else "")
        self.overlay_checkbox.blockSignals(True)
        try:
            self.overlay_checkbox.setChecked(self.map_view.ground_truth_overlay)
        finally:
            self.overlay_checkbox.blockSignals(False)
        self.overlay_checkbox.setEnabled(bool(self.map_view.pattern_overlays))
        self.overlay_label.setText(self.map_view.overlay_text)

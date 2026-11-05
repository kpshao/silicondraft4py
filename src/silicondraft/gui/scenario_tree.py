"""Read-only scenario configuration tree."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget

from ..patterns import pattern_id
from ..scenario.models import Pattern, Scenario


class ScenarioTree(QTreeWidget):
    """Display a scenario as grouped ``setting`` / ``value`` rows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scenario: Scenario | None = None
        self._apply_header_labels()
        self.setColumnWidth(0, 280)
        self.setAlternatingRowColors(True)

    def set_scenario(self, scenario: Scenario) -> None:
        """Rebuild the tree for ``scenario``."""
        self._scenario = scenario
        self._rebuild()

    def retranslate_ui(self) -> None:
        """Re-apply every user-visible string in the current language."""
        self._apply_header_labels()
        if self._scenario is not None:
            self._rebuild()

    def _apply_header_labels(self) -> None:
        self.setHeaderLabels([self.tr("Setting"), self.tr("Value")])

    def _rebuild(self) -> None:
        scenario = self._scenario
        if scenario is None:
            self.clear()
            return
        self.clear()
        self._add_field(None, "schema_version", scenario.schema_version)
        self._add_field(
            None, "preset", self.tr("(none)") if scenario.preset is None else scenario.preset
        )
        self._add_field(None, "seed", scenario.seed)

        product = self._add_group(self.tr("Product"))
        self._add_field(product, "name", scenario.product.name)
        self._add_field(product, "device_family", scenario.product.device_family)
        self._add_field(product, "process_node", scenario.product.process_node)
        self._add_field(product, "fab", scenario.product.fab)
        self._add_field(product, "test_program", scenario.product.test_program)

        wafer = self._add_group(self.tr("Wafer"))
        self._add_field(wafer, "diameter_mm", scenario.wafer.diameter_mm)
        self._add_field(wafer, "die_size_mm", scenario.wafer.die_size_mm)
        self._add_field(wafer, "edge_exclusion_mm", scenario.wafer.edge_exclusion_mm)
        self._add_field(wafer, "notch", scenario.wafer.notch)
        self._add_field(wafer, "cp_sites", scenario.wafer.cp_sites)
        self._add_field(wafer, "wat_sites", scenario.wafer.wat_sites)

        lots = self._add_group(self.tr("Lots"))
        self._add_field(lots, "count", scenario.lots.count)
        self._add_field(lots, "wafers_per_lot", scenario.lots.wafers_per_lot)
        self._add_field(lots, "lot_id_template", scenario.lots.lot_id_template)
        self._add_field(lots, "wafer_id_template", scenario.lots.wafer_id_template)
        self._add_field(lots, "start_date", scenario.lots.start_date)
        self._add_field(lots, "wat_to_cp_gap_min", scenario.lots.wat_to_cp_gap_min)
        self._add_field(lots, "cp_duration_min_per_wafer", scenario.lots.cp_duration_min_per_wafer)
        self._add_field(lots, "lot_interval_hours", scenario.lots.lot_interval_hours)

        items = self._add_group(self.tr("Items"))
        self._add_field(items, "preset", scenario.items.preset)
        self._add_field(items, "overrides", len(scenario.items.overrides))
        for index, override in enumerate(scenario.items.overrides):
            child = self._add_child(parent=items, title=f"override_{index + 1}")
            self._add_field(child, "id", override.id)
            if override.enabled is not None:
                self._add_field(child, "enabled", override.enabled)
            self._add_field(child, "remove", override.remove)

        patterns = self._add_group(self.tr("Patterns"))
        self._add_field(patterns, "count", len(scenario.patterns))
        for index, pattern in enumerate(scenario.patterns):
            self._add_pattern(patterns, index, pattern)

        defects = self._add_group(self.tr("Defects"))
        self._add_field(defects, "enabled", scenario.defects.enabled)
        self._add_field(defects, "model", scenario.defects.model)
        self._add_field(defects, "failure_rate", scenario.defects.failure_rate)
        self._add_field(defects, "cluster_size", scenario.defects.cluster_size)
        self._add_field(defects, "cluster_radius_mm", scenario.defects.cluster_radius_mm)
        self._add_field(defects, "target_items", scenario.defects.target_items)

        linkage = self._add_group(self.tr("Linkage"))
        self._add_field(linkage, "overrides", len(scenario.linkage.overrides))
        for index, linkage_override in enumerate(scenario.linkage.overrides):
            child = self._add_child(parent=linkage, title=f"override_{index + 1}")
            self._add_field(child, "wat", linkage_override.wat)
            self._add_field(child, "cp", linkage_override.cp)
            self._add_field(child, "target_r", linkage_override.target_r)

        export = self._add_group(self.tr("Export"))
        self._add_field(export, "cp_stdf", scenario.export.cp_stdf)
        self._add_field(export, "cp_csv", scenario.export.cp_csv)
        self._add_field(export, "cp_csv_layout", scenario.export.cp_csv_layout)
        self._add_field(export, "wat_csv", scenario.export.wat_csv)
        self._add_field(export, "ground_truth", scenario.export.ground_truth)
        self._add_field(export, "include_die_truth", scenario.export.include_die_truth)
        self._add_field(export, "encoding", scenario.export.encoding)

        metadata = self._add_group(self.tr("Metadata"))
        self._add_field(metadata, "author", scenario.metadata.author)
        self._add_field(metadata, "note", scenario.metadata.note)

    def _add_pattern(self, parent: QTreeWidgetItem, index: int, pattern: Pattern) -> None:
        child = self._add_child(parent=parent, title=pattern_id(index))
        self._add_field(child, "kind", pattern.kind)
        self._add_field(child, "scope", pattern.scope)
        if pattern.target is not None:
            self._add_field(child, "target", pattern.target)
        if pattern.target_item is not None:
            self._add_field(child, "target_item", pattern.target_item)
        self._add_field(child, "amplitude", pattern.amplitude)
        for field_name in ("radius_mm", "extent_mm", "width_mm"):
            value = getattr(pattern, field_name)
            if value is not None:
                self._add_field(child, field_name, value)
        self._add_field(child, "center_mm", pattern.center_mm)
        self._add_field(child, "combine", pattern.combine)

    def _add_group(self, title: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title, ""])
        self.addTopLevelItem(item)
        item.setExpanded(True)
        return item

    def _add_child(self, parent: QTreeWidgetItem, title: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title, ""])
        parent.addChild(item)
        item.setExpanded(True)
        return item

    def _add_field(
        self, parent: QTreeWidgetItem | None, name: str, value: object
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name, self._format_value(value)])
        if parent is None:
            self.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _format_value(self, value: object) -> str:
        if isinstance(value, bool):
            return self.tr("Yes") if value else self.tr("No")
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, float):
            return f"{value:g}"
        if isinstance(value, Sequence) and not isinstance(value, str):
            return ", ".join(self._format_value(item) for item in value)
        if value is None:
            return self.tr("(none)")
        return str(value)

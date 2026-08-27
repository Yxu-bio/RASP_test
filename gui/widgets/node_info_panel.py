import math

from PyQt5.QtCore import Qt, QPointF, QSize, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QColorDialog,
    QTextEdit,
    QComboBox,
    QCheckBox,
    QPushButton,
    QDoubleSpinBox,
    QProgressBar,
    QSplitter,
    QSizePolicy,
    QFileDialog,
    QMessageBox,
)


TOTAL_EVENTS_LABEL = "Total events"
NODE_DENSITY_LABEL = "Node density baseline"


class LegacyTimeDiagramWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.series_rows = []
        self.point_rows = []
        self.series_filter = "All"
        self.show_points = False
        self.show_lines = True
        self.show_legend = True
        self.x_grid_step = 0.0
        self.y_grid_step = 0.0
        self.reverse_time_axis = False
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_plot_data(
        self,
        *,
        series_rows,
        point_rows,
        series_filter,
        show_points,
        show_lines,
        show_legend,
        x_grid_step=0.0,
        y_grid_step=0.0,
        reverse_time_axis=False,
    ) -> None:
        self.series_rows = list(series_rows or [])
        self.point_rows = list(point_rows or [])
        self.series_filter = str(series_filter or "All")
        self.show_points = bool(show_points)
        self.show_lines = bool(show_lines)
        self.show_legend = bool(show_legend)
        self.x_grid_step = float(x_grid_step or 0.0)
        self.y_grid_step = float(y_grid_step or 0.0)
        self.reverse_time_axis = bool(reverse_time_axis)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        if not self.series_rows:
            painter.setPen(QColor("#666666"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No time data")
            painter.end()
            return

        left = 42
        right = 18
        top = 30
        bottom = 34
        width = max(1, self.width() - left - right)
        height = max(1, self.height() - top - bottom)

        times = []
        values = []
        for row in self.series_rows:
            times.append(float(row.get("time", 0.0) or 0.0))
            for name, value in dict(row.get("values", {}) or {}).items():
                if not self._series_visible(name):
                    continue
                values.append(float(value or 0.0))
        if not times:
            painter.end()
            return
        max_time = max(times) if max(times) > 0 else 1.0
        max_value = max(values) if values else 1.0
        if max_value <= 0:
            max_value = 1.0

        grid_pen = QPen(QColor("#d6d6d6"), 1)
        axis_pen = QPen(QColor("#222222"), 1)
        painter.setFont(QFont("Tahoma", 8))
        painter.setPen(grid_pen)

        for tick in self._tick_values(max_time, self.x_grid_step):
            frac = float(tick) / max_time if max_time > 0 else 0.0
            x = left + width - frac * width
            painter.drawLine(int(x), top, int(x), top + height)
            label = self._format_number(self._axis_time_label(tick, max_time))
            painter.setPen(QColor("#333333"))
            painter.drawText(int(x - 18), top + height + 16, 40, 16, Qt.AlignCenter, label)
            painter.setPen(grid_pen)

        for tick in self._tick_values(max_value, self.y_grid_step):
            frac = float(tick) / max_value if max_value > 0 else 0.0
            y = top + height - frac * height
            painter.drawLine(left, int(y), left + width, int(y))
            label = self._format_number(tick)
            painter.setPen(QColor("#333333"))
            painter.drawText(0, int(y - 8), left - 4, 16, Qt.AlignRight | Qt.AlignVCenter, label)
            painter.setPen(grid_pen)

        painter.setPen(axis_pen)
        painter.drawRect(left, top, width, height)

        series_names = self._series_names()
        for name in series_names:
            if not self._series_visible(name):
                continue
            color = QColor(self._series_color(name))
            pen = QPen(color, 2)
            painter.setPen(pen)
            previous = None
            for row in self.series_rows:
                point = self._map_point(
                    time_value=float(row.get("time", 0.0) or 0.0),
                    value=float(dict(row.get("values", {}) or {}).get(name, 0.0) or 0.0),
                    left=left,
                    top=top,
                    width=width,
                    height=height,
                    max_time=max_time,
                    max_value=max_value,
                )
                if previous is not None and self.show_lines:
                    painter.drawLine(previous, point)
                previous = point

        if self.show_points:
            point_items = []
            for point_row in self.point_rows:
                name = str(point_row.get("series", "") or "")
                if not self._series_visible(name):
                    continue
                base_point = self._map_point(
                    time_value=float(point_row.get("time", 0.0) or 0.0),
                    value=float(point_row.get("value", 0.0) or 0.0),
                    left=left,
                    top=top,
                    width=width,
                    height=height,
                    max_time=max_time,
                    max_value=max_value,
                )
                point_items.append({"series": name, "point": base_point})
            self._draw_point_items(painter, point_items)

        if self.show_legend:
            legend_x = left + 8
            legend_y = top + 8
            visible_names = [name for name in series_names if self._series_visible(name)]
            for index, name in enumerate(visible_names):
                y = legend_y + index * 18
                painter.setPen(QPen(QColor(self._series_color(name)), 2))
                painter.drawLine(legend_x, y + 8, legend_x + 26, y + 8)
                if self.show_points:
                    painter.setBrush(QBrush(QColor(self._series_color(name))))
                    painter.setPen(QPen(QColor("#111111"), 1))
                    painter.drawEllipse(QPointF(legend_x + 34, y + 8), 3.5, 3.5)
                painter.setPen(QColor("#222222"))
                painter.drawText(legend_x + 44, y, 140, 16, Qt.AlignLeft | Qt.AlignVCenter, name)

        painter.end()

    def _map_point(self, *, time_value, value, left, top, width, height, max_time, max_value):
        x = left + width - (float(time_value) / max_time) * width
        y = top + height - (float(value) / max_value) * height
        return QPointF(float(x), float(y))

    def _series_visible(self, name):
        name = str(name or "")
        series_filter = str(self.series_filter or "All")
        if not series_filter or series_filter == "All":
            return True
        if series_filter.startswith("only:"):
            return name == series_filter.split(":", 1)[1]
        if series_filter.startswith("hide:"):
            return name != series_filter.split(":", 1)[1]
        return name == series_filter

    def _draw_point_items(self, painter, point_items):
        grouped = {}
        for item in point_items:
            point = item["point"]
            key = (int(round(point.x())), int(round(point.y())))
            grouped.setdefault(key, []).append(item)

        draw_items = []
        for items in grouped.values():
            items.sort(key=lambda item: self._point_series_order(item["series"]))
            count = len(items)
            for index, item in enumerate(items):
                offset = self._point_overlap_offset(index, count)
                point = item["point"]
                draw_items.append(
                    {
                        "series": item["series"],
                        "point": QPointF(point.x() + offset.x(), point.y() + offset.y()),
                    }
                )

        draw_items.sort(key=lambda item: self._point_series_order(item["series"]))
        for item in draw_items:
            name = item["series"]
            point = item["point"]
            color = QColor(self._series_color(name))
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawEllipse(point, 5.3, 5.3)
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#111111"), 1))
            painter.drawEllipse(point, 4.0, 4.0)

    def _point_overlap_offset(self, index, count):
        if count <= 1:
            return QPointF(0.0, 0.0)
        radius = 5.0 if count <= 4 else 6.5
        angle = (2.0 * math.pi * float(index)) / float(count)
        return QPointF(math.cos(angle) * radius, math.sin(angle) * radius)

    def _point_series_order(self, name):
        order = {
            NODE_DENSITY_LABEL: 0,
            "Standard": 0,
            "Dispersal": 1,
            "Vicariance": 2,
            "Extinction": 3,
            TOTAL_EVENTS_LABEL: 4,
        }
        return order.get(str(name), 10)

    def _series_names(self):
        names = []
        for row in self.series_rows:
            for name in dict(row.get("values", {}) or {}).keys():
                if name not in names:
                    names.append(name)
        return names

    def _series_color(self, name):
        palette = {
            "Dispersal": "#d95f02",
            "Vicariance": "#1b9e77",
            "Extinction": "#7570b3",
            TOTAL_EVENTS_LABEL: "#e7298a",
            NODE_DENSITY_LABEL: "#444444",
            "Standard": "#444444",
            "A": "#e41a1c",
            "B": "#377eb8",
            "C": "#4daf4a",
            "D": "#984ea3",
        }
        if name in palette:
            return palette[name]
        fallback = [
            "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
            "#a65628", "#f781bf", "#999999", "#66c2a5", "#fc8d62",
        ]
        idx = sum(ord(ch) for ch in str(name)) % len(fallback)
        return fallback[idx]

    def _format_number(self, value):
        try:
            number = float(value)
        except Exception:
            return str(value)
        if abs(number - round(number)) < 1e-6:
            return str(int(round(number)))
        return ("%.2f" % number).rstrip("0").rstrip(".")

    def _tick_values(self, max_value, step):
        max_value = max(float(max_value or 0.0), 0.0)
        if max_value <= 0:
            return [0.0, 1.0]
        step = float(step or 0.0)
        if step <= 0:
            step = max_value / 5.0
        while step > 0 and max_value / step > 60:
            step *= 2.0
        ticks = []
        value = 0.0
        guard = 0
        while value <= max_value + step * 0.25 and guard < 200:
            ticks.append(min(value, max_value))
            value += step
            guard += 1
        if not ticks or abs(ticks[-1] - max_value) > max(step, 1e-9) * 0.25:
            ticks.append(max_value)
        return ticks

    def _axis_time_label(self, plot_time, max_time):
        plot_time = float(plot_time or 0.0)
        max_time = float(max_time or 0.0)
        if self.reverse_time_axis:
            return max(0.0, max_time - plot_time)
        return plot_time


class LegacyTimePanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_result = None
        self.current_node_payloads = []
        self.selected_clade_key = ""
        self.current_rows = []
        self.current_points = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        controls = QGridLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(6)
        controls.setVerticalSpacing(4)

        self.mode_combo = QComboBox(self)
        self.mode_combo.addItem("Event", "event")
        self.mode_combo.addItem("Area", "area")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.mode_combo.setMinimumWidth(72)

        self.series_combo = QComboBox(self)
        self.series_combo.currentIndexChanged.connect(self._redraw)
        self.series_combo.setMinimumWidth(72)
        self.series_combo.setToolTip("Choose all series, isolate one series, or hide one series.")

        self.root_time_spin = QDoubleSpinBox(self)
        self.root_time_spin.setRange(0.000001, 10 ** 9)
        self.root_time_spin.setDecimals(6)
        self.root_time_spin.setValue(1.0)
        self.root_time_spin.setMaximumWidth(110)

        self.unit_time_spin = QDoubleSpinBox(self)
        self.unit_time_spin.setRange(0.000001, 10 ** 6)
        self.unit_time_spin.setDecimals(4)
        self.unit_time_spin.setValue(1.0)
        self.unit_time_spin.setMaximumWidth(110)

        self.x_spacing_spin = QDoubleSpinBox(self)
        self.x_spacing_spin.setRange(0.000001, 10 ** 9)
        self.x_spacing_spin.setDecimals(4)
        self.x_spacing_spin.setValue(1.0)
        self.x_spacing_spin.valueChanged.connect(self._redraw)
        self.x_spacing_spin.setMaximumWidth(110)

        self.y_spacing_spin = QDoubleSpinBox(self)
        self.y_spacing_spin.setRange(0.000001, 10 ** 9)
        self.y_spacing_spin.setDecimals(4)
        self.y_spacing_spin.setValue(1.0)
        self.y_spacing_spin.valueChanged.connect(self._redraw)
        self.y_spacing_spin.setMaximumWidth(110)

        self.single_clade_check = QCheckBox("Single Clade", self)
        self.single_clade_check.toggled.connect(self._redraw)
        self.parent_event_check = QCheckBox("Events happened on parent node", self)
        self.parent_event_check.toggled.connect(self._redraw)
        self.parent_event_check.setToolTip("Events happened on parent node")
        self.show_points_check = QCheckBox("Show Point", self)
        self.show_points_check.toggled.connect(self._redraw)
        self.show_lines_check = QCheckBox("Show Line", self)
        self.show_lines_check.setChecked(True)
        self.show_lines_check.toggled.connect(self._redraw)
        self.show_legend_check = QCheckBox("Show Legend", self)
        self.show_legend_check.setChecked(True)
        self.show_legend_check.toggled.connect(self._redraw)
        self.reverse_time_check = QCheckBox("Reverse time", self)
        self.reverse_time_check.toggled.connect(self._redraw)
        self.reverse_time_check.setToolTip("Reverse plotted node/event positions and reverse the time-axis labels.")

        self.node_combo = QComboBox(self)
        self.node_combo.currentIndexChanged.connect(self._redraw)

        self.calculate_button = QPushButton("Calculate", self)
        self.calculate_button.clicked.connect(self._redraw)
        self.save_diagram_button = QPushButton("Save Diagram", self)
        self.save_diagram_button.clicked.connect(self._save_diagram)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        controls.addWidget(QLabel("Mode:"), 0, 0)
        controls.addWidget(self.mode_combo, 0, 1)
        controls.addWidget(QLabel("Show:"), 0, 2)
        controls.addWidget(self.series_combo, 0, 3)
        controls.addWidget(QLabel("Root time:"), 1, 0)
        controls.addWidget(self.root_time_spin, 1, 1)
        controls.addWidget(QLabel("Unit time:"), 1, 2)
        controls.addWidget(self.unit_time_spin, 1, 3)
        controls.addWidget(QLabel("X Spacing:"), 2, 0)
        controls.addWidget(self.x_spacing_spin, 2, 1)
        controls.addWidget(QLabel("Y Spacing:"), 2, 2)
        controls.addWidget(self.y_spacing_spin, 2, 3)
        controls.addWidget(QLabel("Node:"), 3, 0)
        controls.addWidget(self.node_combo, 3, 1, 1, 3)

        checks = QGridLayout()
        checks.setContentsMargins(0, 0, 0, 0)
        checks.setHorizontalSpacing(8)
        checks.setVerticalSpacing(2)
        checks.addWidget(self.single_clade_check, 0, 0)
        checks.addWidget(self.parent_event_check, 0, 1)
        checks.addWidget(self.show_points_check, 1, 0)
        checks.addWidget(self.show_lines_check, 1, 1)
        checks.addWidget(self.show_legend_check, 2, 0)
        checks.addWidget(self.reverse_time_check, 2, 1)

        bottom_controls = QHBoxLayout()
        bottom_controls.setContentsMargins(0, 0, 0, 0)
        bottom_controls.addWidget(self.calculate_button)
        bottom_controls.addWidget(self.save_diagram_button)
        bottom_controls.addWidget(self.progress, 1)

        self.diagram = LegacyTimeDiagramWidget(self)
        self.output_text = QTextEdit(self)
        self.output_text.setReadOnly(True)
        self.output_text.setAcceptRichText(False)
        self.output_text.setLineWrapMode(QTextEdit.NoWrap)
        self.output_text.setStyleSheet("font-family: Consolas, 'Courier New', monospace;")

        splitter = QSplitter(Qt.Vertical, self)
        splitter.addWidget(self.diagram)
        splitter.addWidget(self.output_text)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addLayout(controls)
        layout.addLayout(checks)
        layout.addLayout(bottom_controls)
        layout.addWidget(splitter, 1)
        self.setMinimumWidth(260)

    def minimumSizeHint(self):
        return QSize(260, 320)

    def sizeHint(self):
        return QSize(340, 520)

    def set_result(self, result, node_payloads) -> None:
        self.current_result = result
        self.current_node_payloads = list(node_payloads or [])
        data = self._time_data()
        root_age = float(data.get("root_age", 0.0) or 0.0)
        if root_age > 0:
            self.root_time_spin.blockSignals(True)
            self.x_spacing_spin.blockSignals(True)
            self.y_spacing_spin.blockSignals(True)
            self.root_time_spin.setValue(root_age)
            self.x_spacing_spin.setValue(max(root_age / 5.0, 1.0))
            self.y_spacing_spin.setValue(1.0)
            self.root_time_spin.blockSignals(False)
            self.x_spacing_spin.blockSignals(False)
            self.y_spacing_spin.blockSignals(False)
        self._refresh_node_combo()
        self._refresh_series_combo()
        self._redraw()

    def clear(self) -> None:
        self.current_result = None
        self.current_node_payloads = []
        self.selected_clade_key = ""
        self.output_text.setText("No time/event data is available.")
        self.diagram.set_plot_data(
            series_rows=[],
            point_rows=[],
            series_filter="All",
            show_points=False,
            show_lines=True,
            show_legend=True,
            x_grid_step=1.0,
            y_grid_step=1.0,
            reverse_time_axis=False,
        )

    def set_selected_clade(self, clade_key: str) -> None:
        self.selected_clade_key = str(clade_key or "").strip()
        if self.selected_clade_key:
            for index in range(self.node_combo.count()):
                if str(self.node_combo.itemData(index) or "") == self.selected_clade_key:
                    self.node_combo.blockSignals(True)
                    self.node_combo.setCurrentIndex(index)
                    self.node_combo.blockSignals(False)
                    break
        self._redraw()

    def _time_data(self):
        if self.current_result is None:
            return {}
        return dict(getattr(self.current_result, "heuristic_time_data", {}) or {})

    def _events(self):
        return list(self._time_data().get("events", []) or [])

    def _on_mode_changed(self) -> None:
        self._refresh_series_combo()
        self._redraw()

    def _refresh_node_combo(self) -> None:
        self.node_combo.blockSignals(True)
        self.node_combo.clear()
        payloads = list(self.current_node_payloads or [])
        payloads.sort(key=NodeInfoPanel._node_sort_key)
        for payload in payloads:
            display_id = str(getattr(payload, "display_node_id", "") or "").strip()
            clade_key = str(getattr(payload, "clade_key", "") or "").strip()
            if not display_id or not clade_key:
                continue
            self.node_combo.addItem("node %s" % display_id, clade_key)
        self.node_combo.blockSignals(False)

    def _refresh_series_combo(self) -> None:
        mode = self._mode()
        names = self._series_names(mode)
        current = str(self.series_combo.currentData() or self.series_combo.currentText() or "All")
        self.series_combo.blockSignals(True)
        self.series_combo.clear()
        self.series_combo.addItem("All", "All")
        for name in names:
            self.series_combo.addItem("Only: %s" % name, "only:%s" % name)
        for name in names:
            self.series_combo.addItem("Hide: %s" % name, "hide:%s" % name)
        index = self.series_combo.findData(current)
        self.series_combo.setCurrentIndex(index if index >= 0 else 0)
        self.series_combo.blockSignals(False)

    def _mode(self):
        return str(self.mode_combo.currentData() or "event")

    def _series_names(self, mode):
        if mode == "area":
            return [str(x) for x in list(self._time_data().get("area_names", []) or []) if str(x)]
        return ["Dispersal", "Vicariance", "Extinction", TOTAL_EVENTS_LABEL, NODE_DENSITY_LABEL]

    def _redraw(self) -> None:
        data = self._time_data()
        events = self._filtered_events()
        if not data or not events:
            fallback = str(getattr(self.current_result, "time_summary_text", "") or "No time/event data is available.")
            self.output_text.setText(fallback)
            self.diagram.set_plot_data(
                series_rows=[],
                point_rows=[],
                series_filter="All",
                show_points=False,
                show_lines=True,
                show_legend=True,
                x_grid_step=1.0,
                y_grid_step=1.0,
                reverse_time_axis=self.reverse_time_check.isChecked(),
            )
            self.progress.setValue(0)
            return

        mode = self._mode()
        rows, points = self._calculate_rows(events, mode)
        text = self._format_rows(rows, mode)
        self.output_text.setText(text)
        self.diagram.set_plot_data(
            series_rows=rows,
            point_rows=points,
            series_filter=str(self.series_combo.currentData() or "All"),
            show_points=self.show_points_check.isChecked(),
            show_lines=self.show_lines_check.isChecked(),
            show_legend=self.show_legend_check.isChecked(),
            x_grid_step=float(self.x_spacing_spin.value()),
            y_grid_step=float(self.y_spacing_spin.value()),
            reverse_time_axis=self.reverse_time_check.isChecked(),
        )
        self.progress.setValue(100)

    def _filtered_events(self):
        events = self._events()
        if not self.single_clade_check.isChecked():
            return events
        clade_key = str(self.node_combo.currentData() or self.selected_clade_key or "").strip()
        if not clade_key:
            return events
        selected_taxa = set([x for x in clade_key.split("|") if x])
        if not selected_taxa:
            return events
        filtered = []
        for event in events:
            taxa = set([x for x in str(event.get("clade_key", "") or "").split("|") if x])
            if taxa and taxa.issubset(selected_taxa):
                filtered.append(event)
        return filtered or events

    def _calculate_rows(self, events, mode):
        raw_root_age = float(self._time_data().get("root_age", 0.0) or 0.0)
        display_root_age = float(self.root_time_spin.value())
        if raw_root_age <= 0:
            raw_root_age = max([0.0] + [float(e.get("node_age", 0.0) or 0.0) for e in events])
        if display_root_age <= 0:
            display_root_age = raw_root_age or 1.0
        scale = display_root_age / raw_root_age if raw_root_age > 0 else 1.0
        unit_time = float(self.unit_time_spin.value()) * display_root_age / max(1.0, float(len(events)))
        if unit_time <= 0:
            unit_time = display_root_age / 50.0
        bins = self._diagram_sample_count(display_root_age)
        names = self._series_names(mode)
        parent_map = self._parent_age_map(self._events())
        use_parent_events = self.parent_event_check.isChecked() and mode == "event"
        extra_standard_locs = []
        if use_parent_events and self.single_clade_check.isChecked():
            selected_key = str(self.node_combo.currentData() or self.selected_clade_key or "").strip()
            if selected_key in parent_map:
                extra_standard_locs.append(self._scaled_raw_age(parent_map[selected_key], scale, display_root_age))

        rows = []
        points = []
        for idx in range(bins + 1):
            time_value = display_root_age * float(idx) / float(bins)
            axis_time = self._axis_time_label(time_value, display_root_age)
            values = {name: 0.0 for name in names}
            for event in events:
                if mode == "area":
                    loc = self._scaled_event_age(event, scale, display_root_age)
                    weight = math.exp(-((time_value - loc) / unit_time) ** 2 / 2.0)
                    area_probs = dict(event.get("area_probabilities", {}) or {})
                    for name in names:
                        values[name] += float(area_probs.get(name, 0.0) or 0.0) * weight
                else:
                    key = str(event.get("clade_key", "") or "")
                    standard_loc = self._scaled_event_age(event, scale, display_root_age)
                    standard_weight = math.exp(-((time_value - standard_loc) / unit_time) ** 2 / 2.0)
                    if use_parent_events:
                        if key not in parent_map:
                            continue
                        event_loc = self._scaled_raw_age(parent_map[key], scale, display_root_age)
                    else:
                        event_loc = standard_loc
                    event_weight = math.exp(-((time_value - event_loc) / unit_time) ** 2 / 2.0)
                    dispersal = int(event.get("dispersal", 0) or 0)
                    vicariance = int(event.get("vicariance", 0) or 0)
                    extinction = int(event.get("extinction", 0) or 0)
                    values["Dispersal"] += dispersal * event_weight
                    values["Vicariance"] += vicariance * event_weight
                    values["Extinction"] += extinction * event_weight
                    values[TOTAL_EVENTS_LABEL] += (dispersal + vicariance + extinction) * event_weight
                    values[NODE_DENSITY_LABEL] += standard_weight
            for standard_loc in extra_standard_locs:
                values[NODE_DENSITY_LABEL] += math.exp(-((time_value - standard_loc) / unit_time) ** 2 / 2.0)
            rows.append({"time": time_value, "label_time": axis_time, "values": values})

        for event in events:
            if mode == "area":
                loc = self._scaled_event_age(event, scale, display_root_age)
                area_probs = dict(event.get("area_probabilities", {}) or {})
                for name in names:
                    points.append({"time": loc, "series": name, "value": float(area_probs.get(name, 0.0) or 0.0)})
            else:
                key = str(event.get("clade_key", "") or "")
                standard_loc = self._scaled_event_age(event, scale, display_root_age)
                if use_parent_events:
                    if key not in parent_map:
                        continue
                    event_loc = self._scaled_raw_age(parent_map[key], scale, display_root_age)
                else:
                    event_loc = standard_loc
                dispersal = int(event.get("dispersal", 0) or 0)
                vicariance = int(event.get("vicariance", 0) or 0)
                extinction = int(event.get("extinction", 0) or 0)
                points.extend([
                    {"time": event_loc, "series": "Dispersal", "value": dispersal},
                    {"time": event_loc, "series": "Vicariance", "value": vicariance},
                    {"time": event_loc, "series": "Extinction", "value": extinction},
                    {"time": event_loc, "series": TOTAL_EVENTS_LABEL, "value": dispersal + vicariance + extinction},
                    {"time": standard_loc, "series": NODE_DENSITY_LABEL, "value": 1.0},
                ])
        for standard_loc in extra_standard_locs:
            points.append({"time": standard_loc, "series": NODE_DENSITY_LABEL, "value": 1.0})
        return rows, points

    def _scaled_event_age(self, event, scale, display_root_age, parent_map=None):
        key = str(event.get("clade_key", "") or "")
        raw = float(event.get("node_age", 0.0) or 0.0)
        if parent_map and key in parent_map:
            raw = float(parent_map[key])
        return self._scaled_raw_age(raw, scale, display_root_age)

    def _scaled_raw_age(self, raw, scale, display_root_age):
        raw = float(raw or 0.0)
        value = raw * scale
        if self.reverse_time_check.isChecked():
            value = display_root_age - value
        return max(0.0, min(display_root_age, value))

    def _axis_time_label(self, plot_time, display_root_age):
        plot_time = float(plot_time or 0.0)
        display_root_age = float(display_root_age or 0.0)
        if self.reverse_time_check.isChecked():
            return max(0.0, display_root_age - plot_time)
        return plot_time

    def _diagram_sample_count(self, display_root_age):
        width = int(self.diagram.width() or self.diagram.sizeHint().width() or 0)
        smooth_x = 1.0
        if display_root_age > 0:
            smooth_x = 1.0 + float(max(width, 1)) / float(display_root_age)
        return max(40, min(4000, int(max(1.0, float(display_root_age)) * smooth_x)))

    def _parent_age_map(self, events):
        keyed = []
        for event in events:
            key = str(event.get("clade_key", "") or "")
            taxa = set([x for x in key.split("|") if x])
            if taxa:
                keyed.append((key, taxa, float(event.get("node_age", 0.0) or 0.0)))
        parent = {}
        for key, taxa, _age in keyed:
            candidates = [
                (len(parent_taxa), parent_key, parent_age)
                for parent_key, parent_taxa, parent_age in keyed
                if taxa < parent_taxa
            ]
            if candidates:
                candidates.sort(key=lambda item: item[0])
                parent[key] = candidates[0][2]
        return parent

    def _format_rows(self, rows, mode):
        names = self._series_names(mode)
        title = "AreaLine" if mode == "area" else "EventLine"
        lines = [
            "%s" % title,
            "TIME\t" + "\t".join(names),
        ]
        for row in rows:
            values = dict(row.get("values", {}) or {})
            label_time = row.get("label_time", row.get("time", 0.0))
            lines.append(
                "%s\t%s"
                % (
                    self._format_number(label_time),
                    "\t".join(self._format_number(values.get(name, 0.0)) for name in names),
                )
            )
        return "\n".join(lines)

    def _format_number(self, value):
        try:
            number = float(value)
        except Exception:
            return str(value)
        if abs(number - round(number)) < 1e-9:
            return str(int(round(number)))
        return ("%.4f" % number).rstrip("0").rstrip(".")

    def _save_diagram(self) -> None:
        file_path, _selected = QFileDialog.getSaveFileName(
            self,
            "Save Diagram",
            "",
            "PNG Files (*.png);;SVG Files (*.svg)",
        )
        if not file_path:
            return
        try:
            lower = file_path.lower()
            if lower.endswith(".svg"):
                from PyQt5.QtCore import QSize
                from PyQt5.QtSvg import QSvgGenerator

                generator = QSvgGenerator()
                generator.setFileName(file_path)
                generator.setSize(QSize(max(1, self.diagram.width()), max(1, self.diagram.height())))
                painter = QPainter(generator)
                self.diagram.render(painter)
                painter.end()
            else:
                if not lower.endswith(".png"):
                    file_path += ".png"
                self.diagram.grab().save(file_path, "PNG")
        except Exception as exc:
            QMessageBox.critical(self, "Save Diagram failed", str(exc))


class NodeInfoPanel(QWidget):
    state_color_changed = pyqtSignal(str, str)
    node_entry_clicked = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.current_method_name = ""
        self.current_result = None
        self.current_payload = None
        self.current_standard_payload = None
        self.current_node_payloads = []

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(6)

        self.top_tabs = QTabWidget()

        self.list_tab = QWidget()
        self.list_tab_layout = QVBoxLayout(self.list_tab)
        self.list_tab_layout.setContentsMargins(4, 4, 4, 4)
        self.list_tab_layout.setSpacing(6)

        self.list_table = QTableWidget()
        self.list_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.list_table.setSelectionMode(QTableWidget.SingleSelection)
        self.list_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.list_table.setAlternatingRowColors(True)
        self.list_table.verticalHeader().setVisible(False)
        self.list_table.horizontalHeader().setStretchLastSection(True)
        self.list_table.cellClicked.connect(self._on_list_table_clicked)
        self.list_table.setStyleSheet(
            """
            QTableWidget::item:selected {
                background-color: #2d7ff9;
                color: white;
            }
            QTableWidget::item:selected:!active {
                background-color: #2d7ff9;
                color: white;
            }
            """
        )
        self.list_tab_layout.addWidget(self.list_table, 3)

        self.inner_tabs = QTabWidget()

        self.legend_tab = QWidget()
        self.legend_layout = QVBoxLayout(self.legend_tab)
        self.legend_layout.setContentsMargins(4, 4, 4, 4)
        self.legend_layout.setSpacing(6)

        self.selected_node_title = QLabel("当前未选中节点")
        self.selected_node_title.setWordWrap(True)
        self.legend_layout.addWidget(self.selected_node_title)

        self.legend_note = QLabel("")
        self.legend_note.setWordWrap(True)
        self.legend_layout.addWidget(self.legend_note)

        self.legend_table = QTableWidget()
        self.legend_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.legend_table.setSelectionMode(QTableWidget.NoSelection)
        self.legend_table.setAlternatingRowColors(True)
        self.legend_table.verticalHeader().setVisible(False)
        self.legend_table.horizontalHeader().setStretchLastSection(True)
        self.legend_layout.addWidget(self.legend_table, 1)

        self.color_tab = QWidget()
        self.color_layout = QVBoxLayout(self.color_tab)
        self.color_layout.setContentsMargins(4, 4, 4, 4)
        self.color_layout.setSpacing(6)

        self.color_tip = QLabel("双击颜色单元格可修改状态颜色，并同步刷新树渲染。")
        self.color_tip.setWordWrap(True)
        self.color_layout.addWidget(self.color_tip)

        self.color_table = QTableWidget()
        self.color_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.color_table.setSelectionMode(QTableWidget.SingleSelection)
        self.color_table.setAlternatingRowColors(True)
        self.color_table.verticalHeader().setVisible(False)
        self.color_table.horizontalHeader().setStretchLastSection(True)
        self.color_table.cellDoubleClicked.connect(self._on_color_table_double_clicked)
        self.color_layout.addWidget(self.color_table, 1)

        self.inner_tabs.addTab(self.legend_tab, "Legend")
        self.inner_tabs.addTab(self.color_tab, "Color")
        self.list_tab_layout.addWidget(self.inner_tabs, 2)

        self.info_tab = QWidget()
        self.info_layout = QVBoxLayout(self.info_tab)
        self.info_layout.setContentsMargins(8, 8, 8, 8)
        self.info_placeholder = QTextEdit()
        self.info_placeholder.setReadOnly(True)
        self.info_placeholder.setAcceptRichText(False)
        self.info_placeholder.setLineWrapMode(QTextEdit.NoWrap)
        self.info_placeholder.setStyleSheet("font-family: Consolas, 'Courier New', monospace;")
        self.info_layout.addWidget(self.info_placeholder)

        self.time_tab = QWidget()
        self.time_layout = QVBoxLayout(self.time_tab)
        self.time_layout.setContentsMargins(8, 8, 8, 8)
        self.time_panel = LegacyTimePanel(self.time_tab)
        self.time_placeholder = self.time_panel.output_text
        self.time_layout.addWidget(self.time_panel)

        self.top_tabs.addTab(self.list_tab, "List")
        self.top_tabs.addTab(self.info_tab, "Information")
        self.top_tabs.addTab(self.time_tab, "Time")

        self.main_layout.addWidget(self.top_tabs)
        self.setLayout(self.main_layout)

        self.clear_info()

    def minimumSizeHint(self):
        return QSize(260, 420)

    def sizeHint(self):
        return QSize(320, 700)

    def clear_info(self) -> None:
        self.current_payload = None
        self.current_standard_payload = None

        self.list_table.clear()
        self.list_table.setRowCount(0)
        self.list_table.setColumnCount(0)

        self.selected_node_title.setText("当前未选中节点")
        self.legend_note.setText("")

        self.legend_table.clear()
        self.legend_table.setRowCount(0)
        self.legend_table.setColumnCount(0)

        self.color_table.clear()
        self.color_table.setRowCount(0)
        self.color_table.setColumnCount(0)

        self.info_placeholder.setText("Information 页暂不实现")
        self.time_placeholder.setText("Time 页暂不实现")

    def set_standard_result(self, method_name: str, result, node_payloads: list) -> None:
        self.current_method_name = method_name or ""
        self.current_result = result
        self.current_node_payloads = list(node_payloads or [])

        self._refresh_list_tab()
        self._refresh_color_tab()
        self._clear_selected_node_legend()
        self._refresh_information_tabs()

    def show_basic_node_info(self, payload: dict) -> None:
        self.current_payload = payload
        self.current_standard_payload = None

        if not payload:
            self._show_global_legend()
            return

        if "error" in payload:
            self.selected_node_title.setText(str(payload.get("error", "")))
            self.legend_note.setText("")
            self._clear_legend_table()
            return

        name = str(payload.get("name", "") or "")
        clade = str(payload.get("clade_signature", "") or "")
        node_id = str(payload.get("node_id", "") or "")

        lines = []
        if name:
            lines.append(f"名称: {name}")
        if node_id:
            lines.append(f"内部编号: {node_id}")
        if clade:
            lines.append(f"Clade: {clade}")

        self.selected_node_title.setText("\n".join(lines) if lines else "当前未选中节点")
        self.legend_note.setText("当前节点暂无方法结果，下面显示全局状态图例。")
        self._show_global_legend(title_override=self.selected_node_title.text())

    def show_standard_node_info(self, tree_payload: dict, standard_payload) -> None:
        self.current_payload = tree_payload
        self.current_standard_payload = standard_payload
        self._refresh_selected_legend(tree_payload, standard_payload)
        self.time_panel.set_selected_clade(str(getattr(standard_payload, "clade_key", "") or ""))

    def show_message(self, text: str) -> None:
        self.selected_node_title.setText(text or "")
        self.legend_note.setText("")
        self._clear_legend_table()

    def _refresh_information_tabs(self) -> None:
        result = self.current_result
        if result is None:
            self.info_placeholder.setText("No result information is available.")
            self.time_placeholder.setText("No time/event data is available.")
            return

        info_text = str(getattr(result, "information_text", "") or "").strip()
        time_text = str(getattr(result, "time_summary_text", "") or "").strip()

        if not info_text:
            info_lines = [
                "%s result summary" % (self.current_method_name or type(result).__name__),
                "",
                "Internal nodes: %d" % len(getattr(result, "node_results", {}) or {}),
            ]
            warnings = list(getattr(result, "parse_warnings", []) or [])
            if warnings:
                info_lines.append("Warnings: %d" % len(warnings))
                for warning in warnings[:20]:
                    info_lines.append("  " + str(warning))
            info_text = "\n".join(info_lines)

        failure_reasons = list(getattr(result, "tree_failure_reasons", []) or [])
        if failure_reasons and "TREE-SET FAILURE DETAILS" not in info_text:
            failure_lines = ["", "TREE-SET FAILURE DETAILS:"]
            failure_lines.extend("  " + str(reason) for reason in failure_reasons)
            info_text += "\n".join(failure_lines)

        if not time_text:
            time_text = (
                "No structured time/event data is attached to this result."
            )

        self.info_placeholder.setText(info_text)
        self.time_placeholder.setText(time_text)
        self.time_panel.set_result(result, self.current_node_payloads)
        if not getattr(result, "heuristic_time_data", None) and time_text:
            self.time_panel.output_text.setText(time_text)

    def select_row_by_clade_key(self, clade_key: str) -> None:
        clade_key = str(clade_key or "").strip()

        self.list_table.blockSignals(True)
        self.list_table.clearSelection()

        if not clade_key:
            self.list_table.blockSignals(False)
            return

        for row in range(self.list_table.rowCount()):
            item = self.list_table.item(row, 0)
            if item is None:
                continue
            row_clade_key = item.data(Qt.UserRole)
            if str(row_clade_key or "") == clade_key:
                self.list_table.selectRow(row)
                self.list_table.setCurrentCell(row, 0)
                self.list_table.setFocus(Qt.OtherFocusReason)
                break

        self.list_table.blockSignals(False)

    def clear_list_selection(self) -> None:
        self.list_table.blockSignals(True)
        self.list_table.clearSelection()
        self.list_table.setCurrentItem(None)
        self.list_table.blockSignals(False)

    def _on_list_table_clicked(self, row: int, column: int) -> None:
        item = self.list_table.item(row, 0)
        if item is None:
            return

        clade_key = item.data(Qt.UserRole)
        if not clade_key:
            return

        self.node_entry_clicked.emit(str(clade_key))

    def _refresh_list_tab(self) -> None:
        self.list_table.clear()

        payloads = list(self.current_node_payloads or [])
        if not payloads:
            self.list_table.setRowCount(0)
            self.list_table.setColumnCount(0)
            return

        # S-DIVA：只显示已经成功映射到参考树 DIVA 原生节点号的节点
        if self.current_method_name == "S-DIVA":
            payloads = [
                p for p in payloads
                if str(getattr(p, "display_node_id", "") or "").strip()
            ]

        payloads.sort(key=self._node_sort_key)
        compact_summaries = len(payloads) >= 500

        rows = []
        for payload in payloads:
            display_id = str(getattr(payload, "display_node_id", "") or "").strip()
            display_text = f"node {display_id}"
            summary = self._list_state_summary(payload, compact=compact_summaries)
            rows.append((display_text, summary, str(getattr(payload, "clade_key", "") or "")))

        self.list_table.setRowCount(len(rows))
        self.list_table.setColumnCount(2)
        summary_header = "Continuous value" if self._is_continuous_result() else "Optimal reconstruction"
        self.list_table.setHorizontalHeaderLabels(["节点号", summary_header])

        for row_idx, (display_id, summary, clade_key) in enumerate(rows):
            id_item = QTableWidgetItem(display_id)
            id_item.setData(Qt.UserRole, clade_key)
            summary_item = QTableWidgetItem(summary)
            self.list_table.setItem(row_idx, 0, id_item)
            self.list_table.setItem(row_idx, 1, summary_item)

        self.list_table.resizeColumnsToContents()
        self.list_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.list_table.horizontalHeader().setStretchLastSection(True)

    def _list_state_summary(self, payload, compact=False) -> str:
        summary = str(getattr(payload, "state_summary", "") or "无")
        if not compact or self._is_continuous_result():
            return summary

        labels = [
            str(value).strip()
            for value in list(getattr(payload, "state_labels", []) or [])
            if str(value).strip()
        ]
        supports = dict(getattr(payload, "state_supports", {}) or {})
        if supports:
            items = [
                (str(state).strip(), float(probability or 0.0))
                for state, probability in supports.items()
                if str(state).strip()
            ]
            items.sort(key=lambda item: (-item[1], item[0]))
            shown = items[:4]
            text = ", ".join("%s %.2f%%" % (state, probability) for state, probability in shown)
            remaining = max(0, len(items) - len(shown))
        else:
            shown_labels = labels[:4]
            text = ", ".join(shown_labels)
            remaining = max(0, len(labels) - len(shown_labels))

        if remaining:
            text += " (+%d more)" % remaining
        return text or summary

    def _refresh_color_tab(self) -> None:
        if self.current_result is None:
            self.color_table.clear()
            self.color_table.setRowCount(0)
            self.color_table.setColumnCount(0)
            return

        headers = ["Range", "Color"]
        rows = self._legend_rows_for_result()

        self._populate_table(
            self.color_table,
            headers,
            rows,
            color_column=1,
            color_text_mode="double_click",
        )

    def _refresh_selected_legend(self, tree_payload: dict, standard_payload) -> None:
        name = ""
        clade = ""
        if tree_payload:
            name = str(tree_payload.get("name", "") or "")
            clade = str(tree_payload.get("clade_signature", "") or "")

        lines = []
        if name:
            lines.append(f"名称: {name}")

        display_node_id = str(getattr(standard_payload, "display_node_id", "") or "").strip()
        if display_node_id:
            lines.append(f"节点号: {display_node_id}")
        elif getattr(standard_payload, "display_id_source", ""):
            lines.append("节点号: 未映射")

        if clade:
            lines.append(f"Clade: {clade}")

        support_summary = str(getattr(standard_payload, "support_summary", "") or "")
        if support_summary:
            lines.append(support_summary)

        self.selected_node_title.setText("\n".join(lines) if lines else "当前未选中节点")

        interpretation_note = str(getattr(standard_payload, "interpretation_note", "") or "")
        self.legend_note.setText(interpretation_note)

        raw = dict(getattr(standard_payload, "raw_method_payload", {}) or {})
        states = [str(x).strip() for x in list(raw.get("states", []) or []) if str(x).strip()]
        pie_labels = [str(x).strip() for x in list(raw.get("pie_labels", []) or []) if str(x).strip()]
        pie_percents = list(raw.get("pie_percents", []) or [])
        pie_colors = list(raw.get("pie_colors", []) or [])
        state_counts = dict(raw.get("state_counts", {}) or {})
        state_supports = dict(raw.get("state_supports", {}) or {})

        color_map = {}
        source_labels = pie_labels or states
        for idx, state in enumerate(source_labels):
            if idx < len(pie_colors):
                color_map[state] = pie_colors[idx]

        rows = []
        headers = []
        color_column = -1

        if bool(raw.get("continuous", False)):
            display_scale = str(raw.get("display_scale", raw.get("trait_scale", raw.get("trait_transform", "none"))))
            headers = ["Field", "Value"]
            rows = [
                ["Trait", str(raw.get("trait_name", ""))],
                ["Display scale", display_scale],
                ["Plot scale", str(raw.get("plot_scale", raw.get("trait_scale", raw.get("trait_transform", "none"))))],
                ["Mean", "%.6g" % float(raw.get("display_mean", raw.get("mean", 0.0)) or 0.0)],
                ["Median", "%.6g" % float(raw.get("display_median", raw.get("median", 0.0)) or 0.0)],
                ["Lower 95%", "%.6g" % float(raw.get("display_lower95", raw.get("lower95", 0.0)) or 0.0)],
                ["Upper 95%", "%.6g" % float(raw.get("display_upper95", raw.get("upper95", 0.0)) or 0.0)],
                ["Samples", str(raw.get("sample_count", ""))],
            ]
            if str(raw.get("trait_display_scale", "analysis")) == "original":
                rows.extend([
                    ["Analysis scale", str(raw.get("trait_scale", raw.get("trait_transform", "none")))],
                    ["Analysis mean", "%.6g" % float(raw.get("analysis_mean", raw.get("mean", 0.0)) or 0.0)],
                    ["Analysis median", "%.6g" % float(raw.get("analysis_median", raw.get("median", 0.0)) or 0.0)],
                ])
        elif state_supports and self.current_method_name == "S-DIVA":
            headers = ["State", "Support (%)", "Color"]
            for state in states or list(state_supports.keys()):
                rows.append([
                    state,
                    f"{float(state_supports.get(state, 0.0)):.2f}",
                    color_map.get(state, "#808080"),
                ])
            color_column = 2
        elif state_supports:
            headers = ["状态", "加权计数", "支持比例(%)", "颜色"]
            for state in states or list(state_supports.keys()):
                rows.append([
                    state,
                    f"{float(state_counts.get(state, 0.0)):.4f}",
                    f"{float(state_supports.get(state, 0.0)):.2f}",
                    color_map.get(state, "#808080"),
                ])
            color_column = 3
        elif pie_labels and pie_percents:
            headers = ["状态", "比例(%)", "颜色"]
            for idx, state in enumerate(pie_labels):
                percent = pie_percents[idx] if idx < len(pie_percents) else 0.0
                rows.append([
                    state,
                    f"{float(percent):.2f}",
                    color_map.get(state, "#808080"),
                ])
            color_column = 2
        elif states:
            headers = ["状态", "颜色"]
            for state in states:
                rows.append([state, color_map.get(state, "#808080")])
            color_column = 1
        else:
            headers = ["字段", "内容"]
            rows = [["说明", "当前节点无可展示图例字段"]]

        self._populate_table(
            self.legend_table,
            headers=headers,
            rows=rows,
            color_column=color_column,
            color_text_mode="blank",
        )

    def _on_color_table_double_clicked(self, row: int, column: int) -> None:
        if self.current_result is None:
            return
        if column != 1:
            return

        state_item = self.color_table.item(row, 0)
        color_item = self.color_table.item(row, 1)
        if state_item is None or color_item is None:
            return

        state = state_item.text().strip().split(" (", 1)[0].strip()
        old_color = color_item.data(Qt.UserRole) or "#808080"

        qcolor = QColorDialog.getColor(QColor(old_color), self, f"选择状态颜色：{state}")
        if not qcolor.isValid():
            return

        new_color = qcolor.name()
        color_item.setData(Qt.UserRole, new_color)
        color_item.setBackground(QBrush(QColor(new_color)))
        color_item.setText("Double Click")

        self.state_color_changed.emit(state, new_color)

    def _show_global_legend_legacy_old(self, title_override: str = "") -> None:
        if self.current_result is None:
            self.selected_node_title.setText(title_override or "当前未选中节点")
            self.legend_note.setText("")
            self._clear_legend_table()
            return

        self.selected_node_title.setText(title_override or "当前未选中节点")
        self.legend_note.setText("当前未选中节点，下面显示全局状态图例。")

        state_order = list(getattr(self.current_result, "state_order", []) or [])
        state_colors = dict(getattr(self.current_result, "state_colors", {}) or {})

        rows = []
        for state in state_order:
            rows.append([state, state_colors.get(state, "#808080")])

        self._populate_table(
            self.legend_table,
            headers=["状态", "颜色"],
            rows=rows,
            color_column=1,
            color_text_mode="blank",
        )

    def _clear_legend_table(self) -> None:
        self.legend_table.clear()
        self.legend_table.setRowCount(0)
        self.legend_table.setColumnCount(0)

    def _clear_selected_node_legend(self) -> None:
        self.current_standard_payload = None
        self._show_global_legend()

    def _is_continuous_result(self) -> bool:
        return type(self.current_result).__name__ == "ContinuousTraitResult"

    def _legend_rows_for_result(self) -> list:
        state_order = list(getattr(self.current_result, "state_order", []) or [])
        state_colors = dict(getattr(self.current_result, "state_colors", {}) or {})
        if not self._is_continuous_result():
            return [[state, state_colors.get(state, "#808080")] for state in state_order]

        if not state_order:
            state_order = ["Low", "20%", "40%", "60%", "80%", "High"]
        vmin = float(getattr(self.current_result, "color_scale_min", 0.0) or 0.0)
        vmax = float(getattr(self.current_result, "color_scale_max", vmin + 1.0) or (vmin + 1.0))
        if vmax <= vmin:
            vmax = vmin + 1.0
        denom = max(1, len(state_order) - 1)
        rows = []
        for index, label in enumerate(state_order):
            fraction = float(index) / float(denom)
            value = vmin + (vmax - vmin) * fraction
            display_value = self._continuous_display_value(value)
            rows.append(["%s (%.4g)" % (str(label), display_value), state_colors.get(label, "#808080")])
        return rows

    def _continuous_display_value(self, value) -> float:
        result = self.current_result
        display_scale = str(getattr(result, "trait_display_scale", "analysis") or "analysis")
        plot_scale = str(getattr(result, "trait_plot_scale", "analysis") or "analysis")
        transform = str(getattr(result, "trait_transform", "none") or "none")
        number = float(value)
        if display_scale == plot_scale:
            return number
        if display_scale != "original":
            if plot_scale == "original" and transform == "log" and number > 0.0:
                return math.log(number)
            if plot_scale == "original" and transform == "log10" and number > 0.0:
                return math.log10(number)
            return number
        if plot_scale == "original":
            return number
        if transform == "log":
            return math.exp(number)
        if transform == "log10":
            return 10.0 ** number
        return number

    def _show_global_legend(self, title_override: str = "") -> None:
        if self.current_result is None:
            self.selected_node_title.setText(title_override or "Current node")
            self.legend_note.setText("")
            self._clear_legend_table()
            return

        self.selected_node_title.setText(title_override or "Current node")
        headers = ["Scale", "Color"] if self._is_continuous_result() else ["State", "Color"]
        if self._is_continuous_result():
            trait_name = str(getattr(self.current_result, "trait_name", "") or "").strip()
            transform = str(getattr(self.current_result, "trait_transform", "none") or "none")
            display_scale = str(getattr(self.current_result, "trait_display_scale", "analysis") or "analysis")
            plot_scale = str(getattr(self.current_result, "trait_plot_scale", "analysis") or "analysis")
            suffix = ": " + trait_name if trait_name else ""
            if plot_scale == "original" and display_scale == "original" and transform != "none":
                self.legend_note.setText(
                    "Continuous color scale%s. Colors and labels use back-transformed original values."
                    % suffix
                )
            elif plot_scale == "original" and transform != "none":
                self.legend_note.setText(
                    "Continuous color scale%s. Colors use back-transformed original values; labels use %s values."
                    % (suffix, transform)
                )
            elif display_scale == "original" and transform != "none":
                self.legend_note.setText(
                    "Continuous color scale%s. Colors use %s values; labels are back-transformed."
                    % (suffix, transform)
                )
            else:
                self.legend_note.setText("Continuous color scale%s." % suffix)
        else:
            self.legend_note.setText("Global state legend.")

        self._populate_table(
            self.legend_table,
            headers=headers,
            rows=self._legend_rows_for_result(),
            color_column=1,
            color_text_mode="blank",
        )

    def _populate_table(
        self,
        table: QTableWidget,
        headers: list,
        rows: list,
        color_column: int = -1,
        color_text_mode: str = "keep",
    ) -> None:
        table.clear()
        table.setRowCount(len(rows))
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                if col_idx == color_column:
                    color_value = str(value)
                    item.setData(Qt.UserRole, color_value)
                    item.setBackground(QBrush(QColor(color_value)))
                    item.setTextAlignment(Qt.AlignCenter)

                    if color_text_mode == "blank":
                        item.setText("")
                    elif color_text_mode == "double_click":
                        item.setText("Double Click")
                    else:
                        item.setText(color_value)

                table.setItem(row_idx, col_idx, item)

        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)

    @staticmethod
    def _node_sort_key(payload) -> tuple:
        display_id = str(getattr(payload, "display_node_id", "") or "").strip()
        if display_id.isdigit():
            return (0, int(display_id), str(getattr(payload, "clade_key", "") or ""))
        return (1, 10 ** 9, str(getattr(payload, "clade_key", "") or ""))

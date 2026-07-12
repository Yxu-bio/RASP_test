import csv
import math
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QBrush, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from application.services.bsm_dispersal_network_service import BSMDispersalNetworkService


class _NetworkGraphicsView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)

    def fit_to_scene(self):
        scene = self.scene()
        if scene is None:
            return
        rect = scene.itemsBoundingRect()
        if not rect.isNull():
            self.fitInView(rect.adjusted(-30, -30, 30, 30), Qt.KeepAspectRatio)


class BSMEventTableDialog(QDialog):
    def __init__(self, result, area_records=None, range_matrix=None, parent=None):
        super().__init__(parent)
        self.result = result
        self.area_records = list(area_records or [])
        self.range_matrix = range_matrix
        self.network_service = BSMDispersalNetworkService()
        self.current_network = None
        self.all_events = list(getattr(self.result, "events", []) or [])
        self.filtered_events = list(self.all_events)
        self.setWindowTitle("BioGeoBEARS BSM Event Table")
        self.resize(1180, 720)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_events_tab(), "Events")
        self.tabs.addTab(self._build_summary_tab(), "Summary")
        self.tabs.addTab(self._build_time_tab(), "Time")
        self.tabs.addTab(self._build_raw_tab(), "Raw tables")
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_filtered_views()

    def _build_events_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)

        top = QHBoxLayout()
        self.export_events_button = QPushButton("Export events CSV", page)
        self.export_events_button.clicked.connect(self._export_events_csv)
        self.events_caption_label = QLabel(self._events_caption(), page)
        top.addWidget(self.events_caption_label)
        top.addStretch(1)
        top.addWidget(self.export_events_button)
        layout.addLayout(top)

        filters = QGridLayout()
        filters.setContentsMargins(0, 0, 0, 0)
        filters.setHorizontalSpacing(6)
        filters.setVerticalSpacing(4)
        self.scope_combo = self._build_filter_combo(["anagenetic", "cladogenetic"], page)
        self.event_type_combo = self._build_filter_combo(self._unique_event_values("event_type"), page)
        self.source_combo = self._build_filter_combo(self._unique_event_values("source_range"), page)
        self.target_combo = self._build_filter_combo(self._unique_event_values("target_range"), page)
        self.node_combo = self._build_filter_combo(self._unique_event_values("node"), page)
        self.branch_combo = self._build_filter_combo(self._unique_event_values("branch"), page)
        self.time_min_edit = QLineEdit(page)
        self.time_min_edit.setPlaceholderText("min")
        self.time_max_edit = QLineEdit(page)
        self.time_max_edit.setPlaceholderText("max")
        self.search_edit = QLineEdit(page)
        self.search_edit.setPlaceholderText("text search")
        self.reset_filters_button = QPushButton("Reset filters", page)
        self.reset_filters_button.clicked.connect(self._reset_filters)

        filters.addWidget(QLabel("Scope", page), 0, 0)
        filters.addWidget(self.scope_combo, 0, 1)
        filters.addWidget(QLabel("Type", page), 0, 2)
        filters.addWidget(self.event_type_combo, 0, 3)
        filters.addWidget(QLabel("Source", page), 0, 4)
        filters.addWidget(self.source_combo, 0, 5)
        filters.addWidget(QLabel("Target", page), 0, 6)
        filters.addWidget(self.target_combo, 0, 7)
        filters.addWidget(QLabel("Time", page), 1, 0)
        filters.addWidget(self.time_min_edit, 1, 1)
        filters.addWidget(self.time_max_edit, 1, 2)
        filters.addWidget(QLabel("Node", page), 1, 3)
        filters.addWidget(self.node_combo, 1, 4)
        filters.addWidget(QLabel("Branch", page), 1, 5)
        filters.addWidget(self.branch_combo, 1, 6)
        filters.addWidget(self.reset_filters_button, 1, 7)
        filters.addWidget(QLabel("Search", page), 2, 0)
        filters.addWidget(self.search_edit, 2, 1, 1, 7)
        layout.addLayout(filters)

        for combo in [
            self.scope_combo,
            self.event_type_combo,
            self.source_combo,
            self.target_combo,
            self.node_combo,
            self.branch_combo,
        ]:
            combo.currentIndexChanged.connect(self._apply_filters)
        self.time_min_edit.textChanged.connect(self._apply_filters)
        self.time_max_edit.textChanged.connect(self._apply_filters)
        self.search_edit.textChanged.connect(self._apply_filters)

        self.events_table = QTableWidget(page)
        self.events_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.events_table.setAlternatingRowColors(True)
        layout.addWidget(self.events_table, 1)
        return page

    def _build_summary_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)
        self.summary_text = QTextEdit(page)
        self.summary_text.setReadOnly(True)
        layout.addWidget(self.summary_text)
        return page

    def _build_network_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Minimum mean dispersal events per map:", page))
        self.network_threshold_edit = QLineEdit(page)
        self.network_threshold_edit.setText("5")
        self.network_threshold_edit.setPlaceholderText("5")
        self.network_threshold_edit.editingFinished.connect(self._refresh_network_tab)
        controls.addWidget(self.network_threshold_edit)
        self.network_include_anagenetic_check = QCheckBox("Anagenetic d/a", page)
        self.network_include_anagenetic_check.setChecked(True)
        self.network_include_anagenetic_check.toggled.connect(self._refresh_network_tab)
        controls.addWidget(self.network_include_anagenetic_check)
        self.network_include_founder_check = QCheckBox("Founder-event j", page)
        self.network_include_founder_check.setChecked(True)
        self.network_include_founder_check.toggled.connect(self._refresh_network_tab)
        controls.addWidget(self.network_include_founder_check)
        self.network_show_edge_values_check = QCheckBox("Show edge values", page)
        self.network_show_edge_values_check.setChecked(True)
        self.network_show_edge_values_check.toggled.connect(self._redraw_network_tab)
        controls.addWidget(self.network_show_edge_values_check)
        self.network_refresh_button = QPushButton("Refresh", page)
        self.network_refresh_button.clicked.connect(self._refresh_network_tab)
        controls.addWidget(self.network_refresh_button)
        controls.addStretch(1)
        self.export_network_edges_button = QPushButton("Export edge CSV", page)
        self.export_network_edges_button.clicked.connect(self._export_network_edges_csv)
        controls.addWidget(self.export_network_edges_button)
        self.export_network_nodes_button = QPushButton("Export node CSV", page)
        self.export_network_nodes_button.clicked.connect(self._export_network_nodes_csv)
        controls.addWidget(self.export_network_nodes_button)
        self.export_network_geojson_button = QPushButton("Export GeoJSON", page)
        self.export_network_geojson_button.clicked.connect(self._export_network_geojson)
        controls.addWidget(self.export_network_geojson_button)
        layout.addLayout(controls)

        self.network_caption_label = QLabel("", page)
        self.network_caption_label.setWordWrap(True)
        layout.addWidget(self.network_caption_label)

        splitter = QSplitter(Qt.Horizontal, page)
        left = QWidget(splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.network_table = QTableWidget(left)
        self.network_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.network_table.setAlternatingRowColors(True)
        left_layout.addWidget(self.network_table, 1)

        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.network_scene = QGraphicsScene(right)
        self.network_view = _NetworkGraphicsView(right)
        self.network_view.setScene(self.network_scene)
        self.network_summary_text = QTextEdit(right)
        self.network_summary_text.setReadOnly(True)
        self.network_summary_text.setMaximumHeight(170)
        right_layout.addWidget(self.network_view, 1)
        right_layout.addWidget(self.network_summary_text)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)
        return page

    def _build_time_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Bin size (Ma; 0 = exact):", page))
        self.time_bin_edit = QLineEdit(page)
        self.time_bin_edit.setPlaceholderText("0")
        self.time_bin_edit.setText("0")
        self.time_bin_edit.textChanged.connect(self._apply_filters)
        controls.addWidget(self.time_bin_edit)
        controls.addWidget(QLabel("Direction:", page))
        self.time_direction_combo = QComboBox(page)
        self.time_direction_combo.addItem("Young to old (ascending Ma)", "ascending")
        self.time_direction_combo.addItem("Old to young (descending Ma)", "descending")
        self.time_direction_combo.currentIndexChanged.connect(self._apply_filters)
        controls.addWidget(self.time_direction_combo)
        controls.addStretch(1)
        self.export_time_button = QPushButton("Export time CSV", page)
        self.export_time_button.clicked.connect(self._export_time_csv)
        controls.addWidget(self.export_time_button)
        layout.addLayout(controls)
        self.time_table = QTableWidget(page)
        self.time_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.time_table.setAlternatingRowColors(True)
        layout.addWidget(self.time_table, 1)
        return page

    def _build_raw_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Table:", page))
        self.raw_table_combo = QComboBox(page)
        raw_tables = dict(getattr(self.result, "raw_tables", {}) or {})
        for name in sorted(raw_tables.keys()):
            self.raw_table_combo.addItem(name, name)
        self.raw_table_combo.currentIndexChanged.connect(self._populate_raw_table)
        controls.addWidget(self.raw_table_combo)
        controls.addStretch(1)
        self.export_raw_button = QPushButton("Export raw CSV", page)
        self.export_raw_button.clicked.connect(self._export_raw_csv)
        controls.addWidget(self.export_raw_button)
        layout.addLayout(controls)

        self.raw_table = QTableWidget(page)
        self.raw_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.raw_table.setAlternatingRowColors(True)
        layout.addWidget(self.raw_table, 1)
        return page

    def _events_caption(self):
        summary = dict(getattr(self.result, "summary", {}) or {})
        maps = summary.get("nummaps", "")
        prefix = "%d / %d BSM events" % (len(self.filtered_events), len(self.all_events))
        if maps != "":
            prefix += " from %s stochastic maps" % maps
        return prefix

    def _populate_events_table(self):
        events = list(self.filtered_events or [])
        headers = [
            "scope",
            "sample_id",
            "time",
            "node",
            "branch",
            "event_type",
            "event_text",
            "source_range",
            "target_range",
            "dispersal_to",
            "extirpation_from",
        ]
        rows = []
        for event in events:
            rows.append([
                getattr(event, "event_scope", ""),
                getattr(event, "sample_id", ""),
                "" if getattr(event, "time", None) is None else "%.6g" % float(event.time),
                getattr(event, "node", ""),
                getattr(event, "branch", ""),
                getattr(event, "event_type", ""),
                getattr(event, "event_text", ""),
                getattr(event, "source_range", ""),
                getattr(event, "target_range", ""),
                getattr(event, "dispersal_to", ""),
                getattr(event, "extirpation_from", ""),
            ])
        self._fill_table(self.events_table, headers, rows)

    def _populate_time_table(self):
        rows = self._build_time_series(self.filtered_events)
        keys = []
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(key)
        if "time" in keys:
            keys = ["time"] + [key for key in keys if key != "time"]
        elif "time_bin_start" in keys or "time_bin_end" in keys or "time_bin_label" in keys:
            preferred = ["time_bin_start", "time_bin_end", "time_bin_label"]
            keys = [key for key in preferred if key in keys] + [key for key in keys if key not in preferred]
        table_rows = [[row.get(key, "") for key in keys] for row in rows]
        self._fill_table(self.time_table, keys, table_rows)

    def _populate_raw_table(self):
        if not hasattr(self, "raw_table"):
            return
        name = self.raw_table_combo.currentData() if hasattr(self, "raw_table_combo") else ""
        raw_tables = dict(getattr(self.result, "raw_tables", {}) or {})
        rows = list(raw_tables.get(str(name), []) or [])
        display_rows = rows[:5000]
        headers = []
        for row in display_rows:
            for key in row.keys():
                if key not in headers:
                    headers.append(key)
        table_rows = [[row.get(key, "") for key in headers] for row in display_rows]
        self._fill_table(self.raw_table, headers, table_rows)

    def _summary_text(self, events=None):
        events = list(self.filtered_events if events is None else events)
        event_type_counts = Counter(self._event_count_key(event) for event in events)
        route_counts = Counter(self._event_route_key(event) for event in events if self._event_route_key(event))
        lines = []
        lines.append("BioGeoBEARS BSM event summary")
        lines.append("")
        lines.append("Source model: %s" % str(getattr(self.result, "source_model_name", "") or "BioGeoBEARS"))
        lines.append("Filtered events: %d / %d" % (len(events), len(self.all_events)))
        metadata = self._filter_metadata()
        active_filters = [
            "%s=%s" % (key, value)
            for key, value in metadata.items()
            if str(value).strip() and str(value).strip().lower() not in ("all", "")
        ]
        if active_filters:
            lines.append("Filters: %s" % "; ".join(active_filters))
        lines.append("")
        lines.append("Event counts")
        if event_type_counts:
            for key, value in sorted(event_type_counts.items(), key=lambda x: (-int(x[1]), x[0])):
                lines.append("  %s: %s" % (key, value))
        else:
            lines.append("  none")
        if route_counts:
            lines.append("")
            lines.append("Top event routes")
            for route, value in sorted(route_counts.items(), key=lambda x: (-int(x[1]), x[0]))[:20]:
                lines.append("  %s: %s" % (route, value))
        summary = dict(getattr(self.result, "summary", {}) or {})
        if summary:
            lines.append("")
            lines.append("BSM run metadata")
            for key in sorted(summary.keys()):
                lines.append("%s: %s" % (key, summary.get(key)))
        return "\n".join([line for line in lines if line is not None])

    def _build_filter_combo(self, values, parent):
        combo = QComboBox(parent)
        combo.addItem("All", "")
        for value in sorted({str(item).strip() for item in list(values or []) if str(item).strip()}):
            combo.addItem(value, value)
        return combo

    def _unique_event_values(self, attribute):
        values = []
        for event in self.all_events:
            value = str(getattr(event, attribute, "") or "").strip()
            if value:
                values.append(value)
        return values

    def _apply_filters(self, *args):
        if not hasattr(self, "events_table"):
            return
        self.filtered_events = [
            event for event in self.all_events
            if self._event_matches_filters(event)
        ]
        self._refresh_filtered_views()

    def _refresh_filtered_views(self):
        if hasattr(self, "events_caption_label"):
            self.events_caption_label.setText(self._events_caption())
        if hasattr(self, "events_table"):
            self._populate_events_table()
        if hasattr(self, "summary_text"):
            self.summary_text.setPlainText(self._summary_text())
        if hasattr(self, "time_table"):
            self._populate_time_table()
        if hasattr(self, "raw_table"):
            self._populate_raw_table()
        if hasattr(self, "network_table"):
            if self.current_network is None:
                self._refresh_network_tab()

    def _refresh_network_tab(self, *args):
        if not hasattr(self, "network_table"):
            return
        threshold = self._safe_float_or_none(getattr(self, "network_threshold_edit").text())
        if threshold is None:
            threshold = 5.0
        try:
            network = self.network_service.build_network(
                self.result,
                areas=self.area_records,
                range_matrix=self.range_matrix,
                min_mean_per_map=threshold,
                include_anagenetic=self.network_include_anagenetic_check.isChecked(),
                include_founder=self.network_include_founder_check.isChecked(),
            )
        except Exception as exc:
            self.network_caption_label.setText("Could not build dispersal network: %s" % exc)
            self.current_network = None
            self._fill_table(self.network_table, [], [])
            self.network_scene.clear()
            self.network_summary_text.setPlainText(str(exc))
            return
        self.current_network = network
        self._populate_network_table(network)
        self._draw_network_preview(network)
        self._populate_network_summary(network)

    def _redraw_network_tab(self, *args):
        if self.current_network:
            self._draw_network_preview(self.current_network)

    def _populate_network_table(self, network):
        rows = list(network.get("display_edge_rows", []) or [])
        headers = [
            "source_area",
            "target_area",
            "source_name",
            "target_name",
            "mean_per_map",
            "total_count",
            "anagenetic_count",
            "founder_count",
        ]
        table_rows = []
        for row in rows:
            table_rows.append([
                row.get("source_area", ""),
                row.get("target_area", ""),
                row.get("source_name", ""),
                row.get("target_name", ""),
                self._format_number(row.get("mean_per_map", "")),
                self._format_number(row.get("total_count", "")),
                self._format_number(row.get("anagenetic_count", "")),
                self._format_number(row.get("founder_count", "")),
            ])
        self._fill_table(self.network_table, headers, table_rows)
        self.network_caption_label.setText(
            "Showing %d / %d directed dispersal edges. Threshold: mean events per stochastic map >= %s. "
            "Exports keep full numeric counts; GeoJSON uses currently visible edges."
            % (
                len(rows),
                len(network.get("edge_rows", []) or []),
                self._format_number(network.get("min_mean_per_map", 0)),
            )
        )

    def _populate_network_summary(self, network):
        edge_rows = list(network.get("edge_rows", []) or [])
        display_rows = list(network.get("display_edge_rows", []) or [])
        total_mean = sum(float(row.get("mean_per_map", 0.0) or 0.0) for row in edge_rows)
        visible_mean = sum(float(row.get("mean_per_map", 0.0) or 0.0) for row in display_rows)
        lines = [
            "BSM dispersal network",
            "",
            "Stochastic maps: %s" % network.get("nummaps", ""),
            "All directed edges: %d" % len(edge_rows),
            "Visible directed edges: %d" % len(display_rows),
            "Total mean dispersal events/map: %s" % self._format_number(total_mean),
            "Visible mean dispersal events/map: %s" % self._format_number(visible_mean),
            "Node richness source: current range matrix; multi-area taxa are split equally.",
            "Source handling: multi-area source ranges are split equally across possible source areas.",
        ]
        warnings = list(network.get("warnings", []) or [])
        if warnings:
            lines.append("")
            lines.append("Warnings")
            for warning in warnings:
                lines.append("  %s" % warning)
        if display_rows:
            lines.append("")
            lines.append("Top visible edges")
            for row in display_rows[:12]:
                lines.append(
                    "  %s -> %s: %s/map"
                    % (
                        row.get("source_area", ""),
                        row.get("target_area", ""),
                        self._format_number(row.get("mean_per_map", "")),
                    )
                )
        self.network_summary_text.setPlainText("\n".join(lines))

    def _draw_network_preview(self, network):
        self.network_scene.clear()
        areas = list(self.area_records or [])
        node_rows = list(network.get("node_rows", []) or [])
        edge_rows = list(network.get("display_edge_rows", []) or [])
        bounds = self._network_bounds(areas, node_rows)
        if bounds is None:
            self.network_scene.setSceneRect(0, 0, 900, 520)
            label = QGraphicsSimpleTextItem("Load area GeoJSON in Spatial Data Manager to preview the network on a map.")
            label.setBrush(QBrush(QColor(60, 70, 80)))
            label.setPos(20, 20)
            self.network_scene.addItem(label)
            return
        transform = self._network_transform(bounds)
        node_geometry = self._network_node_geometry(node_rows, transform)
        self._draw_network_areas(areas, transform)
        self._draw_network_edges(edge_rows, transform, node_geometry)
        self._draw_network_nodes(node_rows, transform, node_geometry)
        rect = self.network_scene.itemsBoundingRect().adjusted(-30, -30, 30, 30)
        self.network_scene.setSceneRect(rect)
        self.network_view.fit_to_scene()

    def _draw_network_areas(self, areas, transform):
        for index, area in enumerate(areas):
            path = self._network_path_from_geometry(getattr(area, "geometry", {}) or {}, transform)
            if path.isEmpty():
                continue
            color = self._network_color(getattr(area, "color", "") or "", index)
            item = QGraphicsPathItem(path)
            item.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 34)))
            item.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 130), 0.7))
            item.setZValue(0)
            self.network_scene.addItem(item)

    def _draw_network_edges(self, edge_rows, transform, node_geometry):
        if not edge_rows:
            return
        max_mean = max(float(row.get("mean_per_map", 0.0) or 0.0) for row in edge_rows) or 1.0
        show_values = bool(
            getattr(self, "network_show_edge_values_check", None) is not None
            and self.network_show_edge_values_check.isChecked()
        )
        label_limit = min(12, len(edge_rows)) if show_values else 0
        curve_by_pair = self._network_curve_by_pair(edge_rows)
        for index, row in enumerate(edge_rows):
            lon1 = self._safe_float_or_none(row.get("source_lon"))
            lat1 = self._safe_float_or_none(row.get("source_lat"))
            lon2 = self._safe_float_or_none(row.get("target_lon"))
            lat2 = self._safe_float_or_none(row.get("target_lat"))
            if None in (lon1, lat1, lon2, lat2):
                continue
            x1, y1 = transform(lon1, lat1)
            x2, y2 = transform(lon2, lat2)
            dx = x2 - x1
            dy = y2 - y1
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1e-6:
                continue
            nx = -dy / length
            ny = dx / length
            curve = self._network_edge_curve(row, index, curve_by_pair)
            cx = (x1 + x2) * 0.5 + nx * curve
            cy = (y1 + y2) * 0.5 + ny * curve
            target_geom = node_geometry.get(str(row.get("target_area", "") or ""), {})
            clip_radius = float(target_geom.get("radius", 0.0) or 0.0)
            draw_cx, draw_cy, draw_x2, draw_y2, end_t = self._clip_quadratic_to_target_radius(
                x1, y1, cx, cy, x2, y2, clip_radius + 2.5
            )
            mean = float(row.get("mean_per_map", 0.0) or 0.0)
            width = 0.7 + 7.0 * math.sqrt(mean / max_mean)
            line_cx, line_cy, line_x2, line_y2 = self._line_base_before_arrow_head(
                x1, y1, draw_cx, draw_cy, draw_x2, draw_y2, width
            )
            path = QPainterPath(QPointF(x1, y1))
            path.quadTo(QPointF(line_cx, line_cy), QPointF(line_x2, line_y2))
            alpha = 70 + int(150 * math.sqrt(mean / max_mean))
            source_geom = node_geometry.get(str(row.get("source_area", "") or ""), {})
            source_color = QColor(str(source_geom.get("color", "") or ""))
            if not source_color.isValid():
                source_color = QColor(43, 91, 155)
            color = QColor(source_color.red(), source_color.green(), source_color.blue(), min(230, alpha))
            item = QGraphicsPathItem(path)
            pen = QPen(color, width)
            pen.setCapStyle(Qt.FlatCap)
            item.setPen(pen)
            item.setZValue(12)
            item.setToolTip(
                "%s -> %s\n%s mean events/map"
                % (row.get("source_area", ""), row.get("target_area", ""), self._format_number(mean))
            )
            self.network_scene.addItem(item)
            self._draw_network_arrow_head(line_x2, line_y2, draw_x2, draw_y2, color, width)
            if index < label_limit:
                self._draw_network_edge_label(
                    row, mean, color, x1, y1, draw_cx, draw_cy, draw_x2, draw_y2, curve, end_t
                )

    def _network_curve_by_pair(self, edge_rows):
        pair_keys = []
        for row in list(edge_rows or []):
            source = str(row.get("source_area", "") or "")
            target = str(row.get("target_area", "") or "")
            if not source or not target:
                continue
            key = tuple(sorted([source, target]))
            if key not in pair_keys:
                pair_keys.append(key)
        pair_keys.sort()
        curves = {}
        for index, key in enumerate(pair_keys):
            lane = index % 4
            curves[key] = 20.0 + lane * 10.0
        return curves

    def _network_edge_curve(self, row, index, curve_by_pair):
        source = str(row.get("source_area", "") or "")
        target = str(row.get("target_area", "") or "")
        if source and target and source != target:
            sign = 1.0 if source < target else -1.0
            base = float(curve_by_pair.get(tuple(sorted([source, target])), 24.0))
        else:
            sign = 1.0 if index % 2 == 0 else -1.0
            base = 24.0
        return base * sign

    def _draw_network_edge_label(self, row, mean, color, x1, y1, cx, cy, x2, y2, curve, end_t=1.0):
        t = max(0.18, min(0.82, 0.52 * max(0.15, float(end_t or 1.0))))
        px, py = self._quadratic_point(x1, y1, cx, cy, x2, y2, t)
        tx, ty = self._quadratic_tangent(x1, y1, cx, cy, x2, y2, t)
        length = math.sqrt(tx * tx + ty * ty)
        if length < 1e-6:
            return
        nx = -ty / length
        ny = tx / length
        side = 1.0 if curve >= 0 else -1.0
        gap = 1.5
        lx = px + nx * gap * side
        ly = py + ny * gap * side

        label = QGraphicsSimpleTextItem(self._format_network_value(mean, decimals=1))
        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        label.setFont(font)
        label_color = QColor(22, 28, 36)
        label.setBrush(QBrush(label_color))
        label.setToolTip(
            "%s -> %s\n%s mean events/map"
            % (row.get("source_area", ""), row.get("target_area", ""), self._format_number(mean))
        )
        rect = label.boundingRect()
        label.setPos(lx - rect.width() * 0.5, ly - rect.height() * 0.5)
        label.setZValue(25)
        self.network_scene.addItem(label)

    def _quadratic_point(self, x1, y1, cx, cy, x2, y2, t):
        one = 1.0 - t
        x = one * one * x1 + 2.0 * one * t * cx + t * t * x2
        y = one * one * y1 + 2.0 * one * t * cy + t * t * y2
        return x, y

    def _quadratic_tangent(self, x1, y1, cx, cy, x2, y2, t):
        x = 2.0 * (1.0 - t) * (cx - x1) + 2.0 * t * (x2 - cx)
        y = 2.0 * (1.0 - t) * (cy - y1) + 2.0 * t * (y2 - cy)
        return x, y

    def _line_base_before_arrow_head(self, x1, y1, cx, cy, x2, y2, width):
        head_length = max(9.0, float(width or 0.0) * 3.0)
        samples = []
        for index in range(0, 41):
            t = float(index) / 40.0
            px, py = self._quadratic_point(x1, y1, cx, cy, x2, y2, t)
            samples.append((t, px, py))
        distance = 0.0
        for index in range(len(samples) - 1, 0, -1):
            t1, px1, py1 = samples[index]
            _t0, px0, py0 = samples[index - 1]
            dx = px1 - px0
            dy = py1 - py0
            segment = math.sqrt(dx * dx + dy * dy)
            if segment < 1e-6:
                continue
            if distance + segment >= head_length:
                remaining = head_length - distance
                ratio = remaining / segment
                base_x = px1 - dx * ratio
                base_y = py1 - dy * ratio
                # Approximate the sub-curve control with De Casteljau using the
                # nearest t. This keeps the curve tangent stable enough for the
                # short arrow-base gap.
                t = max(0.02, min(1.0, t1 - (1.0 / 40.0) * ratio))
                line_cx = x1 + (cx - x1) * t
                line_cy = y1 + (cy - y1) * t
                return line_cx, line_cy, base_x, base_y
            distance += segment
        return cx, cy, x2, y2

    def _draw_network_arrow_head(self, base_x, base_y, tip_x, tip_y, color, width):
        tx = tip_x - base_x
        ty = tip_y - base_y
        length = math.sqrt(tx * tx + ty * ty)
        if length < 1e-6:
            return
        ux = tx / length
        uy = ty / length
        size = max(7.0, width * 2.0)
        nx = -uy
        ny = ux
        polygon = QPolygonF([
            QPointF(tip_x, tip_y),
            QPointF(base_x + nx * size * 0.45, base_y + ny * size * 0.45),
            QPointF(base_x - nx * size * 0.45, base_y - ny * size * 0.45),
        ])
        item = QGraphicsPolygonItem(polygon)
        item.setBrush(QBrush(color))
        item.setPen(QPen(Qt.NoPen))
        item.setZValue(13)
        self.network_scene.addItem(item)

    def _clip_quadratic_to_target_radius(self, x1, y1, cx, cy, x2, y2, radius):
        radius = max(0.0, float(radius or 0.0))
        if radius <= 0.0:
            return cx, cy, x2, y2, 1.0
        dx = x2 - x1
        dy = y2 - y1
        if math.sqrt(dx * dx + dy * dy) <= radius:
            return cx, cy, x2, y2, 1.0
        low = 0.0
        high = 1.0
        for _ in range(24):
            mid = (low + high) * 0.5
            px, py = self._quadratic_point(x1, y1, cx, cy, x2, y2, mid)
            dist = math.sqrt((px - x2) * (px - x2) + (py - y2) * (py - y2))
            if dist > radius:
                low = mid
            else:
                high = mid
        t = max(0.05, min(1.0, low))
        end_x, end_y = self._quadratic_point(x1, y1, cx, cy, x2, y2, t)
        sub_cx = x1 + (cx - x1) * t
        sub_cy = y1 + (cy - y1) * t
        return sub_cx, sub_cy, end_x, end_y, t

    def _network_node_geometry(self, node_rows, transform):
        rich_values = [float(row.get("richness", 0.0) or 0.0) for row in node_rows]
        max_rich = max(rich_values) if rich_values else 1.0
        if max_rich <= 0:
            max_rich = 1.0
        geometry = {}
        for row in node_rows:
            lon = self._safe_float_or_none(row.get("centroid_lon"))
            lat = self._safe_float_or_none(row.get("centroid_lat"))
            if lon is None or lat is None:
                continue
            x, y = transform(lon, lat)
            richness = float(row.get("richness", 0.0) or 0.0)
            radius = 7.0 + 21.0 * math.sqrt(richness / max_rich)
            geometry[str(row.get("area_code", "") or "")] = {
                "x": x,
                "y": y,
                "radius": radius,
                "richness": richness,
                "color": row.get("color", ""),
            }
        return geometry

    def _draw_network_nodes(self, node_rows, transform, node_geometry):
        for row in node_rows:
            code = str(row.get("area_code", "") or "")
            geom = node_geometry.get(code)
            if not geom:
                continue
            x = float(geom.get("x", 0.0) or 0.0)
            y = float(geom.get("y", 0.0) or 0.0)
            radius = float(geom.get("radius", 0.0) or 0.0)
            richness = float(geom.get("richness", 0.0) or 0.0)
            base = QColor(str(row.get("color", "") or ""))
            if not base.isValid():
                base = QColor(120, 150, 180)
            fill = QColor(base.red(), base.green(), base.blue(), 118)
            outline = QColor(base.red(), base.green(), base.blue(), 185)
            item = QGraphicsEllipseItem(x - radius, y - radius, radius * 2.0, radius * 2.0)
            item.setBrush(QBrush(fill))
            item.setPen(QPen(outline, 1.2))
            item.setZValue(30)
            item.setToolTip("%s\nrichness=%s" % (row.get("display_name", ""), self._format_number(richness)))
            self.network_scene.addItem(item)

            richness_label = QGraphicsSimpleTextItem(self._format_network_value(richness, decimals=0))
            richness_font = QFont()
            richness_font.setPixelSize(10)
            richness_font.setBold(True)
            richness_label.setFont(richness_font)
            richness_label.setBrush(QBrush(QColor(16, 22, 28)))
            richness_rect = richness_label.boundingRect()
            richness_label.setPos(x - richness_rect.width() * 0.5, y - richness_rect.height() * 0.5)
            richness_label.setZValue(32)
            self.network_scene.addItem(richness_label)

            name_label = QGraphicsSimpleTextItem("%s\n%s" % (code, row.get("display_name", "")))
            name_font = QFont()
            name_font.setPixelSize(9)
            name_font.setBold(True)
            name_label.setFont(name_font)
            name_label.setBrush(QBrush(QColor(34, 37, 41)))
            name_rect = name_label.boundingRect()
            label_x = x - name_rect.width() * 0.5
            label_y = y + radius + 3.0
            bg_rect = QRectF(
                label_x - 3.0,
                label_y - 1.5,
                name_rect.width() + 6.0,
                name_rect.height() + 3.0,
            )
            bg = QGraphicsRectItem(bg_rect)
            bg.setBrush(QBrush(QColor(255, 255, 255, 176)))
            bg.setPen(QPen(Qt.NoPen))
            bg.setZValue(31)
            self.network_scene.addItem(bg)
            name_label.setPos(label_x, label_y)
            name_label.setZValue(32)
            self.network_scene.addItem(name_label)

    def _network_bounds(self, areas, node_rows):
        bounds = None
        for area in areas:
            for lon, lat in self._network_geometry_points(getattr(area, "geometry", {}) or {}):
                bounds = self._merge_bounds(bounds, lon, lat)
        for row in node_rows:
            lon = self._safe_float_or_none(row.get("centroid_lon"))
            lat = self._safe_float_or_none(row.get("centroid_lat"))
            if lon is not None and lat is not None:
                bounds = self._merge_bounds(bounds, lon, lat)
        if bounds is None:
            return None
        min_lon, min_lat, max_lon, max_lat = bounds
        if abs(max_lon - min_lon) < 1e-9:
            min_lon -= 0.5
            max_lon += 0.5
        if abs(max_lat - min_lat) < 1e-9:
            min_lat -= 0.5
            max_lat += 0.5
        return min_lon, min_lat, max_lon, max_lat

    def _network_transform(self, bounds):
        min_lon, min_lat, max_lon, max_lat = bounds
        width = max(1e-9, float(max_lon) - float(min_lon))
        height = max(1e-9, float(max_lat) - float(min_lat))
        scale = min(980.0 / width, 580.0 / height)
        margin = 26.0

        def transform(lon, lat):
            return (
                margin + (float(lon) - float(min_lon)) * scale,
                margin + (float(max_lat) - float(lat)) * scale,
            )

        return transform

    def _network_path_from_geometry(self, geometry, transform):
        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)
        geometry_type = str(geometry.get("type", "") or "")
        coordinates = geometry.get("coordinates") or []
        polygons = [coordinates] if geometry_type == "Polygon" else list(coordinates or []) if geometry_type == "MultiPolygon" else []
        for polygon in polygons:
            for ring in list(polygon or []):
                points = list(ring or [])
                if len(points) > 1500:
                    stride = max(1, int(round(float(len(points)) / 1500.0)))
                    points = points[::stride] + [points[-1]]
                qpoints = []
                for point in points:
                    if len(point) < 2:
                        continue
                    x, y = transform(float(point[0]), float(point[1]))
                    qpoints.append(QPointF(x, y))
                if len(qpoints) >= 3:
                    path.addPolygon(QPolygonF(qpoints))
                    path.closeSubpath()
        return path

    def _network_geometry_points(self, geometry):
        geometry_type = str(geometry.get("type", "") or "")
        coordinates = geometry.get("coordinates") or []
        polygons = [coordinates] if geometry_type == "Polygon" else list(coordinates or []) if geometry_type == "MultiPolygon" else []
        for polygon in polygons:
            for ring in list(polygon or []):
                for point in list(ring or []):
                    if len(point) >= 2:
                        yield float(point[0]), float(point[1])

    def _network_color(self, color_text, index):
        color = QColor(str(color_text or ""))
        if color.isValid():
            return color
        palette = [
            "#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
            "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC", "#59A14F",
        ]
        return QColor(palette[index % len(palette)])

    def _merge_bounds(self, bounds, lon, lat):
        lon = float(lon)
        lat = float(lat)
        if bounds is None:
            return lon, lat, lon, lat
        min_lon, min_lat, max_lon, max_lat = bounds
        return min(min_lon, lon), min(min_lat, lat), max(max_lon, lon), max(max_lat, lat)

    def _reset_filters(self):
        for combo in [
            self.scope_combo,
            self.event_type_combo,
            self.source_combo,
            self.target_combo,
            self.node_combo,
            self.branch_combo,
        ]:
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        for edit in [self.time_min_edit, self.time_max_edit, self.search_edit]:
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
        if hasattr(self, "time_bin_edit"):
            self.time_bin_edit.blockSignals(True)
            self.time_bin_edit.setText("0")
            self.time_bin_edit.blockSignals(False)
        if hasattr(self, "time_direction_combo"):
            self.time_direction_combo.blockSignals(True)
            self.time_direction_combo.setCurrentIndex(0)
            self.time_direction_combo.blockSignals(False)
        self._apply_filters()

    def _event_matches_filters(self, event):
        metadata = self._filter_metadata()
        scope = str(getattr(event, "event_scope", "") or "").strip()
        event_type = str(getattr(event, "event_type", "") or "").strip()
        source = str(getattr(event, "source_range", "") or "").strip()
        target = str(getattr(event, "target_range", "") or "").strip()
        node = str(getattr(event, "node", "") or "").strip()
        branch = str(getattr(event, "branch", "") or "").strip()
        if metadata["scope"] and scope != metadata["scope"]:
            return False
        if metadata["event_type"] and event_type != metadata["event_type"]:
            return False
        if metadata["source_range"] and source != metadata["source_range"]:
            return False
        if metadata["target_range"] and target != metadata["target_range"]:
            return False
        if metadata["node"] and node != metadata["node"]:
            return False
        if metadata["branch"] and branch != metadata["branch"]:
            return False
        time_value = getattr(event, "time", None)
        if metadata["time_min"]:
            minimum = self._safe_float_or_none(metadata["time_min"])
            if minimum is not None and (time_value is None or float(time_value) < minimum):
                return False
        if metadata["time_max"]:
            maximum = self._safe_float_or_none(metadata["time_max"])
            if maximum is not None and (time_value is None or float(time_value) > maximum):
                return False
        search = metadata["search"].lower()
        if search:
            haystack = " ".join([
                scope,
                event_type,
                str(getattr(event, "event_text", "") or ""),
                source,
                target,
                str(getattr(event, "dispersal_to", "") or ""),
                str(getattr(event, "extirpation_from", "") or ""),
                str(getattr(event, "node", "") or ""),
                str(getattr(event, "branch", "") or ""),
            ]).lower()
            if search not in haystack:
                return False
        return True

    def _filter_metadata(self):
        def combo_value(name):
            widget = getattr(self, name, None)
            if widget is None:
                return ""
            return str(widget.currentData() or "").strip()

        def edit_value(name):
            widget = getattr(self, name, None)
            if widget is None:
                return ""
            return str(widget.text() or "").strip()

        return {
            "scope": combo_value("scope_combo"),
            "event_type": combo_value("event_type_combo"),
            "source_range": combo_value("source_combo"),
            "target_range": combo_value("target_combo"),
            "node": combo_value("node_combo"),
            "branch": combo_value("branch_combo"),
            "time_min": edit_value("time_min_edit"),
            "time_max": edit_value("time_max_edit"),
            "search": edit_value("search_edit"),
            "time_bin_size": edit_value("time_bin_edit"),
            "time_direction": combo_value("time_direction_combo") or "ascending",
        }

    def _build_time_series(self, events):
        buckets = defaultdict(lambda: Counter())
        bin_size = self._safe_float_or_none(self._filter_metadata().get("time_bin_size", ""))
        if bin_size is None or bin_size <= 0.0:
            bin_size = 0.0
        for event in list(events or []):
            if getattr(event, "time", None) is None:
                continue
            try:
                time_value = float(event.time)
            except Exception:
                continue
            if bin_size > 0.0:
                bin_start = math.floor(time_value / bin_size) * bin_size
                bin_end = bin_start + bin_size
                time_key = (round(bin_start, 6), round(bin_end, 6))
            else:
                time_key = round(time_value, 6)
            buckets[time_key][self._event_count_key(event)] += 1
            buckets[time_key]["total"] += 1

        rows = []
        reverse = self._filter_metadata().get("time_direction", "ascending") == "descending"
        for time_key in sorted(buckets.keys(), reverse=reverse):
            counter = buckets[time_key]
            if isinstance(time_key, tuple):
                row = {
                    "time_bin_start": time_key[0],
                    "time_bin_end": time_key[1],
                    "time_bin_label": "%s-%s" % (self._format_number(time_key[0]), self._format_number(time_key[1])),
                }
            else:
                row = {"time": time_key}
            for key, value in sorted(counter.items()):
                row[key] = int(value)
            rows.append(row)
        return rows

    def _event_count_key(self, event):
        event_type = str(getattr(event, "event_type", "") or "").strip()
        scope = str(getattr(event, "event_scope", "") or "").strip()
        if event_type:
            return "%s:%s" % (scope, event_type)
        return scope or "event"

    def _event_route_key(self, event):
        text = str(getattr(event, "event_text", "") or "").strip()
        if text and text.lower() not in ("none", "na", "<na>", "nan", "null"):
            return text
        source = str(getattr(event, "source_range", "") or "").strip()
        target = str(getattr(event, "target_range", "") or "").strip()
        if source or target:
            return "%s->%s" % (source or "?", target or "?")
        return ""

    def _safe_float_or_none(self, value):
        try:
            return float(str(value).strip())
        except Exception:
            return None

    def _format_number(self, value):
        try:
            number = float(value)
        except Exception:
            return str(value)
        if abs(number - round(number)) < 1e-9:
            return str(int(round(number)))
        return ("%.6f" % number).rstrip("0").rstrip(".")

    def _format_network_value(self, value, decimals=1):
        try:
            number = float(value)
        except Exception:
            return str(value)
        if int(decimals) <= 0:
            return str(int(round(number)))
        return ("%.*f" % (int(decimals), number)).rstrip("0").rstrip(".")

    def _export_events_csv(self):
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export BSM Events",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if "." not in path.replace("\\", "/").split("/")[-1]:
            path += ".csv"

        events = list(self.filtered_events or [])
        metadata = self._filter_metadata()
        headers = [
            "filter_scope",
            "filter_event_type",
            "filter_source_range",
            "filter_target_range",
            "filter_node",
            "filter_branch",
            "filter_time_min",
            "filter_time_max",
            "filter_search",
            "filter_time_bin_size",
            "filter_time_direction",
            "source_model_name",
            "source_run_directory",
            "event_scope",
            "sample_id",
            "event_type",
            "event_text",
            "time",
            "node",
            "branch",
            "source_range",
            "target_range",
            "dispersal_to",
            "extirpation_from",
        ]
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                for event in events:
                    if is_dataclass(event):
                        row = asdict(event)
                    else:
                        row = dict(getattr(event, "__dict__", {}) or {})
                    row.update({
                        "filter_scope": metadata.get("scope", ""),
                        "filter_event_type": metadata.get("event_type", ""),
                        "filter_source_range": metadata.get("source_range", ""),
                        "filter_target_range": metadata.get("target_range", ""),
                        "filter_node": metadata.get("node", ""),
                        "filter_branch": metadata.get("branch", ""),
                        "filter_time_min": metadata.get("time_min", ""),
                        "filter_time_max": metadata.get("time_max", ""),
                        "filter_search": metadata.get("search", ""),
                        "filter_time_bin_size": metadata.get("time_bin_size", ""),
                        "filter_time_direction": metadata.get("time_direction", ""),
                        "source_model_name": str(getattr(self.result, "source_model_name", "") or ""),
                        "source_run_directory": str(getattr(self.result, "source_run_directory", "") or ""),
                    })
                    writer.writerow({key: row.get(key, "") for key in headers})
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_time_csv(self):
        rows = self._build_time_series(self.filtered_events)
        if not rows:
            QMessageBox.information(self, "Export time CSV", "The filtered time table is empty.")
            return
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export BSM Time Summary",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if "." not in path.replace("\\", "/").split("/")[-1]:
            path += ".csv"

        metadata = self._filter_metadata()
        headers = [
            "filter_scope",
            "filter_event_type",
            "filter_source_range",
            "filter_target_range",
            "filter_node",
            "filter_branch",
            "filter_time_min",
            "filter_time_max",
            "filter_search",
            "filter_time_bin_size",
            "filter_time_direction",
        ]
        for row in rows:
            for key in row.keys():
                if key not in headers:
                    headers.append(key)
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                for row in rows:
                    out = {
                        "filter_scope": metadata.get("scope", ""),
                        "filter_event_type": metadata.get("event_type", ""),
                        "filter_source_range": metadata.get("source_range", ""),
                        "filter_target_range": metadata.get("target_range", ""),
                        "filter_node": metadata.get("node", ""),
                        "filter_branch": metadata.get("branch", ""),
                        "filter_time_min": metadata.get("time_min", ""),
                        "filter_time_max": metadata.get("time_max", ""),
                        "filter_search": metadata.get("search", ""),
                        "filter_time_bin_size": metadata.get("time_bin_size", ""),
                        "filter_time_direction": metadata.get("time_direction", ""),
                    }
                    out.update(dict(row))
                    writer.writerow({key: out.get(key, "") for key in headers})
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_raw_csv(self):
        name = self.raw_table_combo.currentData() if hasattr(self, "raw_table_combo") else ""
        raw_tables = dict(getattr(self.result, "raw_tables", {}) or {})
        rows = list(raw_tables.get(str(name), []) or [])
        if not rows:
            QMessageBox.information(self, "Export raw CSV", "The selected raw table is empty.")
            return
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export Raw BSM Table",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if "." not in path.replace("\\", "/").split("/")[-1]:
            path += ".csv"

        headers = ["raw_table"]
        for row in rows:
            for key in row.keys():
                if key not in headers:
                    headers.append(key)
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                for row in rows:
                    out = dict(row)
                    out["raw_table"] = str(name)
                    writer.writerow({key: out.get(key, "") for key in headers})
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_network_edges_csv(self):
        network = self.current_network
        if not network:
            QMessageBox.information(self, "Export edge CSV", "No BSM dispersal network is available.")
            return
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export BSM Dispersal Network Edges",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if "." not in path.replace("\\", "/").split("/")[-1]:
            path += ".csv"
        try:
            self.network_service.write_edges_csv(network, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_network_nodes_csv(self):
        network = self.current_network
        if not network:
            QMessageBox.information(self, "Export node CSV", "No BSM dispersal network is available.")
            return
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export BSM Dispersal Network Nodes",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if "." not in path.replace("\\", "/").split("/")[-1]:
            path += ".csv"
        try:
            self.network_service.write_nodes_csv(network, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_network_geojson(self):
        network = self.current_network
        if not network:
            QMessageBox.information(self, "Export GeoJSON", "No BSM dispersal network is available.")
            return
        if not list(network.get("edge_geojson", {}).get("features", []) or []):
            QMessageBox.information(
                self,
                "Export GeoJSON",
                "No visible network edge has map coordinates. Load area GeoJSON before exporting map features.",
            )
            return
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export BSM Dispersal Network GeoJSON",
            "",
            "GeoJSON files (*.geojson);;JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        if "." not in path.replace("\\", "/").split("/")[-1]:
            path += ".geojson"
        try:
            self.network_service.write_geojson(network, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _fill_table(self, table, headers, rows):
        headers = [str(header) for header in list(headers or [])]
        rows = list(rows or [])
        table.setSortingEnabled(False)
        table.clear()
        table.setColumnCount(len(headers))
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels(headers)
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(list(row or [])):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row_idx, col_idx, item)
        table.resizeColumnsToContents()
        table.setSortingEnabled(True)

from collections import defaultdict

from PyQt5.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class _SpatialGraphicsView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)

    def fit_to_scene(self):
        scene = self.scene()
        if scene is None:
            return
        rect = scene.itemsBoundingRect()
        if rect.isNull():
            rect = scene.sceneRect()
        if not rect.isNull():
            self.fitInView(rect.adjusted(-20, -20, 20, 20), Qt.KeepAspectRatio)


class SpatialMapView(QWidget):
    occurrence_selected = pyqtSignal(int)
    area_selected = pyqtSignal(str)

    """Lightweight PyQt map preview for occurrence/polygon QA.

    This intentionally avoids WebEngine/GIS dependencies. Coordinates are
    projected as lon/lat onto a flat preview canvas, which is sufficient for
    checking area coding, outliers, and matched/unmatched point status.
    """

    DEFAULT_POINT_LIMIT = 5000
    MAX_POINT_LIMIT = 1000000
    MAX_RING_POINTS = 2000

    STATUS_COLORS = {
        "matched": QColor(42, 157, 143),
        "unmatched": QColor(214, 64, 69),
        "multi_area": QColor(232, 142, 42),
        "raw": QColor(53, 104, 184),
    }

    STATUS_LABELS = {
        "matched": "inside_one_polygon",
        "unmatched": "outside_all_polygons",
        "multi_area": "inside_multiple_polygons",
        "raw": "unencoded_occurrence",
    }

    AREA_FALLBACK_COLORS = [
        "#4C78A8",
        "#F58518",
        "#54A24B",
        "#E45756",
        "#72B7B2",
        "#B279A2",
        "#FF9DA6",
        "#9D755D",
        "#BAB0AC",
        "#59A14F",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._drawn_area_count = 0
        self._drawn_point_count = 0
        self._last_summary_lines = []
        self._point_items_by_row_index = {}
        self._area_items_by_code = {}
        self._suppress_selection_signal = False
        self._selection_highlight_items = []

        self.scene = QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.view = _SpatialGraphicsView(self)
        self.view.setScene(self.scene)

        self.show_areas_check = QCheckBox("Areas", self)
        self.show_areas_check.setChecked(True)
        self.show_areas_check.toggled.connect(self.refresh)
        self.show_points_check = QCheckBox("Occurrence points", self)
        self.show_points_check.setChecked(True)
        self.show_points_check.toggled.connect(self.refresh)
        self.show_labels_check = QCheckBox("Area labels", self)
        self.show_labels_check.setChecked(False)
        self.show_labels_check.toggled.connect(self.refresh)
        self.status_filter_checkboxes = {}
        for status in ["matched", "unmatched", "multi_area", "raw"]:
            checkbox = QCheckBox(self.STATUS_LABELS[status], self)
            checkbox.setChecked(True)
            checkbox.toggled.connect(self.refresh)
            self.status_filter_checkboxes[status] = checkbox

        self.point_limit_spin = QSpinBox(self)
        self.point_limit_spin.setRange(100, self.MAX_POINT_LIMIT)
        self.point_limit_spin.setSingleStep(1000)
        self.point_limit_spin.setValue(self.DEFAULT_POINT_LIMIT)
        self.point_limit_spin.valueChanged.connect(self.refresh)

        self.refresh_button = QPushButton("Refresh Map", self)
        self.refresh_button.clicked.connect(self.refresh)
        self.draw_all_button = QPushButton("Draw All Points", self)
        self.draw_all_button.clicked.connect(self._draw_all_points)
        self.fit_button = QPushButton("Fit", self)
        self.fit_button.clicked.connect(self.view.fit_to_scene)

        self.summary_label = QLabel("Load occurrences and area polygons to preview spatial data.", self)
        self.summary_label.setWordWrap(True)
        self.legend_label = QLabel(self._legend_html(), self)
        self.legend_label.setTextFormat(Qt.RichText)

        self.info_text = QTextEdit(self)
        self.info_text.setReadOnly(True)
        self.info_text.setMinimumWidth(260)
        self.info_text.setLineWrapMode(QTextEdit.NoWrap)

        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        controls = QGroupBox("Map preview", self)
        controls_layout = QHBoxLayout(controls)
        controls_layout.addWidget(self.show_areas_check)
        controls_layout.addWidget(self.show_points_check)
        controls_layout.addWidget(self.show_labels_check)
        controls_layout.addSpacing(12)
        controls_layout.addWidget(QLabel("Point preview limit", controls))
        controls_layout.addWidget(self.point_limit_spin)
        controls_layout.addSpacing(12)
        controls_layout.addWidget(self.refresh_button)
        controls_layout.addWidget(self.draw_all_button)
        controls_layout.addWidget(self.fit_button)
        controls_layout.addStretch(1)
        status_filters = QGroupBox("Point status filter", self)
        status_filter_layout = QHBoxLayout(status_filters)
        for status in ["matched", "unmatched", "multi_area", "raw"]:
            status_filter_layout.addWidget(self.status_filter_checkboxes[status])
        status_filter_layout.addStretch(1)
        left.addWidget(controls)
        left.addWidget(status_filters)
        left.addWidget(self.view, 1)
        left.addWidget(self.summary_label)

        right = QGroupBox("Selection and legend", self)
        right_layout = QVBoxLayout(right)
        form = QFormLayout()
        form.addRow("Legend", self.legend_label)
        right_layout.addLayout(form)
        right_layout.addWidget(self.info_text, 1)

        root.addLayout(left, 1)
        root.addWidget(right)

    def set_project(self, project):
        self._project = project
        self.refresh()

    def refresh(self):
        self.scene.clear()
        self._drawn_area_count = 0
        self._drawn_point_count = 0
        self._point_items_by_row_index = {}
        self._area_items_by_code = {}
        self._selection_highlight_items = []
        project = self._project
        if project is None:
            self._set_empty_summary()
            return

        areas = list(getattr(project, "areas", []) or [])
        point_rows = self._point_rows(project)
        visible_point_rows = self._visible_point_rows(point_rows)
        bounds = self._data_bounds(areas, visible_point_rows)
        if bounds is None:
            self._set_empty_summary()
            return
        transform = self._build_transform(bounds)

        if self.show_areas_check.isChecked():
            self._draw_areas(areas, transform)
        if self.show_points_check.isChecked():
            self._draw_points(visible_point_rows, transform)

        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-30, -30, 30, 30))
        self._update_summary(project, point_rows, visible_point_rows)
        QTimer.singleShot(0, self.view.fit_to_scene)

    def drawn_area_count(self):
        return self._drawn_area_count

    def drawn_point_count(self):
        return self._drawn_point_count

    def set_point_preview_limit(self, limit):
        limit = int(limit or 0)
        limit = max(100, min(self.MAX_POINT_LIMIT, limit))
        self.point_limit_spin.setValue(limit)

    def _draw_all_points(self):
        project = self._project
        if project is None:
            return
        point_rows = self._visible_point_rows(self._point_rows(project))
        target = max(100, min(self.MAX_POINT_LIMIT, len(point_rows)))
        self.point_limit_spin.setValue(target)

    def select_point_by_row_index(self, row_index):
        row_index = int(row_index or 0)
        if row_index <= 0:
            return False
        item = self._point_items_by_row_index.get(row_index)
        if item is None:
            self._make_point_visible(row_index)
            item = self._point_items_by_row_index.get(row_index)
        if item is None:
            return False
        self._suppress_selection_signal = True
        try:
            self.scene.clearSelection()
            self.view.centerOn(item)
        finally:
            self._suppress_selection_signal = False
        self._show_selection_metadata(item.data(0), item=item, emit_signal=False)
        return True

    def select_area_by_code(self, area_code):
        code = str(area_code or "").strip()
        if not code:
            return False
        item = self._area_items_by_code.get(code)
        if item is None:
            if not self.show_areas_check.isChecked():
                self.show_areas_check.setChecked(True)
            item = self._area_items_by_code.get(code)
        if item is None:
            return False
        self._suppress_selection_signal = True
        try:
            self.scene.clearSelection()
            metadata = item.data(0)
            if isinstance(metadata, dict) and metadata.get("centroid_x") is not None and metadata.get("centroid_y") is not None:
                self.view.centerOn(QPointF(float(metadata.get("centroid_x")), float(metadata.get("centroid_y"))))
            else:
                self.view.centerOn(item)
        finally:
            self._suppress_selection_signal = False
        self._show_selection_metadata(item.data(0), item=item, emit_signal=False)
        return True

    def _set_empty_summary(self):
        self.scene.setSceneRect(0, 0, 900, 520)
        self.summary_label.setText("Load occurrences and area polygons to preview spatial data.")
        self._last_summary_lines = [
            "Map preview",
            "",
            "No drawable spatial data are loaded.",
        ]
        self.info_text.setPlainText("\n".join(self._last_summary_lines))

    def _update_summary(self, project, point_rows, visible_point_rows):
        status_counts = defaultdict(int)
        for point in point_rows:
            status_counts[point.get("status", "raw")] += 1
        visible_status_counts = defaultdict(int)
        for point in visible_point_rows:
            visible_status_counts[point.get("status", "raw")] += 1
        limit = int(self.point_limit_spin.value())
        point_source = "encoding audit" if list(getattr(project, "encoded_audit_rows", []) or []) else "occurrences"
        lines = [
            "Map preview",
            "",
            "Area polygons loaded: %d" % len(getattr(project, "areas", []) or []),
            "Area polygons drawn: %d" % self._drawn_area_count,
            "Point source: %s" % point_source,
            "Points available: %d" % len(point_rows),
            "Points after filter: %d" % len(visible_point_rows),
            "Points drawn: %d" % self._drawn_point_count,
            "Point preview limit: %d" % limit,
        ]
        if status_counts:
            lines.append("")
            lines.append("Coordinate status:")
            for status in sorted(status_counts):
                shown = visible_status_counts.get(status, 0)
                lines.append("  %s=%d shown=%d" % (self._status_label(status), status_counts[status], shown))
        if len(visible_point_rows) > self._drawn_point_count:
            lines.append("")
            lines.append("Only the first %d points are drawn. Encoding, QA, and exports still use full data." % self._drawn_point_count)
        self._last_summary_lines = lines
        self.summary_label.setText(
            "Drawn %d area polygons and %d/%d filtered points."
            % (self._drawn_area_count, self._drawn_point_count, len(visible_point_rows))
        )
        self.info_text.setPlainText("\n".join(lines))

    def _draw_areas(self, areas, transform):
        for index, area in enumerate(areas):
            geometry = getattr(area, "geometry", {}) or {}
            path = self._path_from_geometry(geometry, transform)
            if path.isEmpty():
                continue
            color = self._area_color(area, index)
            item = QGraphicsPathItem(path)
            item.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 42)))
            item.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 180), 0.8))
            item.setFlag(QGraphicsItem.ItemIsSelectable, True)
            item.setZValue(0)
            item.setToolTip("Area: %s" % getattr(area, "area_code", ""))
            centroid_x = None
            centroid_y = None
            if getattr(area, "centroid_lon", None) is not None and getattr(area, "centroid_lat", None) is not None:
                centroid_x, centroid_y = transform(float(area.centroid_lon), float(area.centroid_lat))
            item.setData(0, {
                "kind": "area",
                "area_code": getattr(area, "area_code", ""),
                "display_name": getattr(area, "display_name", ""),
                "group": getattr(area, "group", ""),
                "geometry_id": getattr(area, "geometry_id", ""),
                "source": getattr(area, "source", ""),
                "centroid_lon": getattr(area, "centroid_lon", None),
                "centroid_lat": getattr(area, "centroid_lat", None),
                "centroid_x": centroid_x,
                "centroid_y": centroid_y,
            })
            self.scene.addItem(item)
            self._area_items_by_code[str(getattr(area, "area_code", "") or "")] = item
            self._drawn_area_count += 1
            if self.show_labels_check.isChecked():
                self._draw_area_label(area, transform)

    def _draw_area_label(self, area, transform):
        lon = getattr(area, "centroid_lon", None)
        lat = getattr(area, "centroid_lat", None)
        if lon is None or lat is None:
            return
        x, y = transform(float(lon), float(lat))
        label = QGraphicsSimpleTextItem(str(getattr(area, "area_code", "") or ""))
        label.setBrush(QBrush(QColor(36, 47, 58)))
        label.setPos(x + 3.0, y + 3.0)
        label.setZValue(3)
        self.scene.addItem(label)

    def _draw_points(self, point_rows, transform):
        limit = int(self.point_limit_spin.value())
        display_rows = point_rows[:limit]
        radius = 2.2 if len(display_rows) > 10000 else 3.4
        for point in display_rows:
            x, y = transform(float(point["longitude"]), float(point["latitude"]))
            status = str(point.get("status", "raw") or "raw")
            color = self.STATUS_COLORS.get(status, self.STATUS_COLORS["raw"])
            item = QGraphicsEllipseItem(x - radius, y - radius, radius * 2.0, radius * 2.0)
            item.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 210)))
            item.setPen(QPen(QColor(255, 255, 255, 220), 0.7))
            item.setFlag(QGraphicsItem.ItemIsSelectable, True)
            item.setZValue(10)
            item.setToolTip("%s: %s" % (self._status_label(status), point.get("taxon", "")))
            item.setData(0, dict(point, kind="point"))
            self.scene.addItem(item)
            self._point_items_by_row_index[int(point.get("row_index", 0) or 0)] = item
            self._drawn_point_count += 1

    def _on_selection_changed(self):
        if self._suppress_selection_signal:
            return
        selected = self.scene.selectedItems()
        if not selected:
            if self._selection_highlight_items:
                return
            self.info_text.setPlainText("\n".join(self._last_summary_lines))
            return
        item = selected[-1]
        metadata = item.data(0)
        self._suppress_selection_signal = True
        try:
            self.scene.clearSelection()
        finally:
            self._suppress_selection_signal = False
        self._show_selection_metadata(metadata, item=item, emit_signal=True)

    def _show_selection_metadata(self, metadata, item=None, emit_signal=True):
        if not isinstance(metadata, dict):
            self.info_text.setPlainText("\n".join(self._last_summary_lines))
            return
        if metadata.get("kind") == "area":
            lines = [
                "Selected area",
                "",
                "Area code: %s" % metadata.get("area_code", ""),
                "Display name: %s" % metadata.get("display_name", ""),
                "Group: %s" % metadata.get("group", ""),
                "Geometry ID: %s" % metadata.get("geometry_id", ""),
                "Centroid lon: %s" % self._format_number(metadata.get("centroid_lon")),
                "Centroid lat: %s" % self._format_number(metadata.get("centroid_lat")),
                "Source: %s" % metadata.get("source", ""),
            ]
            if emit_signal:
                self.area_selected.emit(str(metadata.get("area_code", "") or ""))
        else:
            lines = [
                "Selected occurrence point",
                "",
                "Row: %s" % metadata.get("row_index", ""),
                "Taxon: %s" % metadata.get("taxon", ""),
                "Longitude: %s" % self._format_number(metadata.get("longitude")),
                "Latitude: %s" % self._format_number(metadata.get("latitude")),
                "Coordinate status: %s" % self._status_label(metadata.get("status", "")),
                "Matched areas: %s" % (", ".join(metadata.get("matched_areas", []) or []) or "unmatched"),
            ]
            if emit_signal:
                self.occurrence_selected.emit(int(metadata.get("row_index", 0) or 0))
        self._highlight_item(item, metadata)
        self.info_text.setPlainText("\n".join(lines))

    def _highlight_item(self, item, metadata):
        self._clear_selection_highlights()
        if item is None or not isinstance(metadata, dict):
            return
        if metadata.get("kind") == "area" and hasattr(item, "path"):
            highlight = QGraphicsPathItem(item.path())
            highlight.setBrush(QBrush(Qt.NoBrush))
            highlight.setPen(QPen(QColor(220, 40, 45), 2.4))
            highlight.setZValue(30)
            self.scene.addItem(highlight)
            self._selection_highlight_items.append(highlight)
            return
        if metadata.get("kind") == "point" and hasattr(item, "rect"):
            rect = item.rect()
            center = rect.center()
            radius = max(rect.width(), rect.height()) * 1.9
            halo = QGraphicsEllipseItem(
                center.x() - radius,
                center.y() - radius,
                radius * 2.0,
                radius * 2.0,
            )
            halo.setBrush(QBrush(Qt.NoBrush))
            halo.setPen(QPen(QColor(220, 40, 45), 2.2))
            halo.setZValue(35)
            self.scene.addItem(halo)
            self._selection_highlight_items.append(halo)

    def _clear_selection_highlights(self):
        for item in list(self._selection_highlight_items or []):
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self._selection_highlight_items = []

    def _active_statuses(self):
        return set(
            status
            for status, checkbox in self.status_filter_checkboxes.items()
            if checkbox.isChecked()
        )

    def _visible_point_rows(self, point_rows):
        active = self._active_statuses()
        if not active:
            return []
        return [
            point
            for point in list(point_rows or [])
            if str(point.get("status", "raw") or "raw") in active
        ]

    def _make_point_visible(self, row_index):
        project = self._project
        if project is None:
            return
        point_rows = self._point_rows(project)
        target = None
        for point in point_rows:
            if int(point.get("row_index", 0) or 0) == row_index:
                target = point
                break
        if target is None:
            return
        status = str(target.get("status", "raw") or "raw")
        checkbox = self.status_filter_checkboxes.get(status)
        if checkbox is not None and not checkbox.isChecked():
            checkbox.setChecked(True)
        visible_rows = self._visible_point_rows(point_rows)
        visible_index = None
        for index, point in enumerate(visible_rows):
            if int(point.get("row_index", 0) or 0) == row_index:
                visible_index = index
                break
        if visible_index is not None and visible_index >= int(self.point_limit_spin.value()):
            new_limit = min(self.MAX_POINT_LIMIT, max(100, visible_index + 1))
            if new_limit != int(self.point_limit_spin.value()):
                self.point_limit_spin.setValue(new_limit)
                return
        self.refresh()

    def _point_rows(self, project):
        audit_rows = list(getattr(project, "encoded_audit_rows", []) or [])
        if audit_rows:
            return [
                {
                    "row_index": int(getattr(row, "row_index", 0) or 0),
                    "taxon": str(getattr(row, "taxon", "") or ""),
                    "longitude": float(getattr(row, "longitude", 0.0) or 0.0),
                    "latitude": float(getattr(row, "latitude", 0.0) or 0.0),
                    "matched_areas": list(getattr(row, "matched_areas", []) or []),
                    "status": str(getattr(row, "status", "") or "raw"),
                }
                for row in audit_rows
            ]
        return [
            {
                "row_index": int(getattr(row, "row_index", 0) or 0),
                "taxon": str(getattr(row, "taxon", "") or ""),
                "longitude": float(getattr(row, "longitude", 0.0) or 0.0),
                "latitude": float(getattr(row, "latitude", 0.0) or 0.0),
                "matched_areas": [],
                "status": "raw",
            }
            for row in list(getattr(project, "occurrences", []) or [])
        ]

    def _data_bounds(self, areas, point_rows):
        bounds = None
        for area in areas:
            for lon, lat in self._geometry_points(getattr(area, "geometry", {}) or {}):
                bounds = self._merge_bounds(bounds, lon, lat)
        for point in point_rows:
            bounds = self._merge_bounds(bounds, point["longitude"], point["latitude"])
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

    def _build_transform(self, bounds):
        min_lon, min_lat, max_lon, max_lat = bounds
        width = max(1e-9, float(max_lon) - float(min_lon))
        height = max(1e-9, float(max_lat) - float(min_lat))
        scale = min(1100.0 / width, 680.0 / height)
        margin = 24.0

        def transform(lon, lat):
            return (
                margin + (float(lon) - float(min_lon)) * scale,
                margin + (float(max_lat) - float(lat)) * scale,
            )

        return transform

    def _path_from_geometry(self, geometry, transform):
        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)
        geometry_type = str(geometry.get("type", "") or "")
        coordinates = geometry.get("coordinates") or []
        if geometry_type == "Polygon":
            polygons = [coordinates]
        elif geometry_type == "MultiPolygon":
            polygons = list(coordinates or [])
        else:
            polygons = []
        for polygon in polygons:
            self._add_polygon_to_path(path, polygon, transform)
        return path

    def _add_polygon_to_path(self, path, polygon, transform):
        for ring in list(polygon or []):
            points = self._display_ring_points(ring)
            if len(points) < 3:
                continue
            qpoints = []
            for point in points:
                if len(point) < 2:
                    continue
                x, y = transform(float(point[0]), float(point[1]))
                qpoints.append(QPointF(x, y))
            if len(qpoints) < 3:
                continue
            path.addPolygon(QPolygonF(qpoints))
            path.closeSubpath()

    def _display_ring_points(self, ring):
        points = list(ring or [])
        if len(points) <= self.MAX_RING_POINTS:
            return points
        stride = max(1, int(round(float(len(points)) / float(self.MAX_RING_POINTS))))
        sampled = points[::stride]
        if points[-1] != sampled[-1]:
            sampled.append(points[-1])
        return sampled

    def _geometry_points(self, geometry):
        geometry_type = str(geometry.get("type", "") or "")
        coordinates = geometry.get("coordinates") or []
        if geometry_type == "Polygon":
            polygons = [coordinates]
        elif geometry_type == "MultiPolygon":
            polygons = list(coordinates or [])
        else:
            polygons = []
        for polygon in polygons:
            for ring in list(polygon or []):
                for point in list(ring or []):
                    if len(point) >= 2:
                        yield float(point[0]), float(point[1])

    def _merge_bounds(self, bounds, lon, lat):
        lon = float(lon)
        lat = float(lat)
        if bounds is None:
            return lon, lat, lon, lat
        return (
            min(bounds[0], lon),
            min(bounds[1], lat),
            max(bounds[2], lon),
            max(bounds[3], lat),
        )

    def _area_color(self, area, index):
        raw = str(getattr(area, "color", "") or "").strip()
        if raw:
            color = QColor(raw)
            if color.isValid():
                return color
        return QColor(self.AREA_FALLBACK_COLORS[index % len(self.AREA_FALLBACK_COLORS)])

    def _status_label(self, status):
        return self.STATUS_LABELS.get(str(status or ""), str(status or "unknown"))

    def _format_number(self, value):
        if value is None or value == "":
            return ""
        try:
            return "%.6f" % float(value)
        except Exception:
            return str(value)

    def _legend_html(self):
        parts = []
        for status in ["matched", "unmatched", "multi_area", "raw"]:
            color = self.STATUS_COLORS[status]
            parts.append(
                '<span style="color: rgb(%d,%d,%d);">&#9679;</span> %s'
                % (color.red(), color.green(), color.blue(), self.STATUS_LABELS[status])
            )
        return "<br/>".join(parts)

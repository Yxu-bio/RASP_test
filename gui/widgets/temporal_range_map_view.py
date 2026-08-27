import math

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _TemporalMapGraphicsView(QGraphicsView):
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

    def fit_to_map(self):
        scene = self.scene()
        if scene is None:
            return
        rect = scene.itemsBoundingRect()
        if not rect.isNull():
            self.fitInView(rect.adjusted(-16, -16, 16, 16), Qt.KeepAspectRatio)


class _PieSliceItem(QGraphicsPathItem):
    def __init__(self, owner, area_code, group_id, path):
        super().__init__(path)
        self.owner = owner
        self.area_code = str(area_code or "")
        self.group_id = str(group_id or "")
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor(255, 255, 255, 235), 2.0))
        self.setZValue(24)
        self.owner.group_hovered.emit(self.group_id)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(QPen(QColor(255, 255, 255, 205), 0.8))
        self.setZValue(20)
        self.owner.group_hover_cleared.emit()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        self.owner.area_selected.emit(self.area_code)
        super().mousePressEvent(event)


class TemporalRangeMapView(QWidget):
    group_hovered = pyqtSignal(str)
    group_hover_cleared = pyqtSignal()
    area_selected = pyqtSignal(str)

    MAX_RING_POINTS = 2500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._areas = []
        self._area_items = {}
        self._area_labels = {}
        self._area_centers = {}
        self._glyph_items = []
        self._glyph_text_items = []
        self._highlighted_group_id = ""
        self.scene = QGraphicsScene(self)
        self.view = _TemporalMapGraphicsView(self)
        self.view.setScene(self.scene)
        self.summary_label = QLabel("No spatial area polygons are loaded.", self)
        self.summary_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.summary_label)

    def set_areas(self, areas):
        self._areas = list(areas or [])
        self._build_scene()

    def set_lineage_glyphs(
        self,
        glyphs,
        group_colors=None,
        group_labels=None,
        focused_active_count=0,
        scope_label="",
    ):
        self._clear_glyphs()
        for area_code, label in self._area_labels.items():
            center = self._area_centers.get(area_code)
            if center is not None:
                label.setPos(center.x() + 5.0, center.y() + 5.0)
        glyphs = dict(glyphs or {})
        group_colors = dict(group_colors or {})
        group_labels = dict(group_labels or {})
        focused_active_count = int(focused_active_count or 0)
        maximum = max(
            [0.0] + [float(dict(values or {}).get("expected_count", 0.0) or 0.0) for values in glyphs.values()]
        )
        shown = 0
        for area_code, values in glyphs.items():
            center = self._area_centers.get(str(area_code))
            if center is None:
                continue
            expected = float(dict(values or {}).get("expected_count", 0.0) or 0.0)
            if expected <= 0.0:
                continue
            shown += 1
            radius = max(7.0, 31.0 * math.sqrt(expected / maximum)) if maximum > 0.0 else 7.0
            group_values = dict(dict(values or {}).get("group_values", {}) or {})
            total = sum(max(0.0, float(value or 0.0)) for value in group_values.values())
            if total <= 0.0:
                continue
            start_angle = 90.0
            tooltip_rows = []
            for group_id, value in sorted(
                group_values.items(),
                key=lambda item: (-float(item[1] or 0.0), str(item[0])),
            ):
                value = max(0.0, float(value or 0.0))
                if value <= 0.0:
                    continue
                span = -360.0 * value / total
                path = QPainterPath()
                path.moveTo(center)
                path.arcTo(
                    QRectF(center.x() - radius, center.y() - radius, radius * 2.0, radius * 2.0),
                    start_angle,
                    span,
                )
                path.closeSubpath()
                item = _PieSliceItem(self, area_code, group_id, path)
                color = QColor(group_colors.get(group_id, "#76848d"))
                if not color.isValid():
                    color = QColor("#76848d")
                color.setAlpha(225)
                item.setBrush(QBrush(color))
                item.setPen(QPen(QColor(255, 255, 255, 205), 0.8))
                item.setZValue(20)
                self.scene.addItem(item)
                self._glyph_items.append(item)
                tooltip_rows.append(
                    "%s: %.3f" % (group_labels.get(group_id, group_id), value)
                )
                start_angle += span

            outline = QGraphicsEllipseItem(
                center.x() - radius,
                center.y() - radius,
                radius * 2.0,
                radius * 2.0,
            )
            outline.setBrush(QBrush(Qt.NoBrush))
            outline.setPen(QPen(QColor(48, 58, 65, 190), 1.15))
            outline.setZValue(21)
            outline.setAcceptedMouseButtons(Qt.NoButton)
            self.scene.addItem(outline)
            self._glyph_text_items.append(outline)

            value_label = QGraphicsSimpleTextItem(self._format_count(expected))
            value_label.setFont(QFont("Segoe UI", 8, QFont.DemiBold))
            value_label.setBrush(QBrush(QColor(25, 31, 36)))
            value_label.setPos(
                center.x() - value_label.boundingRect().width() / 2.0,
                center.y() - value_label.boundingRect().height() / 2.0,
            )
            value_label.setZValue(25)
            value_label.setAcceptedMouseButtons(Qt.NoButton)
            self.scene.addItem(value_label)
            self._glyph_text_items.append(value_label)

            area_label = self._area_labels.get(str(area_code))
            if area_label is not None:
                area_label.setPos(center.x() + radius + 4.0, center.y() - radius)
            occupancy = expected / float(focused_active_count) if focused_active_count else 0.0
            tooltip = (
                "%s\nExpected active-lineage occupancy: %.3f\n"
                "Occupied-lineage fraction: %.1f%%\n%s"
            ) % (
                area_code,
                expected,
                occupancy * 100.0,
                "\n".join(tooltip_rows),
            )
            for item in self._glyph_items[-len(tooltip_rows):]:
                item.setToolTip(tooltip)

        self.highlight_group(self._highlighted_group_id)
        if not self._areas:
            self.summary_label.setText("No spatial areas are loaded. Tree dynamics remain available.")
        elif focused_active_count <= 0:
            self.summary_label.setText(
                "%s. No focused lineage crosses this time slice." % (scope_label or "Current focus")
            )
        else:
            self.summary_label.setText(
                "%s. %d active focused lineages; %d occupied areas. "
                "Bubble area represents expected active-lineage occupancy; slices show clade contributions."
                % (scope_label or "Current focus", focused_active_count, shown)
            )

    def set_probabilities(self, probabilities, scope_label=""):
        glyphs = {}
        for area, probability in dict(probabilities or {}).items():
            value = max(0.0, float(probability or 0.0))
            if value > 0.0:
                glyphs[area] = {
                    "expected_count": value,
                    "group_values": {"aggregate": value},
                    "contributors": [],
                }
        self.set_lineage_glyphs(
            glyphs,
            group_colors={"aggregate": "#2f6f8f"},
            group_labels={"aggregate": "Aggregate"},
            focused_active_count=1,
            scope_label=scope_label,
        )

    def highlight_group(self, group_id):
        self._highlighted_group_id = str(group_id or "")
        for item in self._glyph_items:
            if not self._highlighted_group_id or item.group_id == self._highlighted_group_id:
                item.setOpacity(1.0)
            else:
                item.setOpacity(0.16)

    def fit_to_map(self):
        self.view.fit_to_map()

    def _clear_glyphs(self):
        for item in self._glyph_items + self._glyph_text_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self._glyph_items = []
        self._glyph_text_items = []

    def _build_scene(self):
        self.scene.clear()
        self._area_items = {}
        self._area_labels = {}
        self._area_centers = {}
        self._glyph_items = []
        self._glyph_text_items = []
        if not self._areas:
            self.scene.setSceneRect(0, 0, 900, 520)
            self.summary_label.setText("No spatial area polygons are loaded. Tree dynamics remain available.")
            return
        bounds = self._data_bounds(self._areas)
        transform = self._build_transform(bounds)
        for area in self._areas:
            code = str(getattr(area, "area_code", "") or "").strip()
            path = self._path_from_geometry(getattr(area, "geometry", {}) or {}, transform)
            if not code:
                continue
            lon = getattr(area, "centroid_lon", None)
            lat = getattr(area, "centroid_lat", None)
            if path.isEmpty():
                if lon is None or lat is None:
                    continue
                x, y = transform(float(lon), float(lat))
                item = QGraphicsEllipseItem(x - 4.0, y - 4.0, 8.0, 8.0)
            else:
                item = QGraphicsPathItem(path)
            item.setBrush(QBrush(QColor(244, 246, 244)))
            item.setPen(QPen(QColor(128, 139, 145, 155), 0.75))
            item.setZValue(1)
            self.scene.addItem(item)
            self._area_items[code] = item
            if lon is not None and lat is not None:
                x, y = transform(float(lon), float(lat))
                center = QPointF(x, y)
                self._area_centers[code] = center
                label = QGraphicsSimpleTextItem(code)
                label.setFont(QFont("Segoe UI", 8))
                label.setBrush(QBrush(QColor(48, 57, 63)))
                label.setPos(x + 5.0, y + 5.0)
                label.setZValue(26)
                label.setAcceptedMouseButtons(Qt.NoButton)
                self.scene.addItem(label)
                self._area_labels[code] = label
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))
        self.summary_label.setText("Loaded %d spatial areas." % len(self._area_items))
        self.fit_to_map()

    def _format_count(self, value):
        value = float(value or 0.0)
        if value >= 100.0:
            return "%.0f" % value
        if value >= 10.0:
            return "%.1f" % value
        return "%.2f" % value

    def _data_bounds(self, areas):
        bounds = None
        for area in areas:
            for lon, lat in self._geometry_points(getattr(area, "geometry", {}) or {}):
                bounds = self._merge_bounds(bounds, lon, lat)
            if getattr(area, "centroid_lon", None) is not None and getattr(area, "centroid_lat", None) is not None:
                bounds = self._merge_bounds(bounds, float(area.centroid_lon), float(area.centroid_lat))
        if bounds is None:
            return -180.0, -90.0, 180.0, 90.0
        min_lon, min_lat, max_lon, max_lat = bounds
        if abs(max_lon - min_lon) < 1e-9:
            min_lon, max_lon = min_lon - 0.5, max_lon + 0.5
        if abs(max_lat - min_lat) < 1e-9:
            min_lat, max_lat = min_lat - 0.5, max_lat + 0.5
        return min_lon, min_lat, max_lon, max_lat

    def _build_transform(self, bounds):
        min_lon, min_lat, max_lon, max_lat = bounds
        width = max(1e-9, max_lon - min_lon)
        height = max(1e-9, max_lat - min_lat)
        scale = min(1000.0 / width, 620.0 / height)

        def transform(lon, lat):
            return 24.0 + (lon - min_lon) * scale, 24.0 + (max_lat - lat) * scale

        return transform

    def _path_from_geometry(self, geometry, transform):
        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)
        geometry_type = str(geometry.get("type", "") or "")
        coordinates = geometry.get("coordinates") or []
        polygons = [coordinates] if geometry_type == "Polygon" else list(coordinates or []) if geometry_type == "MultiPolygon" else []
        for polygon in polygons:
            for ring in list(polygon or []):
                points = self._display_ring_points(ring)
                qpoints = []
                for point in points:
                    if len(point) >= 2:
                        qpoints.append(QPointF(*transform(float(point[0]), float(point[1]))))
                if len(qpoints) >= 3:
                    path.addPolygon(QPolygonF(qpoints))
                    path.closeSubpath()
        return path

    def _display_ring_points(self, ring):
        points = list(ring or [])
        if len(points) <= self.MAX_RING_POINTS:
            return points
        stride = max(1, int(round(float(len(points)) / float(self.MAX_RING_POINTS))))
        sampled = points[::stride]
        if points and sampled and points[-1] != sampled[-1]:
            sampled.append(points[-1])
        return sampled

    def _geometry_points(self, geometry):
        geometry_type = str(geometry.get("type", "") or "")
        coordinates = geometry.get("coordinates") or []
        polygons = [coordinates] if geometry_type == "Polygon" else list(coordinates or []) if geometry_type == "MultiPolygon" else []
        for polygon in polygons:
            for ring in list(polygon or []):
                for point in list(ring or []):
                    if len(point) >= 2:
                        yield float(point[0]), float(point[1])

    def _merge_bounds(self, bounds, lon, lat):
        if bounds is None:
            return lon, lat, lon, lat
        return min(bounds[0], lon), min(bounds[1], lat), max(bounds[2], lon), max(bounds[3], lat)

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QBrush, QPainter, QPainterPath, QPen, QPolygonF
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


class TemporalRangeMapView(QWidget):
    MAX_RING_POINTS = 2500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._areas = []
        self._area_items = {}
        self._area_labels = {}
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

    def set_probabilities(self, probabilities, scope_label=""):
        probabilities = dict(probabilities or {})
        for code, item in self._area_items.items():
            value = max(0.0, min(1.0, float(probabilities.get(code, 0.0) or 0.0)))
            fill = self._heat_color(value)
            item.setBrush(QBrush(fill))
            item.setPen(QPen(QColor(66, 75, 84, 190 if value > 0.0 else 100), 0.75))
            item.setToolTip("%s: %.2f%%" % (code, value * 100.0))
            label = self._area_labels.get(code)
            if label is not None:
                label.setText("%s\n%.1f%%" % (code, value * 100.0))
        shown = sum(1 for value in probabilities.values() if float(value or 0.0) > 0.0)
        self.summary_label.setText(
            "%s%s%d area marginal probabilities above zero. Color scale: 0%% (light) to 100%% (dark)."
            % ((scope_label + ". ") if scope_label else "", "", shown)
        )

    def fit_to_map(self):
        self.view.fit_to_map()

    def _build_scene(self):
        self.scene.clear()
        self._area_items = {}
        self._area_labels = {}
        if not self._areas:
            self.scene.setSceneRect(0, 0, 900, 520)
            self.summary_label.setText("No spatial area polygons are loaded. Tree playback remains available.")
            return
        bounds = self._data_bounds(self._areas)
        transform = self._build_transform(bounds)
        for area in self._areas:
            code = str(getattr(area, "area_code", "") or "").strip()
            path = self._path_from_geometry(getattr(area, "geometry", {}) or {}, transform)
            if not code:
                continue
            if path.isEmpty():
                lon = getattr(area, "centroid_lon", None)
                lat = getattr(area, "centroid_lat", None)
                if lon is None or lat is None:
                    continue
                x, y = transform(float(lon), float(lat))
                item = QGraphicsEllipseItem(x - 9.0, y - 9.0, 18.0, 18.0)
            else:
                item = QGraphicsPathItem(path)
            item.setBrush(QBrush(self._heat_color(0.0)))
            item.setPen(QPen(QColor(66, 75, 84, 100), 0.75))
            item.setZValue(1)
            self.scene.addItem(item)
            self._area_items[code] = item
            lon = getattr(area, "centroid_lon", None)
            lat = getattr(area, "centroid_lat", None)
            if lon is not None and lat is not None:
                x, y = transform(float(lon), float(lat))
                label = QGraphicsSimpleTextItem(code)
                label.setBrush(QBrush(QColor(27, 35, 42)))
                label.setPos(x + 3.0, y + 3.0)
                label.setZValue(5)
                self.scene.addItem(label)
                self._area_labels[code] = label
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.summary_label.setText("Loaded %d spatial areas." % len(self._area_items))
        self.fit_to_map()

    def _heat_color(self, probability):
        value = max(0.0, min(1.0, float(probability)))
        low = QColor(236, 244, 242)
        high = QColor(16, 105, 116)
        red = int(round(low.red() + (high.red() - low.red()) * value))
        green = int(round(low.green() + (high.green() - low.green()) * value))
        blue = int(round(low.blue() + (high.blue() - low.blue()) * value))
        return QColor(red, green, blue, 225)

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

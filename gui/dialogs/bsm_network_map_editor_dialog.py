import json
import math
from pathlib import Path

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QBrush, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from application.services.bsm_dispersal_network_service import BSMDispersalNetworkService
from gui.window_behavior import configure_resizable_window


class _NetworkEditorView(QGraphicsView):
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


class _ControlHandle(QGraphicsEllipseItem):
    def __init__(self, editor, edge_key, role, x, y):
        size = 14 if str(role) == "curve" else 10
        super().__init__(-size * 0.5, -size * 0.5, size, size)
        self.editor = editor
        self.edge_key = edge_key
        self.role = role
        self.setPos(float(x), float(y))
        if str(role) == "curve":
            self.setBrush(QBrush(QColor(255, 255, 255, 245)))
            self.setPen(QPen(QColor(35, 112, 180), 2.0))
        else:
            self.setBrush(QBrush(QColor(255, 255, 255, 230)))
            self.setPen(QPen(QColor(36, 42, 52), 1.2))
        self.setZValue(80)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setToolTip("%s curve handle" % edge_key if str(role) == "curve" else "%s %s control point" % (edge_key, role))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and not self.editor.is_redrawing:
            return self.editor.constrain_edge_control_position(self.edge_key, self.role, value)
        if change == QGraphicsItem.ItemPositionHasChanged and not self.editor.is_redrawing:
            self.editor.update_edge_control(self.edge_key, self.role, value)
        return super().itemChange(change, value)


class _EdgeLabelItem(QGraphicsSimpleTextItem):
    def __init__(self, editor, edge_key, text, x, y):
        super().__init__(text)
        self.editor = editor
        self.edge_key = edge_key
        font = QFont("Arial")
        font.setPixelSize(10)
        font.setBold(True)
        self.setFont(font)
        self.setBrush(QBrush(QColor(18, 24, 32)))
        self.setPos(float(x), float(y))
        self.setZValue(70)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setToolTip("%s label" % edge_key)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and not self.editor.is_redrawing:
            self.editor.update_edge_label(self.edge_key, value)
        return super().itemChange(change, value)


class BSMNetworkMapEditorDialog(QDialog):
    LAYOUT_FORMAT = "rasp5_bsm_network_layout"
    LAYOUT_VERSION = 2
    """Map-based editor for BSM dispersal network figure layouts.

    This dialog consumes existing data from upstream modules. It can draw on
    spatial area polygons when available, or fall back to a schematic network
    when no spatial project has been loaded. It does not generate BSM events or
    import GeoJSON by itself.
    """

    PAPER_AREA_COLORS = {
        # One-letter RASP/BioGeoBEARS areas mapped onto the Daru et al.
        # global plant realm palette when their meanings are known.
        "A": "#7A8E42",  # Afrotropic / Afrotropics
        "U": "#516A78",  # Australasia
        "I": "#A3B18A",  # Indo-Malay / Indomalaya
        "R": "#D9A441",  # Nearctic
        "N": "#1B5E20",  # Neotropic / Neotropics
        "E": "#5B8FA8",  # East Asia / Eastern Palearctic-like slot
        "W": "#8C5A3C",  # Palearctic / Western Palearctic
        # Daru et al. global plant realm abbreviations.
        "AFR": "#7A8E42",
        "AUS": "#516A78",
        "IDM": "#A3B18A",
        "NEA": "#D9A441",
        "NEO": "#1B5E20",
        "PAL": "#8C5A3C",
        "EAS": "#5B8FA8",
    }

    def __init__(self, result, area_records=None, range_matrix=None, parent=None):
        super().__init__(parent)
        self.result = result
        self.area_records = list(area_records or [])
        self.range_matrix = range_matrix
        self.network_service = BSMDispersalNetworkService()
        self.current_network = None
        self.edge_layout = {}
        self.manual_edge_layout = {}
        self.edge_items = {}
        self.node_geometry = {}
        self.is_redrawing = False
        self._last_layout_mode = "auto"
        self._active_layout_mode = "auto"
        self._edge_width_divisor = 1.0
        self._visible_edge_rows = []
        self._view_initialized = False

        self.setWindowTitle("BSM Network Map Editor")
        self.resize(1280, 760)
        configure_resizable_window(self)
        self._build_ui()
        self.refresh_network(reset_layout=True)

    def _build_ui(self):
        root = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Layout:", self))
        self.layout_mode_combo = QComboBox(self)
        self.layout_mode_combo.addItem("Auto", "auto")
        self.layout_mode_combo.addItem("Map", "map")
        self.layout_mode_combo.addItem("Circle network", "network")
        self.layout_mode_combo.currentIndexChanged.connect(self._on_layout_mode_changed)
        controls.addWidget(self.layout_mode_combo)
        self.projection_label = QLabel("Projection:", self)
        controls.addWidget(self.projection_label)
        self.projection_combo = QComboBox(self)
        self.projection_combo.addItem("Equirectangular", "equirectangular")
        self.projection_combo.addItem("Robinson", "robinson")
        self.projection_combo.addItem("Equal Earth", "equal_earth")
        self.projection_combo.addItem("Mollweide", "mollweide")
        self.projection_combo.addItem("Winkel Tripel", "winkel_tripel")
        self.projection_combo.addItem("Mercator", "mercator")
        self.projection_combo.setToolTip("Map projection used for spatial BSM network display and PNG export.")
        self.projection_combo.currentIndexChanged.connect(self._on_projection_changed)
        controls.addWidget(self.projection_combo)
        controls.addWidget(QLabel("Min mean events/map:", self))
        self.threshold_edit = QLineEdit(self)
        self.threshold_edit.setText("5")
        self.threshold_edit.setFixedWidth(70)
        self.threshold_edit.editingFinished.connect(lambda: self.refresh_network(reset_layout=False))
        controls.addWidget(self.threshold_edit)
        self.edge_percentile_label = QLabel("Circle edge percentile:", self)
        controls.addWidget(self.edge_percentile_label)
        self.edge_percentile_edit = QLineEdit(self)
        self.edge_percentile_edit.setText("0")
        self.edge_percentile_edit.setFixedWidth(48)
        self.edge_percentile_edit.setToolTip("Hide edges below this percentile of visible edge weights. 0 keeps all edges passing the mean threshold; 50 matches the paper-style median filter.")
        self.edge_percentile_edit.editingFinished.connect(self.redraw)
        controls.addWidget(self.edge_percentile_edit)
        self.width_scale_label = QLabel("Edge width scale:", self)
        controls.addWidget(self.width_scale_label)
        self.width_scale_edit = QLineEdit(self)
        self.width_scale_edit.setText("1.0")
        self.width_scale_edit.setFixedWidth(48)
        self.width_scale_edit.setToolTip("Multiply rendered edge widths. Data values are unchanged.")
        self.width_scale_edit.editingFinished.connect(self.redraw_edges_only)
        controls.addWidget(self.width_scale_edit)
        self.include_anagenetic_check = QCheckBox("Anagenetic d/a", self)
        self.include_anagenetic_check.setChecked(True)
        self.include_anagenetic_check.toggled.connect(lambda: self.refresh_network(reset_layout=False))
        controls.addWidget(self.include_anagenetic_check)
        self.include_founder_check = QCheckBox("Founder j", self)
        self.include_founder_check.setChecked(True)
        self.include_founder_check.toggled.connect(lambda: self.refresh_network(reset_layout=False))
        controls.addWidget(self.include_founder_check)
        self.show_handles_check = QCheckBox("Edit handles", self)
        self.show_handles_check.setChecked(False)
        self.show_handles_check.setToolTip("Show draggable curve handles for adjusting map and circle-network edge curves.")
        self.show_handles_check.toggled.connect(self.redraw)
        controls.addWidget(self.show_handles_check)
        self.show_values_check = QCheckBox("Edge values", self)
        self.show_values_check.setChecked(False)
        self.show_values_check.toggled.connect(self.redraw)
        controls.addWidget(self.show_values_check)
        self.show_area_labels_check = QCheckBox("Area labels", self)
        self.show_area_labels_check.setChecked(False)
        self.show_area_labels_check.toggled.connect(self.redraw)
        controls.addWidget(self.show_area_labels_check)
        self.reset_layout_button = QPushButton("Reset Auto Layout", self)
        self.reset_layout_button.clicked.connect(lambda: self.refresh_network(reset_layout=True))
        controls.addWidget(self.reset_layout_button)
        controls.addStretch(1)
        self.save_layout_button = QPushButton("Save Layout", self)
        self.save_layout_button.clicked.connect(self.save_layout)
        controls.addWidget(self.save_layout_button)
        self.load_layout_button = QPushButton("Load Layout", self)
        self.load_layout_button.clicked.connect(self.load_layout)
        controls.addWidget(self.load_layout_button)
        self.export_png_button = QPushButton("Export PNG", self)
        self.export_png_button.clicked.connect(self.export_png)
        controls.addWidget(self.export_png_button)
        root.addLayout(controls)

        self.source_label = QLabel("", self)
        self.source_label.setWordWrap(True)
        root.addWidget(self.source_label)

        splitter = QSplitter(Qt.Horizontal, self)
        self.scene = QGraphicsScene(self)
        self.view = _NetworkEditorView(self)
        self.view.setScene(self.scene)
        splitter.addWidget(self.view)

        side_panel = QWidget(splitter)
        side_layout = QVBoxLayout(side_panel)
        self.info_text = QTextEdit(side_panel)
        self.info_text.setReadOnly(True)
        self.info_text.setLineWrapMode(QTextEdit.NoWrap)
        side_layout.addWidget(self.info_text, 1)
        splitter.addWidget(side_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        root.addLayout(close_row)

    def refresh_network(self, reset_layout=False):
        threshold = self._safe_float(self.threshold_edit.text(), 5.0)
        self.current_network = self.network_service.build_network(
            self.result,
            areas=self.area_records,
            range_matrix=self.range_matrix,
            min_mean_per_map=threshold,
            include_anagenetic=self.include_anagenetic_check.isChecked(),
            include_founder=self.include_founder_check.isChecked(),
        )
        if reset_layout:
            self.edge_layout = {}
            self.manual_edge_layout = {}
        self.redraw(fit_view=reset_layout or not self._view_initialized)

    def redraw(self, *_args, fit_view=False):
        self._sync_interactive_items_to_layout()
        self.is_redrawing = True
        try:
            self.scene.clear()
            self.edge_items = {}
            self.node_geometry = {}
            network = self.current_network or {}
            areas = list(self.area_records or [])
            node_rows = list(network.get("node_rows", []) or [])
            raw_edge_rows = list(network.get("display_edge_rows", []) or [])
            bounds = self._bounds(areas, node_rows)
            layout_mode = self._effective_layout_mode(bounds)
            self._active_layout_mode = layout_mode
            self._sync_mode_controls(layout_mode)
            edge_rows = self._filtered_edge_rows(raw_edge_rows)
            self._visible_edge_rows = list(edge_rows)
            if layout_mode == "map" and bounds is None:
                self.scene.setSceneRect(0, 0, 900, 520)
                message = "No spatial coordinates are available. Switch Layout to Circle network, or load an area GeoJSON for map mode."
                self.scene.addText(message)
                self.source_label.setText(message)
                self.info_text.setPlainText(message)
                return
            if layout_mode == "map":
                transform = self._transform(bounds)
                self._draw_areas(areas, transform)
                self.node_geometry = self._build_node_geometry(node_rows, transform)
            else:
                self._draw_schematic_background()
                self.node_geometry = self._build_schematic_node_geometry(node_rows, edge_rows)
            self._ensure_edge_layout(edge_rows)
            self._draw_edges(edge_rows)
            self._draw_nodes(node_rows, layout_mode=layout_mode)
            rect = self.scene.itemsBoundingRect().adjusted(-30, -30, 30, 30)
            self.scene.setSceneRect(rect)
            if fit_view or not self._view_initialized:
                self.view.fit_to_scene()
                self._view_initialized = True
            self._update_info(network, edge_rows, layout_mode)
        finally:
            self.is_redrawing = False

    def redraw_edges_only(self, *_args):
        if not self._visible_edge_rows or not self.node_geometry:
            self.redraw(fit_view=False)
            return
        if self._active_layout_mode == "network":
            self.redraw(fit_view=False)
            return
        self._sync_interactive_items_to_layout()
        self.is_redrawing = True
        try:
            edge_rows = list(self._visible_edge_rows or [])
            self._ensure_edge_layout(edge_rows)
            old_items_by_key = {}
            for row in edge_rows:
                key = self._edge_key(row)
                old = self.edge_items.pop(key, {})
                old_items_by_key[key] = old
                for item in [old.get("path"), old.get("arrow"), old.get("label")]:
                    if item is not None and item.scene() is self.scene:
                        self.scene.removeItem(item)
            self._edge_width_divisor = self._circle_width_divisor(edge_rows) if self._active_layout_mode == "network" else 1.0
            max_mean = max(float(row.get("mean_per_map", 0.0) or 0.0) for row in edge_rows) if edge_rows else 1.0
            for row in sorted(edge_rows, key=lambda item: float(item.get("mean_per_map", 0.0) or 0.0)):
                self._draw_single_edge(
                    row,
                    max_mean,
                    preserve_handles=True,
                    existing_handles=old_items_by_key.get(self._edge_key(row), {}).get("handles", []) or [],
                )
        finally:
            self.is_redrawing = False

    def _on_layout_mode_changed(self, *_args):
        self.edge_layout = {}
        self.manual_edge_layout = {}
        self.redraw(fit_view=True)

    def _on_projection_changed(self, *_args):
        self.edge_layout = {}
        self.manual_edge_layout = {}
        self.redraw(fit_view=True)

    def _sync_mode_controls(self, layout_mode):
        is_network = str(layout_mode or "") == "network"
        is_map = str(layout_mode or "") == "map"
        can_edit_curves = is_map or is_network
        for widget in (self.projection_label, self.projection_combo):
            widget.setVisible(is_map)
            widget.setEnabled(is_map)
        for widget in (self.edge_percentile_label, self.edge_percentile_edit):
            widget.setVisible(is_network)
            widget.setEnabled(is_network)
        self.show_handles_check.setVisible(can_edit_curves)
        self.show_handles_check.setEnabled(can_edit_curves)
        if not can_edit_curves and self.show_handles_check.isChecked():
            old_state = self.show_handles_check.blockSignals(True)
            self.show_handles_check.setChecked(False)
            self.show_handles_check.blockSignals(old_state)

    def update_edge_control(self, edge_key, role, position):
        layout = self.edge_layout.setdefault(str(edge_key), {})
        row = None
        for edge in list(self._visible_edge_rows or []):
            if self._edge_key(edge) == edge_key:
                row = edge
                break
        if str(role) == "curve" and row is not None:
            self._apply_curve_handle(layout, row, position)
        else:
            layout[str(role)] = [float(position.x()), float(position.y())]
        self._remember_manual_edge_layout(edge_key)
        if row is not None:
            self._redraw_single_edge(row, preserve_handles=True)

    def constrain_edge_control_position(self, edge_key, role, position):
        if str(role) != "curve" or self._active_layout_mode not in ("map", "network"):
            return position
        row = None
        for edge in list(self._visible_edge_rows or []):
            if self._edge_key(edge) == edge_key:
                row = edge
                break
        if row is None:
            return position
        source = str(row.get("source_area", "") or "")
        target = str(row.get("target_area", "") or "")
        source_geom = self.node_geometry.get(source)
        target_geom = self.node_geometry.get(target)
        if not source_geom or not target_geom:
            return position
        x1 = float(source_geom["x"])
        y1 = float(source_geom["y"])
        x2 = float(target_geom["x"])
        y2 = float(target_geom["y"])
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx * dx + dy * dy) or 1.0
        nx = -dy / length
        ny = dx / length
        mid = QPointF((x1 + x2) * 0.5, (y1 + y2) * 0.5)
        raw_offset = (float(position.x()) - mid.x()) * nx + (float(position.y()) - mid.y()) * ny
        limit = min(260.0, max(70.0, length * 0.55))
        offset = max(-limit, min(limit, raw_offset))
        return QPointF(mid.x() + nx * offset, mid.y() + ny * offset)

    def update_edge_label(self, edge_key, position):
        layout = self.edge_layout.setdefault(str(edge_key), {})
        layout["label"] = [float(position.x()), float(position.y())]
        layout["label_manual"] = True
        self._remember_manual_edge_layout(edge_key)

    def _sync_interactive_items_to_layout(self):
        if self.is_redrawing:
            return
        if not self.edge_items:
            return
        row_by_key = {
            self._edge_key(row): row
            for row in list(self._visible_edge_rows or [])
        }
        for key, items in list(self.edge_items.items()):
            row = row_by_key.get(key)
            layout = None
            changed = False
            if row is not None:
                for handle in list((items or {}).get("handles", []) or []):
                    if handle is None or handle.scene() is not self.scene:
                        continue
                    if layout is None:
                        layout = self.edge_layout.setdefault(str(key), {})
                    role = str(getattr(handle, "role", "") or "")
                    position = handle.scenePos()
                    if role == "curve":
                        self._apply_curve_handle(layout, row, position)
                        changed = True
                    elif role:
                        layout[role] = [float(position.x()), float(position.y())]
                        changed = True
            label = (items or {}).get("label")
            if label is not None and label.scene() is self.scene:
                if layout is None:
                    layout = self.edge_layout.setdefault(str(key), {})
                position = label.scenePos()
                layout["label"] = [float(position.x()), float(position.y())]
                layout["label_manual"] = True
                changed = True
            if changed:
                self._remember_manual_edge_layout(key)

    def _apply_curve_handle(self, layout, row, position):
        source = str(row.get("source_area", "") or "")
        target = str(row.get("target_area", "") or "")
        source_geom = self.node_geometry.get(source)
        target_geom = self.node_geometry.get(target)
        if not source_geom or not target_geom:
            return
        x1 = float(source_geom["x"])
        y1 = float(source_geom["y"])
        x2 = float(target_geom["x"])
        y2 = float(target_geom["y"])
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx * dx + dy * dy) or 1.0
        nx = -dy / length
        ny = dx / length
        mid = QPointF((x1 + x2) * 0.5, (y1 + y2) * 0.5)
        raw_offset = (float(position.x()) - mid.x()) * nx + (float(position.y()) - mid.y()) * ny
        limit = min(260.0, max(70.0, length * 0.55))
        offset = max(-limit, min(limit, raw_offset))
        c1 = QPointF(x1 + dx * 0.34 + nx * offset, y1 + dy * 0.34 + ny * offset)
        c2 = QPointF(x1 + dx * 0.68 + nx * offset, y1 + dy * 0.68 + ny * offset)
        curve = QPointF(mid.x() + nx * offset, mid.y() + ny * offset)
        layout["c1"] = [c1.x(), c1.y()]
        layout["c2"] = [c2.x(), c2.y()]
        layout["curve"] = [curve.x(), curve.y()]
        layout["curve_offset"] = offset
        layout["curve_manual"] = True
        if not layout.get("label_manual"):
            label = self._cubic_point(QPointF(x1, y1), c1, c2, QPointF(x2, y2), 0.52)
            label = QPointF(label.x() + nx * offset * 0.18, label.y() + ny * offset * 0.18)
            layout["label"] = [label.x(), label.y()]

    def _draw_areas(self, areas, transform):
        for index, area in enumerate(areas):
            path = self._path_from_geometry(getattr(area, "geometry", {}) or {}, transform)
            if path.isEmpty():
                continue
            color = self._color(getattr(area, "color", "") or "", index)
            item = QGraphicsPathItem(path)
            item.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 44)))
            item.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 155), 0.65))
            item.setZValue(0)
            item.setToolTip("Area: %s" % str(getattr(area, "display_name", "") or getattr(area, "area_code", "")))
            self.scene.addItem(item)

    def _build_node_geometry(self, node_rows, transform):
        rich_values = [float(row.get("richness", 0.0) or 0.0) for row in node_rows]
        max_rich = max(rich_values) if rich_values else 1.0
        if max_rich <= 0:
            max_rich = 1.0
        geometry = {}
        for index, row in enumerate(node_rows):
            code = str(row.get("area_code", "") or "")
            lon = self._safe_float(row.get("centroid_lon"), None)
            lat = self._safe_float(row.get("centroid_lat"), None)
            if not code or lon is None or lat is None:
                continue
            x, y = transform(lon, lat)
            richness = float(row.get("richness", 0.0) or 0.0)
            color = row.get("color", "")
            if not QColor(str(color or "")).isValid():
                color = self._color("", index).name()
            geometry[code] = {
                "x": x,
                "y": y,
                "radius": 7.0 + 21.0 * math.sqrt(richness / max_rich),
                "richness": richness,
                "color": color,
            }
        return geometry

    def _draw_schematic_background(self):
        # Circle-network mode intentionally has no map or decorative orbit.
        # It follows the igraph::layout.circle style used in the plant-realm
        # exchange figures, where the network itself carries the comparison.
        self.scene.setSceneRect(0, 0, 780, 760)

    def _circle_node_label(self, code):
        text = str(code or "").strip()
        if len(text) <= 4:
            return text
        parts = [part for part in text.replace("-", "_").split("_") if part]
        if len(parts) > 1:
            label = "".join(part[:1].upper() for part in parts)
            if 1 < len(label) <= 4:
                return label
        return text[:4].upper()

    def _build_schematic_node_geometry(self, node_rows, edge_rows):
        codes = []
        row_by_code = {}
        for row in list(node_rows or []):
            code = str(row.get("area_code", "") or "")
            if code:
                row_by_code[code] = row
        for row in list(edge_rows or []):
            for key in ("source_area", "target_area"):
                code = str(row.get(key, "") or "")
                if code and code not in codes:
                    codes.append(code)
                    if code not in row_by_code:
                        row_by_code[code] = {"area_code": code, "display_name": code, "richness": 0.0}
        if not codes:
            for row in list(node_rows or []):
                code = str(row.get("area_code", "") or "")
                if code and code not in codes:
                    codes.append(code)

        if not codes:
            return {}

        order = self._schematic_order(codes)
        rich_values = [float(row_by_code.get(code, {}).get("richness", 0.0) or 0.0) for code in order]
        max_rich = max(rich_values) if rich_values else 1.0
        if max_rich <= 0:
            max_rich = 1.0

        center_x = 390.0
        center_y = 360.0
        radius = 250.0
        start_angle = -90.0
        geometry = {}
        for index, code in enumerate(order):
            angle = math.radians(start_angle + 360.0 * float(index) / float(len(order)))
            row = row_by_code.get(code, {})
            richness = float(row.get("richness", 0.0) or 0.0)
            color = row.get("color", "") or self.PAPER_AREA_COLORS.get(code, "")
            if not QColor(str(color or "")).isValid():
                color = self._color("", index).name()
            geometry[code] = {
                "x": center_x + math.cos(angle) * radius,
                "y": center_y + math.sin(angle) * radius,
                "radius": 22.0,
                "richness": richness,
                "color": color,
                "angle": angle,
                "layout": "circle",
                "label": self._circle_node_label(code),
                "display_name": row.get("display_name", "") or code,
            }
        return geometry

    def _schematic_order(self, codes):
        preferred = [
            "EAS", "AUS", "AFR", "PAL", "NEO", "NEA", "IDM",
            "E", "U", "A", "W", "N", "R", "I",
        ]
        seen = []
        for code in preferred:
            if code in codes and code not in seen:
                seen.append(code)
        for code in sorted(codes):
            if code not in seen:
                seen.append(code)
        return seen

    def _draw_nodes(self, node_rows, layout_mode="map"):
        row_by_code = {
            str(row.get("area_code", "") or ""): row
            for row in list(node_rows or [])
            if str(row.get("area_code", "") or "")
        }
        rows_to_draw, drawn_codes = self._node_rows_for_drawing(node_rows, layout_mode)
        for row in rows_to_draw:
            code = str(row.get("area_code", "") or "")
            geom = self.node_geometry.get(code)
            if not geom:
                continue
            x = float(geom["x"])
            y = float(geom["y"])
            radius = float(geom["radius"])
            richness = max(float(geom.get("richness", 0.0) or 0.0), float(row.get("richness", 0.0) or 0.0))
            base = QColor(str(row.get("color", "") or geom.get("color", "") or ""))
            if not base.isValid():
                base = QColor(120, 150, 180)
            item = QGraphicsEllipseItem(x - radius, y - radius, radius * 2.0, radius * 2.0)
            if layout_mode == "network":
                item.setBrush(QBrush(QColor(base.red(), base.green(), base.blue(), 235)))
                item.setPen(QPen(QColor(base.darker(130)), 1.0))
            else:
                item.setBrush(QBrush(QColor(base.red(), base.green(), base.blue(), 118)))
                item.setPen(QPen(QColor(base.red(), base.green(), base.blue(), 185), 1.2))
            item.setZValue(50)
            item.setToolTip("%s\nrichness=%s" % (row.get("display_name", ""), self._format_number(richness)))
            self.scene.addItem(item)

            if layout_mode == "network":
                node_text = str(geom.get("label", "") or code)
            elif richness > 0:
                node_text = self._format_number(richness)
            elif len(code) <= 4:
                node_text = code
            else:
                node_text = ""
            if layout_mode == "network":
                self._add_text_path(node_text, x, y, 17, QColor(16, 22, 28), 52, center=True, bold=True)
            elif node_text:
                label = QGraphicsSimpleTextItem(node_text)
                font = QFont("Segoe UI")
                font.setPixelSize(11)
                font.setBold(True)
                label.setFont(font)
                label.setBrush(QBrush(QColor(22, 27, 32)))
                rect = label.boundingRect()
                label.setPos(x - rect.width() * 0.5, y - rect.height() * 0.5)
                label.setZValue(52)
                self.scene.addItem(label)

            if layout_mode == "network" and self.show_area_labels_check.isChecked():
                name = str(row.get("display_name", "") or code)
                if name != code:
                    angle = float(geom.get("angle", 0.0))
                    lx = x + math.cos(angle) * (radius + 18.0)
                    ly = y + math.sin(angle) * (radius + 18.0)
                    self._add_text_path(name, lx, ly, 9, QColor(36, 42, 52), 52, center=True, bold=False)
            elif layout_mode == "map" and self.show_area_labels_check.isChecked():
                name = str(row.get("display_name", "") or code)
                if name:
                    self._add_map_area_label(name, x, y, radius)

        # Draw geometry entries that only came from visible edges and not from
        # node_rows. This keeps network-only mode useful even without a matrix.
        for code, geom in sorted(self.node_geometry.items()):
            if code in row_by_code or code in drawn_codes:
                continue
            x = float(geom["x"])
            y = float(geom["y"])
            radius = float(geom["radius"])
            base = QColor(str(geom.get("color", "") or ""))
            if not base.isValid():
                base = QColor(120, 150, 180)
            item = QGraphicsEllipseItem(x - radius, y - radius, radius * 2.0, radius * 2.0)
            item.setBrush(QBrush(QColor(base.red(), base.green(), base.blue(), 235 if layout_mode == "network" else 135)))
            item.setPen(QPen(QColor(base.darker(130)), 1.0 if layout_mode == "network" else 1.2))
            item.setZValue(50)
            self.scene.addItem(item)
            if layout_mode == "network":
                self._add_text_path(str(geom.get("label", "") or code), x, y, 17, QColor(16, 22, 28), 52, center=True, bold=True)
            else:
                text = str(geom.get("label", "") or code)
                if len(text) > 4:
                    text = ""
                if not text:
                    continue
                label = QGraphicsSimpleTextItem(text)
                font = QFont("Arial")
                font.setPixelSize(10)
                font.setBold(True)
                label.setFont(font)
                label.setBrush(QBrush(QColor(16, 22, 28)))
                rect = label.boundingRect()
                label.setPos(x - rect.width() * 0.5, y - rect.height() * 0.5)
                label.setZValue(52)
                self.scene.addItem(label)

    def _node_rows_for_drawing(self, node_rows, layout_mode):
        if layout_mode == "network":
            rows = []
            seen = set()
            for row in list(node_rows or []):
                code = str(row.get("area_code", "") or "")
                if not code or code in seen:
                    continue
                seen.add(code)
                rows.append(row)
            return rows, seen

        clusters = {}
        order = []
        for row in list(node_rows or []):
            code = str(row.get("area_code", "") or "")
            geom = self.node_geometry.get(code)
            if not code or not geom:
                continue
            key = (round(float(geom.get("x", 0.0)), 1), round(float(geom.get("y", 0.0)), 1))
            if key not in clusters:
                merged = dict(row)
                merged["_merged_codes"] = [code]
                clusters[key] = merged
                order.append(key)
                continue
            merged = clusters[key]
            merged["_merged_codes"].append(code)
            old_richness = float(merged.get("richness", 0.0) or 0.0)
            new_richness = float(row.get("richness", 0.0) or 0.0)
            if new_richness > old_richness:
                merged["area_code"] = code
                merged["richness"] = new_richness
            old_name = str(merged.get("display_name", "") or "")
            new_name = str(row.get("display_name", "") or "")
            if new_name and (not old_name or len(new_name) > len(old_name)):
                merged["display_name"] = new_name
            if row.get("color") and not merged.get("color"):
                merged["color"] = row.get("color")

        rows = [clusters[key] for key in order]
        drawn_codes = set()
        for row in rows:
            for code in list(row.get("_merged_codes", []) or []):
                drawn_codes.add(str(code))
        return rows, drawn_codes

    def _add_map_area_label(self, text, x, y, radius):
        label = QGraphicsSimpleTextItem(str(text))
        font = QFont("Segoe UI")
        font.setPixelSize(11)
        font.setBold(False)
        label.setFont(font)
        label.setBrush(QBrush(QColor(34, 39, 44)))
        rect = label.boundingRect()
        lx = float(x) - rect.width() * 0.5
        ly = float(y) - float(radius) - rect.height() - 5.0
        label.setPos(lx, ly)
        label.setZValue(53)
        self.scene.addItem(label)

    def _ensure_edge_layout(self, edge_rows):
        curve_by_pair = self._curve_by_pair(edge_rows)
        for index, row in enumerate(edge_rows):
            key = self._edge_key(row)
            manual_layout = self.manual_edge_layout.get(key)
            if manual_layout:
                self.edge_layout[key] = self._copy_edge_layout(manual_layout)
            if self._has_complete_edge_layout(self.edge_layout.get(key)):
                continue
            source = str(row.get("source_area", "") or "")
            target = str(row.get("target_area", "") or "")
            source_geom = self.node_geometry.get(source)
            target_geom = self.node_geometry.get(target)
            if not source_geom or not target_geom:
                continue
            x1 = float(source_geom["x"])
            y1 = float(source_geom["y"])
            x2 = float(target_geom["x"])
            y2 = float(target_geom["y"])
            dx = x2 - x1
            dy = y2 - y1
            length = math.sqrt(dx * dx + dy * dy) or 1.0
            nx = -dy / length
            ny = dx / length
            if source_geom.get("layout") == "circle" and target_geom.get("layout") == "circle":
                offset = min(150.0, max(42.0, length * 0.30))
            else:
                sign = 1.0 if source < target else -1.0
                base = float(curve_by_pair.get(tuple(sorted([source, target])), 28.0))
                offset = base * sign
            c1 = QPointF(x1 + dx * 0.34 + nx * offset, y1 + dy * 0.34 + ny * offset)
            c2 = QPointF(x1 + dx * 0.68 + nx * offset, y1 + dy * 0.68 + ny * offset)
            curve = QPointF((x1 + x2) * 0.5 + nx * offset, (y1 + y2) * 0.5 + ny * offset)
            label = self._cubic_point(QPointF(x1, y1), c1, c2, QPointF(x2, y2), 0.52)
            label = QPointF(label.x() + nx * offset * 0.18, label.y() + ny * offset * 0.18)
            self.edge_layout[key] = {
                "source": source,
                "target": target,
                "c1": [c1.x(), c1.y()],
                "c2": [c2.x(), c2.y()],
                "curve": [curve.x(), curve.y()],
                "curve_offset": offset,
                "label": [label.x(), label.y()],
            }

    def _copy_edge_layout(self, layout):
        return {
            name: list(value) if isinstance(value, list) else value
            for name, value in dict(layout or {}).items()
        }

    def _has_complete_edge_layout(self, layout):
        if not layout:
            return False
        return all(name in layout for name in ("c1", "c2", "label"))

    def _remember_manual_edge_layout(self, edge_key):
        key = str(edge_key)
        layout = self.edge_layout.get(key)
        if not layout:
            return
        self.manual_edge_layout[key] = self._copy_edge_layout(layout)

    def _draw_edges(self, edge_rows):
        max_mean = max(float(row.get("mean_per_map", 0.0) or 0.0) for row in edge_rows) if edge_rows else 1.0
        self._edge_width_divisor = self._circle_width_divisor(edge_rows) if self._active_layout_mode == "network" else 1.0
        for row in sorted(edge_rows, key=lambda item: float(item.get("mean_per_map", 0.0) or 0.0)):
            self._draw_single_edge(row, max_mean)
        if self._active_layout_mode == "network":
            self._draw_circle_width_legend(edge_rows)

    def _filtered_edge_rows(self, edge_rows):
        rows = list(edge_rows or [])
        if self._active_layout_mode != "network":
            return rows
        percentile = self._edge_filter_percentile()
        if percentile <= 0.0 or not rows:
            return rows
        values = sorted(
            float(row.get("mean_per_map", 0.0) or 0.0)
            for row in rows
            if float(row.get("mean_per_map", 0.0) or 0.0) > 0
        )
        if not values:
            return rows
        cutoff = self._percentile(values, percentile)
        return [
            row for row in rows
            if float(row.get("mean_per_map", 0.0) or 0.0) >= cutoff
        ]

    def _edge_filter_percentile(self):
        value = self._safe_float(self.edge_percentile_edit.text() if hasattr(self, "edge_percentile_edit") else "0", 0.0)
        return max(0.0, min(99.0, float(value or 0.0)))

    def _edge_width_scale(self):
        value = self._safe_float(self.width_scale_edit.text() if hasattr(self, "width_scale_edit") else "1.0", 1.0)
        return max(0.2, min(5.0, float(value or 1.0)))

    def _percentile(self, sorted_values, percentile):
        values = list(sorted_values or [])
        if not values:
            return 0.0
        if len(values) == 1:
            return float(values[0])
        position = max(0.0, min(100.0, float(percentile))) / 100.0 * float(len(values) - 1)
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return float(values[lower])
        fraction = position - float(lower)
        return float(values[lower]) * (1.0 - fraction) + float(values[upper]) * fraction

    def _circle_width_divisor(self, edge_rows):
        values = sorted(
            float(row.get("mean_per_map", 0.0) or 0.0)
            for row in list(edge_rows or [])
            if float(row.get("mean_per_map", 0.0) or 0.0) > 0
        )
        if not values:
            return 1.0
        if len(values) == 1:
            q95 = values[0]
        else:
            position = 0.95 * float(len(values) - 1)
            lower = int(math.floor(position))
            upper = int(math.ceil(position))
            if lower == upper:
                q95 = values[lower]
            else:
                fraction = position - float(lower)
                q95 = values[lower] * (1.0 - fraction) + values[upper] * fraction
        return max(q95 / 6.0, 1e-9)

    def _draw_circle_width_legend(self, edge_rows):
        values = [
            float(row.get("mean_per_map", 0.0) or 0.0)
            for row in list(edge_rows or [])
            if float(row.get("mean_per_map", 0.0) or 0.0) > 0
        ]
        if not values:
            return
        divisor = self._edge_width_divisor or 1.0
        max_value = max(values)
        legend_values = [2.0 * divisor, 5.0 * divisor, min(10.0 * divisor, max_value)]
        deduped = []
        for value in legend_values:
            if value <= 0:
                continue
            if any(abs(value - old) / max(old, 1e-9) < 0.08 for old in deduped):
                continue
            deduped.append(value)
        if not deduped:
            return
        x = 34.0
        y = 668.0
        self._add_text_path(
            "Dispersal events/map",
            x,
            y - 20.0,
            13,
            QColor(44, 48, 54),
            90,
            center=False,
            bold=True,
        )
        for index, value in enumerate(deduped):
            yy = y + float(index) * 25.0
            width = min(10.0, max(2.0, value / divisor)) * self._edge_width_scale()
            pen = QPen(QColor(78, 82, 88), width)
            pen.setCapStyle(Qt.RoundCap)
            line = self.scene.addLine(x, yy, x + 76.0, yy, pen)
            line.setZValue(90)
            self._add_text_path(
                self._format_number(value),
                x + 88.0,
                yy + 4.0,
                12,
                QColor(44, 48, 54),
                90,
                center=False,
                bold=False,
            )

    def _add_text_path(self, text, x, y, pixel_size, color, z_value, center=False, bold=False):
        item = QGraphicsSimpleTextItem(str(text))
        font = QFont("Arial")
        font.setPixelSize(int(pixel_size))
        font.setBold(bool(bold))
        item.setFont(font)
        item.setBrush(QBrush(color))
        rect = item.boundingRect()
        if center:
            item.setPos(float(x) - rect.width() * 0.5, float(y) - rect.height() * 0.5)
        else:
            item.setPos(float(x), float(y) - rect.height())
        item.setZValue(float(z_value))
        self.scene.addItem(item)
        return item

    def _draw_single_edge(self, row, max_mean, preserve_handles=False, existing_handles=None):
        key = self._edge_key(row)
        source = str(row.get("source_area", "") or "")
        target = str(row.get("target_area", "") or "")
        source_geom = self.node_geometry.get(source)
        target_geom = self.node_geometry.get(target)
        layout = self.edge_layout.get(key)
        if not source_geom or not target_geom or not layout:
            return
        start = QPointF(float(source_geom["x"]), float(source_geom["y"]))
        target_center = QPointF(float(target_geom["x"]), float(target_geom["y"]))
        c1 = QPointF(float(layout["c1"][0]), float(layout["c1"][1]))
        c2 = QPointF(float(layout["c2"][0]), float(layout["c2"][1]))
        if self._active_layout_mode == "map" and "curve" not in layout:
            layout["curve"] = self._curve_handle_from_controls(start, target_center, c1, c2)
        mean = float(row.get("mean_per_map", 0.0) or 0.0)
        if self._active_layout_mode == "network":
            divisor = self._edge_width_divisor or 1.0
            width = min(10.0, max(2.0, mean / divisor)) * self._edge_width_scale()
        else:
            width = (0.8 + 7.0 * math.sqrt(mean / (max_mean or 1.0))) * self._edge_width_scale()
        color = QColor(str(source_geom.get("color", "") or ""))
        if not color.isValid():
            color = QColor(43, 91, 155)
        color.setAlpha(215)
        samples = self._cubic_samples(start, c1, c2, target_center, 72)
        tip = self._clip_samples_to_target(samples, target_center, float(target_geom["radius"]) + 2.5)
        line_points, arrow = self._split_line_and_arrow(samples[: tip + 1], width)
        path = QPainterPath(line_points[0])
        for point in line_points[1:]:
            path.lineTo(point)
        item = QGraphicsPathItem(path)
        pen = QPen(color, width)
        pen.setCapStyle(Qt.FlatCap)
        item.setPen(pen)
        item.setZValue(30)
        item.setToolTip("%s -> %s\n%s mean events/map" % (source, target, self._format_number(mean)))
        self.scene.addItem(item)

        arrow_item = None
        if arrow:
            base, tip_point = arrow
            arrow_item = self._make_arrow_item(base, tip_point, color, width)
            self.scene.addItem(arrow_item)

        label_item = None
        if self.show_values_check.isChecked():
            label_pos = QPointF(float(layout["label"][0]), float(layout["label"][1]))
            label_item = _EdgeLabelItem(self, key, self._format_number(mean), label_pos.x(), label_pos.y())
            self.scene.addItem(label_item)

        handles = list(existing_handles or []) if preserve_handles else []
        if self.show_handles_check.isChecked() and self._active_layout_mode in ("map", "network") and not preserve_handles:
            curve_xy = layout.get("curve")
            if not curve_xy:
                curve_point = self._cubic_point(start, c1, c2, target_center, 0.5)
                curve_xy = [curve_point.x(), curve_point.y()]
            handle = _ControlHandle(self, key, "curve", float(curve_xy[0]), float(curve_xy[1]))
            self.scene.addItem(handle)
            handles = [handle]
        elif preserve_handles and handles:
            curve_xy = layout.get("curve")
            if curve_xy:
                for handle in handles:
                    if getattr(handle, "role", "") == "curve" and handle.scene() is self.scene:
                        old_state = self.is_redrawing
                        self.is_redrawing = True
                        handle.setPos(float(curve_xy[0]), float(curve_xy[1]))
                        self.is_redrawing = old_state

        self.edge_items[key] = {
            "path": item,
            "arrow": arrow_item,
            "label": label_item,
            "handles": handles,
        }

    def _redraw_single_edge(self, row, preserve_handles=False):
        key = self._edge_key(row)
        old = self.edge_items.pop(key, {})
        items_to_remove = [old.get("path"), old.get("arrow"), old.get("label")]
        if not preserve_handles:
            items_to_remove += list(old.get("handles", []) or [])
        for item in items_to_remove:
            if item is not None and item.scene() is self.scene:
                self.scene.removeItem(item)
        edge_rows = list(self._visible_edge_rows or [])
        max_mean = max(float(edge.get("mean_per_map", 0.0) or 0.0) for edge in edge_rows) if edge_rows else 1.0
        self._draw_single_edge(row, max_mean, preserve_handles=preserve_handles, existing_handles=old.get("handles", []) or [])

    def _curve_handle_from_controls(self, start, target_center, c1, c2):
        dx = target_center.x() - start.x()
        dy = target_center.y() - start.y()
        length = math.sqrt(dx * dx + dy * dy) or 1.0
        nx = -dy / length
        ny = dx / length
        mid = QPointF((start.x() + target_center.x()) * 0.5, (start.y() + target_center.y()) * 0.5)
        control_mid = QPointF((c1.x() + c2.x()) * 0.5, (c1.y() + c2.y()) * 0.5)
        raw_offset = (control_mid.x() - mid.x()) * nx + (control_mid.y() - mid.y()) * ny
        limit = min(260.0, max(70.0, length * 0.55))
        offset = max(-limit, min(limit, raw_offset))
        return [mid.x() + nx * offset, mid.y() + ny * offset]

    def _make_arrow_item(self, base, tip, color, width):
        dx = tip.x() - base.x()
        dy = tip.y() - base.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-6:
            return None
        ux = dx / length
        uy = dy / length
        nx = -uy
        ny = ux
        size = max(7.0, float(width or 0.0) * 2.3)
        polygon = QPolygonF([
            QPointF(tip.x(), tip.y()),
            QPointF(base.x() + nx * size * 0.5, base.y() + ny * size * 0.5),
            QPointF(base.x() - nx * size * 0.5, base.y() - ny * size * 0.5),
        ])
        item = QGraphicsPolygonItem(polygon)
        item.setBrush(QBrush(color))
        item.setPen(QPen(Qt.NoPen))
        item.setZValue(35)
        return item

    def _clip_samples_to_target(self, samples, target_center, radius):
        for index in range(len(samples) - 1, 0, -1):
            dx = samples[index].x() - target_center.x()
            dy = samples[index].y() - target_center.y()
            if math.sqrt(dx * dx + dy * dy) > radius:
                return index
        return max(1, len(samples) - 1)

    def _split_line_and_arrow(self, samples, width):
        if len(samples) < 3:
            return samples, None
        head_length = max(10.0, float(width or 0.0) * 3.0)
        distance = 0.0
        tip = samples[-1]
        for index in range(len(samples) - 1, 0, -1):
            p1 = samples[index]
            p0 = samples[index - 1]
            dx = p1.x() - p0.x()
            dy = p1.y() - p0.y()
            segment = math.sqrt(dx * dx + dy * dy)
            if segment < 1e-6:
                continue
            if distance + segment >= head_length:
                remaining = head_length - distance
                ratio = remaining / segment
                base = QPointF(p1.x() - dx * ratio, p1.y() - dy * ratio)
                return samples[:index] + [base], (base, tip)
            distance += segment
        return samples[:-1], (samples[-2], tip)

    def _cubic_samples(self, p0, p1, p2, p3, count):
        return [self._cubic_point(p0, p1, p2, p3, float(i) / float(count - 1)) for i in range(count)]

    def _cubic_point(self, p0, p1, p2, p3, t):
        one = 1.0 - t
        x = one ** 3 * p0.x() + 3 * one * one * t * p1.x() + 3 * one * t * t * p2.x() + t ** 3 * p3.x()
        y = one ** 3 * p0.y() + 3 * one * one * t * p1.y() + 3 * one * t * t * p2.y() + t ** 3 * p3.y()
        return QPointF(x, y)

    def save_layout(self):
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Save BSM network layout",
            "",
            "RASP BSM network layout (*.bsm-network-layout.json);;JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        if "." not in Path(path).name:
            path += ".bsm-network-layout.json"
        edges = {}
        for key, layout in dict(self.edge_layout).items():
            edges[str(key)] = self._copy_edge_layout(layout)
        for key, layout in dict(self.manual_edge_layout).items():
            edges[str(key)] = self._copy_edge_layout(layout)
        payload = {
            "format": self.LAYOUT_FORMAT,
            "version": self.LAYOUT_VERSION,
            "layout_mode": str(self.layout_mode_combo.currentData() or "auto"),
            "projection": str(self.projection_combo.currentData() or "equirectangular"),
            "controls": {
                "min_mean_per_map": str(self.threshold_edit.text() or ""),
                "circle_edge_percentile": str(self.edge_percentile_edit.text() or ""),
                "edge_width_scale": str(self.width_scale_edit.text() or ""),
                "include_anagenetic": bool(self.include_anagenetic_check.isChecked()),
                "include_founder": bool(self.include_founder_check.isChecked()),
                "show_edge_values": bool(self.show_values_check.isChecked()),
                "show_area_labels": bool(self.show_area_labels_check.isChecked()),
            },
            "network_ref": {
                "format": str((self.current_network or {}).get("format", "") or ""),
                "version": (self.current_network or {}).get("version", ""),
                "nummaps": (self.current_network or {}).get("nummaps", ""),
                "edge_keys": sorted(
                    "%s->%s" % (row.get("source_area", ""), row.get("target_area", ""))
                    for row in list((self.current_network or {}).get("edge_rows", []) or [])
                ),
            },
            "edges": edges,
        }
        try:
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "Save layout failed", str(exc))

    def load_layout(self):
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Load BSM network layout",
            "",
            "RASP BSM network layout (*.bsm-network-layout.json);;JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            fmt = str(payload.get("format", "") or "")
            if fmt and fmt != self.LAYOUT_FORMAT:
                raise ValueError("Unsupported BSM network layout format: %s" % fmt)
            version = int(payload.get("version", 1) or 1)
            if version not in (1, self.LAYOUT_VERSION):
                raise ValueError("Unsupported BSM network layout version: %s" % version)
            edges = dict(payload.get("edges", {}) or {})
        except Exception as exc:
            QMessageBox.critical(self, "Load layout failed", str(exc))
            return
        if int(payload.get("version", 1) or 1) >= 2:
            self._restore_layout_controls(payload)
            self.refresh_network(reset_layout=False)
        copied_edges = {str(key): self._copy_edge_layout(value) for key, value in edges.items()}
        self.edge_layout.update({key: self._copy_edge_layout(value) for key, value in copied_edges.items()})
        self.manual_edge_layout.update({key: self._copy_edge_layout(value) for key, value in copied_edges.items()})
        self.redraw(fit_view=False)

    def _restore_layout_controls(self, payload):
        controls = dict(payload.get("controls", {}) or {})
        widgets = [
            self.layout_mode_combo, self.projection_combo, self.threshold_edit,
            self.edge_percentile_edit, self.width_scale_edit,
            self.include_anagenetic_check, self.include_founder_check,
            self.show_values_check, self.show_area_labels_check,
        ]
        old_states = [widget.blockSignals(True) for widget in widgets]
        try:
            self._set_combo_data(self.layout_mode_combo, payload.get("layout_mode", "auto"))
            self._set_combo_data(self.projection_combo, payload.get("projection", "equirectangular"))
            self.threshold_edit.setText(str(controls.get("min_mean_per_map", self.threshold_edit.text()) or "0"))
            self.edge_percentile_edit.setText(str(controls.get("circle_edge_percentile", self.edge_percentile_edit.text()) or "0"))
            self.width_scale_edit.setText(str(controls.get("edge_width_scale", self.width_scale_edit.text()) or "1"))
            self.include_anagenetic_check.setChecked(bool(controls.get("include_anagenetic", True)))
            self.include_founder_check.setChecked(bool(controls.get("include_founder", True)))
            self.show_values_check.setChecked(bool(controls.get("show_edge_values", False)))
            self.show_area_labels_check.setChecked(bool(controls.get("show_area_labels", False)))
        finally:
            for widget, state in zip(widgets, old_states):
                widget.blockSignals(state)

    def _set_combo_data(self, combo, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def export_png(self):
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export BSM network map PNG",
            "",
            "PNG files (*.png);;All files (*)",
        )
        if not path:
            return
        if "." not in Path(path).name:
            path += ".png"
        rect = self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        if rect.isNull():
            QMessageBox.information(self, "Export PNG", "The map is empty.")
            return
        image = QImage(max(1, int(rect.width())), max(1, int(rect.height())), QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.scene.render(painter, source=rect)
        painter.end()
        if not image.save(path):
            QMessageBox.critical(self, "Export PNG failed", "Could not write PNG file:\n%s" % path)

    def _update_info(self, network, edge_rows, layout_mode):
        area_count = len(self.area_records)
        matrix_text = "yes" if self.range_matrix is not None else "no"
        summary = dict(getattr(self.result, "summary", {}) or {})
        maps = summary.get("nummaps", "")
        self.source_label.setText(
            "Inputs: BSM events=%s stochastic map(s); spatial areas=%d; range matrix=%s; layout=%s; projection=%s."
            % (maps or "unknown", area_count, matrix_text, layout_mode, self._projection_name() if layout_mode == "map" else "n/a")
        )
        lines = [
            "BSM Network Map Editor",
            "",
            "This window consumes upstream data:",
            "  BSM event result: %s" % ("available" if self.result is not None else "missing"),
            "  Spatial project areas: %d" % area_count,
            "  Range matrix for node richness: %s" % matrix_text,
            "  Active layout: %s" % layout_mode,
            "",
            "Visible edges: %d / %d" % (len(edge_rows), len(network.get("edge_rows", []) or [])),
            "Threshold mean events/map: %s" % self._format_number(network.get("min_mean_per_map", "")),
            "Edge percentile filter: %s" % self._format_number(self._edge_filter_percentile()),
            "Edge width scale: %s" % self._format_number(self._edge_width_scale()),
            "Projection: %s" % (self._projection_name() if layout_mode == "map" else "n/a"),
        ]
        lines.extend(["", "Editing:"])
        if layout_mode == "network":
            lines.extend([
                "  Circle network uses automatic igraph-style curves.",
                "  Edit handles enables draggable curve controls for circle edges.",
                "  Edge numbers are draggable if Edge values is enabled.",
            ])
        else:
            lines.extend([
                "  Edit handles enables draggable curve controls for map edges.",
                "  Edge numbers are draggable if Edge values is enabled.",
                "  Circle-network percentile is hidden in map mode.",
            ])
        if layout_mode == "network":
            lines.extend([
                "",
                "Circle network layout:",
                "  Used when no spatial GeoJSON is loaded, or when Layout is set to Circle network.",
                "  This is suitable for Fig. 2/Fig. 3 style schematic exchange networks.",
            ])
        warnings = list(network.get("warnings", []) or [])
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in warnings:
                lines.append("  %s" % warning)
        self.info_text.setPlainText("\n".join(lines))

    def _effective_layout_mode(self, bounds):
        mode = self.layout_mode_combo.currentData() if hasattr(self, "layout_mode_combo") else "auto"
        mode = str(mode or "auto")
        if mode == "auto":
            return "map" if bounds is not None else "network"
        return mode

    def _edge_key(self, row):
        return "%s->%s" % (str(row.get("source_area", "") or ""), str(row.get("target_area", "") or ""))

    def _curve_by_pair(self, edge_rows):
        pair_keys = []
        for row in list(edge_rows or []):
            source = str(row.get("source_area", "") or "")
            target = str(row.get("target_area", "") or "")
            if source and target:
                pair = tuple(sorted([source, target]))
                if pair not in pair_keys:
                    pair_keys.append(pair)
        pair_keys.sort()
        return {pair: 24.0 + (index % 5) * 11.0 for index, pair in enumerate(pair_keys)}

    def _bounds(self, areas, node_rows):
        bounds = None
        for area in areas:
            for lon, lat in self._geometry_points(getattr(area, "geometry", {}) or {}):
                px, py = self._project(lon, lat)
                bounds = self._merge_bounds(bounds, px, py)
        for row in node_rows:
            lon = self._safe_float(row.get("centroid_lon"), None)
            lat = self._safe_float(row.get("centroid_lat"), None)
            if lon is not None and lat is not None:
                px, py = self._project(lon, lat)
                bounds = self._merge_bounds(bounds, px, py)
        if bounds is None:
            return None
        min_x, min_y, max_x, max_y = bounds
        if abs(max_x - min_x) < 1e-9:
            min_x -= 0.5
            max_x += 0.5
        if abs(max_y - min_y) < 1e-9:
            min_y -= 0.5
            max_y += 0.5
        return min_x, min_y, max_x, max_y

    def _transform(self, bounds):
        min_x, min_y, max_x, max_y = bounds
        width = max(1e-9, float(max_x) - float(min_x))
        height = max(1e-9, float(max_y) - float(min_y))
        scale = min(1080.0 / width, 640.0 / height)
        margin = 28.0

        def transform(lon, lat):
            px, py = self._project(lon, lat)
            return (
                margin + (float(px) - float(min_x)) * scale,
                margin + (float(max_y) - float(py)) * scale,
            )

        return transform

    def _projection_key(self):
        if hasattr(self, "projection_combo"):
            value = self.projection_combo.currentData()
            if value:
                return str(value)
        return "equirectangular"

    def _projection_name(self):
        if hasattr(self, "projection_combo"):
            text = self.projection_combo.currentText()
            if text:
                return str(text)
        return "Equirectangular"

    def _project(self, lon, lat):
        key = self._projection_key()
        lon = float(lon)
        lat = max(-89.9999, min(89.9999, float(lat)))
        lam = math.radians(lon)
        phi = math.radians(lat)
        if key == "mercator":
            merc_lat = max(-85.05112878, min(85.05112878, lat))
            merc_phi = math.radians(merc_lat)
            return lon, math.degrees(math.log(math.tan(math.pi * 0.25 + merc_phi * 0.5)))
        if key == "robinson":
            return self._project_robinson(lam, phi)
        if key == "equal_earth":
            return self._project_equal_earth(lam, phi)
        if key == "mollweide":
            return self._project_mollweide(lam, phi)
        if key == "winkel_tripel":
            return self._project_winkel_tripel(lam, phi)
        return lon, lat

    def _project_robinson(self, lam, phi):
        x_table = [
            1.0000, 0.9986, 0.9954, 0.9900, 0.9822, 0.9730, 0.9600,
            0.9427, 0.9216, 0.8962, 0.8679, 0.8350, 0.7986, 0.7597,
            0.7186, 0.6732, 0.6213, 0.5722, 0.5322,
        ]
        y_table = [
            0.0000, 0.0620, 0.1240, 0.1860, 0.2480, 0.3100, 0.3720,
            0.4340, 0.4958, 0.5571, 0.6176, 0.6769, 0.7346, 0.7903,
            0.8435, 0.8936, 0.9394, 0.9761, 1.0000,
        ]
        degrees = abs(math.degrees(phi))
        index = min(17, int(degrees // 5.0))
        fraction = (degrees - float(index) * 5.0) / 5.0
        x_coef = x_table[index] * (1.0 - fraction) + x_table[index + 1] * fraction
        y_coef = y_table[index] * (1.0 - fraction) + y_table[index + 1] * fraction
        return 0.8487 * lam * x_coef, 1.3523 * y_coef * (1.0 if phi >= 0 else -1.0)

    def _project_equal_earth(self, lam, phi):
        a1 = 1.340264
        a2 = -0.081106
        a3 = 0.000893
        a4 = 0.003796
        theta = math.asin(math.sqrt(3.0) * math.sin(phi) / 2.0)
        theta2 = theta * theta
        theta6 = theta2 * theta2 * theta2
        denominator = 3.0 * (
            9.0 * a4 * theta6 * theta2
            + 7.0 * a3 * theta6
            + 3.0 * a2 * theta2
            + a1
        )
        if abs(denominator) < 1e-12:
            denominator = 1e-12
        x = 2.0 * math.sqrt(3.0) * lam * math.cos(theta) / denominator
        y = a4 * theta6 * theta2 * theta + a3 * theta6 * theta + a2 * theta2 * theta + a1 * theta
        return x, y

    def _project_mollweide(self, lam, phi):
        if abs(abs(phi) - math.pi * 0.5) < 1e-10:
            theta = math.copysign(math.pi * 0.5, phi)
        else:
            theta = phi
            target = math.pi * math.sin(phi)
            for _index in range(12):
                value = 2.0 * theta + math.sin(2.0 * theta) - target
                deriv = 2.0 + 2.0 * math.cos(2.0 * theta)
                if abs(deriv) < 1e-12:
                    break
                delta = value / deriv
                theta -= delta
                if abs(delta) < 1e-12:
                    break
        x = 2.0 * math.sqrt(2.0) * lam * math.cos(theta) / math.pi
        y = math.sqrt(2.0) * math.sin(theta)
        return x, y

    def _project_winkel_tripel(self, lam, phi):
        standard_parallel = math.acos(2.0 / math.pi)
        half_lam = lam * 0.5
        cos_phi = math.cos(phi)
        alpha = math.acos(max(-1.0, min(1.0, cos_phi * math.cos(half_lam))))
        if abs(alpha) < 1e-12:
            sinc = 1.0
        else:
            sinc = math.sin(alpha) / alpha
        if abs(sinc) < 1e-12:
            sinc = 1e-12
        aitoff_x = 2.0 * cos_phi * math.sin(half_lam) / sinc
        aitoff_y = math.sin(phi) / sinc
        x = 0.5 * (aitoff_x + lam * math.cos(standard_parallel))
        y = 0.5 * (aitoff_y + phi)
        return x, y

    def _path_from_geometry(self, geometry, transform):
        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)
        geometry_type = str(geometry.get("type", "") or "")
        coordinates = geometry.get("coordinates") or []
        polygons = [coordinates] if geometry_type == "Polygon" else list(coordinates or []) if geometry_type == "MultiPolygon" else []
        for polygon in polygons:
            for ring in list(polygon or []):
                points = list(ring or [])
                if len(points) > 1800:
                    stride = max(1, int(round(float(len(points)) / 1800.0)))
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

    def _geometry_points(self, geometry):
        geometry_type = str(geometry.get("type", "") or "")
        coordinates = geometry.get("coordinates") or []
        polygons = [coordinates] if geometry_type == "Polygon" else list(coordinates or []) if geometry_type == "MultiPolygon" else []
        for polygon in polygons:
            for ring in list(polygon or []):
                for point in list(ring or []):
                    if len(point) >= 2:
                        yield float(point[0]), float(point[1])

    def _color(self, value, index):
        color = QColor(str(value or ""))
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

    def _safe_float(self, value, default):
        try:
            return float(str(value).strip())
        except Exception:
            return default

    def _format_number(self, value):
        try:
            number = float(value)
        except Exception:
            return str(value)
        if abs(number - round(number)) < 1e-9:
            return str(int(round(number)))
        return ("%.6f" % number).rstrip("0").rstrip(".")

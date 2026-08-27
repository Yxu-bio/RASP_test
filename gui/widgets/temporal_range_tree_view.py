from PyQt5.QtCore import QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen
from PyQt5.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QSizePolicy,
    QStyle,
    QStyleOptionGraphicsItem,
    QVBoxLayout,
    QWidget,
)


def _cosmetic_pen(color, width=1.0, style=Qt.SolidLine):
    pen = QPen(color, float(width), style, Qt.RoundCap, Qt.RoundJoin)
    pen.setCosmetic(True)
    return pen


class _TemporalTreeGraphicsView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setBackgroundBrush(QBrush(QColor("#fbfcfd")))

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)

    def fit_to_tree(self):
        scene = self.scene()
        if scene is None:
            return
        rect = scene.itemsBoundingRect()
        if not rect.isNull():
            self.fitInView(rect.adjusted(-20, -20, 20, 20), Qt.KeepAspectRatio)


class _BranchLineItem(QGraphicsLineItem):
    def __init__(self, branch_id, owner, *args):
        super().__init__(*args)
        self.branch_id = str(branch_id or "")
        self.owner = owner
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setData(0, self.branch_id)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(max(12.0, float(self.pen().widthF()) + 8.0))
        return stroker.createStroke(super().shape())

    def paint(self, painter, option, widget=None):
        clean_option = QStyleOptionGraphicsItem(option)
        clean_option.state &= ~QStyle.State_Selected
        clean_option.state &= ~QStyle.State_HasFocus
        super().paint(painter, clean_option, widget)

    def hoverEnterEvent(self, event):
        self.owner.branch_hovered.emit(self.branch_id)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.owner.branch_hover_cleared.emit()
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.owner.branch_zoom_requested.emit(self.branch_id)
        event.accept()


class TemporalRangeTreeView(QWidget):
    LARGE_TREE_THRESHOLD = 300

    branch_selected = pyqtSignal(str)
    branch_hovered = pyqtSignal(str)
    branch_hover_cleared = pyqtSignal()
    branch_zoom_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline = None
        self.current_frame = None
        self._branch_items = {}
        self._branch_positions = {}
        self._branch_style_cache = {}
        self._connector_positions = {}
        self._connector_overlay_items = {}
        self._cursor_item = None
        self._cursor_label = None
        self._selection_marker = None
        self._selected_branch_id = ""
        self._hovered_group_id = ""
        self._updating_selection = False
        self._root_age = 0.0
        self._plot_left = 48.0
        self._plot_width = 900.0
        self._plot_top = 20.0
        self._plot_bottom = 520.0
        self._leaf_count = 0
        self._tree_rect = QRectF()

        self.scene = QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.view = _TemporalTreeGraphicsView(self)
        self.view.setScene(self.scene)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

    def set_timeline(self, timeline):
        self.timeline = timeline
        self._selected_branch_id = ""
        self._hovered_group_id = ""
        self._build_scene()

    def set_frame(self, frame):
        self.current_frame = frame
        if frame is None:
            return
        self._move_cursor(float(frame.time))
        active = set(dict(frame.active_branch_probabilities or {}).keys())
        focused = set(frame.focused_branch_ids or [])
        group_ids = dict(frame.branch_group_ids or {})
        group_colors = dict(frame.group_colors or {})
        visual_styles = {}
        for branch_id, item in self._branch_items.items():
            color, width, alpha, z_value = self._branch_visual_style(
                branch_id,
                active,
                focused,
                group_ids,
                group_colors,
            )
            visual_styles[branch_id] = (color, width, alpha, z_value)
            style_key = (color.name(), int(alpha), round(float(width), 3), int(z_value))
            if self._branch_style_cache.get(branch_id) != style_key:
                item.setPen(_cosmetic_pen(color, width))
                item.setZValue(z_value)
                self._branch_style_cache[branch_id] = style_key
        self._update_connector_overlays(visual_styles, group_ids)
        self._update_selection_marker()

    def _branch_visual_style(self, branch_id, active, focused, group_ids, group_colors):
        is_focused = branch_id in focused
        is_active = branch_id in active
        group_id = str(group_ids.get(branch_id, "") or "")
        color = QColor(group_colors.get(group_id, "#6f7b83"))
        if not color.isValid():
            color = QColor("#6f7b83")
        width = 0.85
        alpha = 78
        if is_focused:
            width = 1.25
            alpha = 150
        if is_focused and is_active:
            width = 2.5 if self.is_large_tree() else 3.2
            alpha = 245
        if self._hovered_group_id and group_id != self._hovered_group_id:
            alpha = min(alpha, 30)
        if branch_id == self._selected_branch_id:
            width += 1.8
            alpha = 255
        color.setAlpha(alpha)
        z_value = 14 if branch_id == self._selected_branch_id else 10 if is_active else 4
        return color, width, alpha, z_value

    def _update_connector_overlays(self, visual_styles, group_ids):
        for item in self._connector_overlay_items.values():
            item.setVisible(False)

        paths = {}
        for branch_id, style in visual_styles.items():
            if not str(group_ids.get(branch_id, "") or ""):
                continue
            position = self._connector_positions.get(branch_id)
            if position is None:
                continue
            x_value, parent_y, child_y = position
            if abs(float(parent_y) - float(child_y)) < 1.0e-9:
                continue
            color, width, alpha, z_value = style
            key = (color.name(), round(float(width), 3), int(alpha), int(z_value))
            path = paths.setdefault(key, QPainterPath())
            path.moveTo(float(x_value), float(parent_y))
            path.lineTo(float(x_value), float(child_y))

        for key, path in paths.items():
            color_name, width, alpha, z_value = key
            item = self._connector_overlay_items.get(key)
            if item is None:
                item = QGraphicsPathItem()
                self.scene.addItem(item)
                self._connector_overlay_items[key] = item
            color = QColor(color_name)
            color.setAlpha(alpha)
            item.setPath(path)
            item.setPen(_cosmetic_pen(color, width))
            item.setZValue(max(2, z_value - 1))
            item.setVisible(True)

    def select_branch(self, branch_id):
        branch_id = str(branch_id or "")
        self._selected_branch_id = branch_id
        self._updating_selection = True
        try:
            self.scene.clearSelection()
            item = self._branch_items.get(branch_id)
            if item is not None:
                item.setSelected(True)
        finally:
            self._updating_selection = False
        if self.current_frame is not None:
            self.set_frame(self.current_frame)

    def set_hovered_group(self, group_id):
        group_id = str(group_id or "")
        if group_id == self._hovered_group_id:
            return
        self._hovered_group_id = group_id
        if self.current_frame is not None:
            self.set_frame(self.current_frame)

    def fit_to_tree(self):
        if self.is_large_tree():
            self._fit_rect_width(self._tree_rect, self._tree_rect.center().y())
        else:
            self.view.fit_to_tree()

    def fit_all(self):
        self.view.fit_to_tree()

    def is_large_tree(self):
        return self._leaf_count >= self.LARGE_TREE_THRESHOLD

    def _fit_rect_width(self, rect, center_y=None):
        if rect is None or rect.isNull():
            return
        viewport_width = max(1.0, float(self.view.viewport().width()) - 28.0)
        scale = viewport_width / max(1.0, float(rect.width()))
        scale = max(0.05, min(8.0, scale))
        self.view.resetTransform()
        self.view.scale(scale, scale)
        if center_y is None:
            center_y = rect.center().y()
        self.view.centerOn(rect.center().x(), float(center_y))

    def zoom_to_branch(self, branch_id):
        branch_id = str(branch_id or "")
        if not branch_id or self.timeline is None:
            self.fit_to_tree()
            return
        children = dict(self.timeline.metadata.get("branch_children", {}) or {})
        branch_ids = []
        stack = [branch_id]
        while stack:
            current = stack.pop()
            if current in branch_ids:
                continue
            branch_ids.append(current)
            stack.extend(reversed(list(children.get(current, []) or [])))
        rect = QRectF()
        has_rect = False
        for current_id in branch_ids:
            item = self._branch_items.get(current_id)
            if item is None:
                continue
            item_rect = item.sceneBoundingRect()
            rect = item_rect if not has_rect else rect.united(item_rect)
            has_rect = True
        if has_rect and not rect.isNull():
            padding_x = max(28.0, rect.width() * 0.08)
            padding_y = max(24.0, rect.height() * 0.08)
            target = rect.adjusted(-padding_x, -padding_y, padding_x + 120.0, padding_y)
            if len(branch_ids) >= self.LARGE_TREE_THRESHOLD:
                selected_position = self._branch_positions.get(branch_id)
                center_y = selected_position[3] if selected_position is not None else target.center().y()
                self._fit_rect_width(target, center_y)
            else:
                self.view.fitInView(target, Qt.KeepAspectRatio)

    def _build_scene(self):
        self.scene.clear()
        self._branch_items = {}
        self._branch_positions = {}
        self._branch_style_cache = {}
        self._connector_positions = {}
        self._connector_overlay_items = {}
        self._cursor_item = None
        self._cursor_label = None
        self._selection_marker = None
        if self.timeline is None:
            return

        tree = self.timeline.reference_tree
        leaves = list(tree.iter_leaves())
        leaf_count = max(1, len(leaves))
        self._leaf_count = leaf_count
        if leaf_count <= 60:
            spacing = 28.0
        elif leaf_count <= 300:
            spacing = max(4.0, min(18.0, 1200.0 / float(leaf_count)))
        else:
            spacing = 3.0
        self._plot_top = 34.0
        self._plot_bottom = self._plot_top + max(220.0, spacing * max(1, leaf_count - 1))
        self._root_age = max(0.0, float(self.timeline.root_age))
        self._plot_left = 58.0
        self._plot_width = 1040.0
        self._tree_rect = QRectF(
            self._plot_left,
            self._plot_top,
            self._plot_width,
            self._plot_bottom - self._plot_top,
        )

        self._draw_time_background()

        y_by_node = {}
        for index, leaf in enumerate(leaves):
            y_by_node[leaf] = self._plot_top + (index * spacing)
        for node in tree.traverse("postorder"):
            if node in y_by_node:
                continue
            children = list(getattr(node, "children", []) or [])
            child_y = [y_by_node[child] for child in children if child in y_by_node]
            y_by_node[node] = sum(child_y) / float(len(child_y)) if child_y else self._plot_top

        key_by_node = dict((node, self._clade_key(node)) for node in tree.traverse("preorder"))
        x_by_node = {}
        for node, key in key_by_node.items():
            age = float(self.timeline.node_ages.get(key, 0.0))
            x_by_node[node] = self._x_for_time(age)

        connector_path = QPainterPath()
        for node in tree.traverse("preorder"):
            children = list(getattr(node, "children", []) or [])
            if children:
                ys = [y_by_node[child] for child in children]
                connector_path.moveTo(x_by_node[node], min(ys))
                connector_path.lineTo(x_by_node[node], max(ys))
        connector = QGraphicsPathItem(connector_path)
        connector.setPen(_cosmetic_pen(QColor(150, 162, 172, 150), 0.85))
        connector.setZValue(1)
        self.scene.addItem(connector)

        branch_by_child_key = dict((branch.child_clade_key, branch) for branch in self.timeline.branches)
        for node in tree.traverse("preorder"):
            parent = getattr(node, "up", None)
            if parent is None:
                continue
            branch = branch_by_child_key.get(key_by_node[node])
            if branch is None:
                continue
            item = _BranchLineItem(
                branch.branch_id,
                self,
                x_by_node[parent],
                y_by_node[node],
                x_by_node[node],
                y_by_node[node],
            )
            item.setToolTip(self._branch_tooltip(branch))
            item.setPen(_cosmetic_pen(QColor(137, 150, 161, 95), 0.85))
            self.scene.addItem(item)
            self._branch_items[branch.branch_id] = item
            self._branch_positions[branch.branch_id] = (x_by_node[parent], y_by_node[node], x_by_node[node], y_by_node[node])
            self._connector_positions[branch.branch_id] = (
                x_by_node[parent],
                y_by_node[parent],
                y_by_node[node],
            )

        if not self.is_large_tree():
            node_radius = 1.8
            for node in tree.traverse("preorder"):
                if getattr(node, "is_leaf", lambda: False)():
                    continue
                x = x_by_node[node]
                y = y_by_node[node]
                dot = QGraphicsEllipseItem(x - node_radius, y - node_radius, node_radius * 2.0, node_radius * 2.0)
                dot.setBrush(QBrush(QColor("#ffffff")))
                dot.setPen(_cosmetic_pen(QColor("#66727c"), 1.0))
                dot.setZValue(12)
                self.scene.addItem(dot)
        if leaf_count <= 80:
            label_font = QFont("Segoe UI", 8)
            for leaf in leaves:
                label = QGraphicsSimpleTextItem(str(getattr(leaf, "name", "") or ""))
                label.setBrush(QBrush(QColor(42, 48, 55)))
                label.setFont(label_font)
                label.setPos(x_by_node[leaf] + 6.0, y_by_node[leaf] - 7.0)
                label.setZValue(11)
                self.scene.addItem(label)

        self._draw_time_axis()
        self._cursor_item = self.scene.addLine(
            self._plot_left,
            self._plot_top - 14.0,
            self._plot_left,
            self._plot_bottom + 10.0,
            _cosmetic_pen(QColor(196, 63, 70, 210), 1.25, Qt.DashLine),
        )
        self._cursor_item.setZValue(30)
        self._cursor_label = QGraphicsSimpleTextItem()
        self._cursor_label.setBrush(QBrush(QColor("#a92f3a")))
        self._cursor_label.setFont(QFont("Segoe UI", 8))
        self._cursor_label.setZValue(31)
        self.scene.addItem(self._cursor_label)
        self._selection_marker = QGraphicsEllipseItem()
        self._selection_marker.setBrush(QBrush(Qt.NoBrush))
        self._selection_marker.setPen(_cosmetic_pen(QColor(198, 54, 61), 2.0))
        self._selection_marker.setZValue(40)
        self._selection_marker.setVisible(False)
        self.scene.addItem(self._selection_marker)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-25, -25, 180, 35))
        self.fit_to_tree()

    def _draw_time_background(self):
        tick_count = 5
        height = self._plot_bottom - self._plot_top
        for index in range(tick_count):
            x0 = self._plot_left + (index / float(tick_count)) * self._plot_width
            x1 = self._plot_left + ((index + 1) / float(tick_count)) * self._plot_width
            if index % 2 == 0:
                band = self.scene.addRect(
                    x0,
                    self._plot_top,
                    x1 - x0,
                    height,
                    QPen(Qt.NoPen),
                    QBrush(QColor("#f5f8fa")),
                )
                band.setZValue(-10)
        for index in range(tick_count + 1):
            x = self._plot_left + (index / float(tick_count)) * self._plot_width
            grid = self.scene.addLine(
                x,
                self._plot_top,
                x,
                self._plot_bottom,
                _cosmetic_pen(QColor(188, 198, 206, 120), 0.8, Qt.DotLine),
            )
            grid.setZValue(-8)

    def _draw_time_axis(self):
        axis_y = self._plot_bottom + 22.0
        self.scene.addLine(
            self._plot_left,
            axis_y,
            self._plot_left + self._plot_width,
            axis_y,
            _cosmetic_pen(QColor(92, 101, 108), 0.9),
        )
        tick_count = 5
        for index in range(tick_count + 1):
            fraction = index / float(tick_count)
            x = self._plot_left + fraction * self._plot_width
            age = self._root_age * (1.0 - fraction)
            self.scene.addLine(x, axis_y, x, axis_y + 5.0, _cosmetic_pen(QColor(92, 101, 108), 0.8))
            label = QGraphicsSimpleTextItem("%.4g" % age)
            label.setBrush(QBrush(QColor(72, 80, 87)))
            label.setPos(x - label.boundingRect().width() / 2.0, axis_y + 5.0)
            self.scene.addItem(label)
        title = QGraphicsSimpleTextItem("Time before present")
        title.setBrush(QBrush(QColor(72, 80, 87)))
        title.setPos(self._plot_left + self._plot_width / 2.0 - title.boundingRect().width() / 2.0, axis_y + 23.0)
        self.scene.addItem(title)

    def _move_cursor(self, time_value):
        if self._cursor_item is None:
            return
        x = self._x_for_time(time_value)
        self._cursor_item.setLine(x, self._plot_top - 14.0, x, self._plot_bottom + 10.0)
        if self._cursor_label is not None:
            self._cursor_label.setText("t = %.4g" % float(time_value))
            label_width = self._cursor_label.boundingRect().width()
            self._cursor_label.setPos(x - label_width / 2.0, self._plot_top - 30.0)

    def _x_for_time(self, age):
        if self._root_age <= 0.0:
            return self._plot_left
        fraction = (self._root_age - float(age)) / self._root_age
        return self._plot_left + (max(0.0, min(1.0, fraction)) * self._plot_width)

    def _update_selection_marker(self):
        if self._selection_marker is None:
            return
        position = self._branch_positions.get(self._selected_branch_id)
        if position is None:
            self._selection_marker.setVisible(False)
            return
        radius = 7.0
        x = float(position[2])
        y = float(position[3])
        self._selection_marker.setRect(x - radius, y - radius, radius * 2.0, radius * 2.0)
        self._selection_marker.setVisible(True)

    def _on_selection_changed(self):
        if self._updating_selection:
            return
        selected = self.scene.selectedItems()
        branch_id = ""
        for item in selected:
            value = item.data(0)
            if value:
                branch_id = str(value)
                break
        self._selected_branch_id = branch_id
        if self.current_frame is not None:
            self.set_frame(self.current_frame)
        self.branch_selected.emit(branch_id)

    def _branch_tooltip(self, branch):
        tip_count = int(dict(branch.metadata or {}).get("descendant_tip_count", 0) or 0)
        return (
            "%s -> %s\nTime %.6g to %.6g\n%d descendant tips\n%s\n"
            "Click: focus clade. Double-click: zoom to clade."
        ) % (
            branch.parent_node_id or "parent",
            branch.child_node_id or "child",
            float(branch.older_time),
            float(branch.younger_time),
            tip_count,
            str(branch.interpolation_mode),
        )

    def _clade_key(self, node):
        if getattr(node, "is_leaf", lambda: False)():
            return str(getattr(node, "name", "") or "")
        return "|".join(sorted(str(name) for name in node.get_leaf_names()))

from PyQt5.QtCore import QPointF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QPainter, QPen
from PyQt5.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _TemporalTreeGraphicsView(QGraphicsView):
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

    def fit_to_tree(self):
        scene = self.scene()
        if scene is None:
            return
        rect = scene.itemsBoundingRect()
        if not rect.isNull():
            self.fitInView(rect.adjusted(-20, -20, 20, 20), Qt.KeepAspectRatio)


class TemporalRangeTreeView(QWidget):
    branch_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline = None
        self.current_frame = None
        self._branch_items = {}
        self._branch_midpoint_probabilities = {}
        self._cursor_item = None
        self._selected_branch_id = ""
        self._updating_selection = False
        self._root_age = 0.0
        self._plot_left = 30.0
        self._plot_width = 900.0
        self._plot_top = 20.0
        self._plot_bottom = 520.0

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
        self._build_scene()

    def set_frame(self, frame):
        self.current_frame = frame
        if frame is None:
            return
        self._move_cursor(float(frame.time))
        active = dict(frame.active_branch_probabilities or {})
        for branch_id, item in self._branch_items.items():
            probabilities = active.get(branch_id)
            is_active = probabilities is not None
            if probabilities is None:
                probabilities = self._branch_midpoint_probabilities.get(branch_id, {})
            color = self._probability_color(probabilities)
            width = 3.0 if is_active else 1.35
            alpha = 245 if is_active else 105
            color.setAlpha(alpha)
            if branch_id == self._selected_branch_id:
                item.setPen(QPen(QColor(196, 45, 50), 4.2, Qt.SolidLine, Qt.RoundCap))
                item.setZValue(20)
            else:
                item.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap))
                item.setZValue(8 if is_active else 3)

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

    def fit_to_tree(self):
        self.view.fit_to_tree()

    def _build_scene(self):
        self.scene.clear()
        self._branch_items = {}
        self._branch_midpoint_probabilities = {}
        self._cursor_item = None
        if self.timeline is None:
            return

        tree = self.timeline.reference_tree
        leaves = list(tree.iter_leaves())
        leaf_count = max(1, len(leaves))
        spacing = max(2.5, min(18.0, 900.0 / float(leaf_count)))
        self._plot_top = 24.0
        self._plot_bottom = self._plot_top + max(220.0, spacing * max(1, leaf_count - 1))
        self._root_age = max(0.0, float(self.timeline.root_age))
        self._plot_left = 28.0
        self._plot_width = 980.0

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

        for node in tree.traverse("preorder"):
            children = list(getattr(node, "children", []) or [])
            if children:
                ys = [y_by_node[child] for child in children]
                connector = self.scene.addLine(
                    x_by_node[node], min(ys), x_by_node[node], max(ys),
                    QPen(QColor(174, 181, 189), 0.9),
                )
                connector.setZValue(1)

        branch_by_child_key = dict((branch.child_clade_key, branch) for branch in self.timeline.branches)
        for node in tree.traverse("preorder"):
            parent = getattr(node, "up", None)
            if parent is None:
                continue
            child_key = key_by_node[node]
            branch = branch_by_child_key.get(child_key)
            if branch is None:
                continue
            item = QGraphicsLineItem(x_by_node[parent], y_by_node[node], x_by_node[node], y_by_node[node])
            item.setFlag(QGraphicsItem.ItemIsSelectable, True)
            item.setData(0, branch.branch_id)
            item.setToolTip(self._branch_tooltip(branch))
            self.scene.addItem(item)
            self._branch_items[branch.branch_id] = item
            midpoint = (float(branch.older_time) + float(branch.younger_time)) / 2.0
            self._branch_midpoint_probabilities[branch.branch_id] = self._interpolate(branch, midpoint)

        node_radius = 2.2 if leaf_count > 300 else 3.2
        for node in tree.traverse("preorder"):
            x = x_by_node[node]
            y = y_by_node[node]
            dot = QGraphicsEllipseItem(x - node_radius, y - node_radius, node_radius * 2.0, node_radius * 2.0)
            dot.setBrush(QBrush(QColor(73, 83, 94)))
            dot.setPen(QPen(Qt.NoPen))
            dot.setZValue(10)
            self.scene.addItem(dot)
        if leaf_count <= 160:
            for leaf in leaves:
                label = QGraphicsSimpleTextItem(str(getattr(leaf, "name", "") or ""))
                label.setBrush(QBrush(QColor(42, 48, 55)))
                label.setPos(x_by_node[leaf] + 6.0, y_by_node[leaf] - 7.0)
                label.setZValue(11)
                self.scene.addItem(label)

        self._cursor_item = self.scene.addLine(
            self._plot_left,
            self._plot_top - 14.0,
            self._plot_left,
            self._plot_bottom + 14.0,
            QPen(QColor(204, 67, 71), 1.4, Qt.DashLine),
        )
        self._cursor_item.setZValue(30)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-25, -25, 180, 25))
        self.fit_to_tree()

    def _move_cursor(self, time_value):
        if self._cursor_item is None:
            return
        x = self._x_for_time(time_value)
        self._cursor_item.setLine(x, self._plot_top - 14.0, x, self._plot_bottom + 14.0)

    def _x_for_time(self, age):
        if self._root_age <= 0.0:
            return self._plot_left
        fraction = (self._root_age - float(age)) / self._root_age
        return self._plot_left + (max(0.0, min(1.0, fraction)) * self._plot_width)

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
        if branch_id:
            self.branch_selected.emit(branch_id)

    def _probability_color(self, probabilities):
        if not probabilities:
            return QColor(150, 157, 165)
        state, _value = max(probabilities.items(), key=lambda item: float(item[1]))
        raw = str(dict(getattr(self.timeline, "state_colors", {}) or {}).get(state, "") or "")
        color = QColor(raw)
        return color if color.isValid() else QColor(47, 126, 146)

    def _interpolate(self, branch, time_value):
        older = float(branch.older_time)
        younger = float(branch.younger_time)
        span = older - younger
        fraction = 0.0 if span <= 0.0 else (older - float(time_value)) / span
        fraction = max(0.0, min(1.0, fraction))
        values = {}
        labels = set(branch.older_probabilities) | set(branch.younger_probabilities)
        for label in labels:
            values[label] = (
                float(branch.older_probabilities.get(label, 0.0)) * (1.0 - fraction)
                + float(branch.younger_probabilities.get(label, 0.0)) * fraction
            )
        return values

    def _branch_tooltip(self, branch):
        return "%s -> %s\nTime %.6g to %.6g\n%s" % (
            branch.parent_node_id or "parent",
            branch.child_node_id or "child",
            float(branch.older_time),
            float(branch.younger_time),
            str(branch.interpolation_mode),
        )

    def _clade_key(self, node):
        if getattr(node, "is_leaf", lambda: False)():
            return str(getattr(node, "name", "") or "")
        return "|".join(sorted(str(name) for name in node.get_leaf_names()))

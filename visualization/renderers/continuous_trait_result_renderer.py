from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget

from infrastructure.tree.ete_adapter import ETEAdapter
from visualization.renderers.base_result_renderer import BaseResultRenderer


class ContinuousTraitResultRenderer(BaseResultRenderer):
    def __init__(self):
        self.adapter = ETEAdapter()
        self._source_tree = None
        self._display_tree = None
        self._result = None
        self._segment_count = 10

    def set_tree(self, tree) -> None:
        self._source_tree = tree
        self._sync_tree()

    def set_result(self, result) -> None:
        self._result = result
        self._sync_tree()

    def apply_leaf_states(self, leaf_state_map: dict, state_colors: dict) -> None:
        # Continuous rendering uses numeric tip values from the result.
        return

    def build_view(self) -> QWidget:
        return self.adapter.build_embedded_view()

    def bind_node_click_callback(self, callback) -> None:
        self.adapter.bind_click_callback(callback)

    def set_show_leaf_name(self, flag: bool) -> None:
        self.adapter.set_show_leaf_name(flag)

    def set_show_branch_length(self, flag: bool) -> None:
        self.adapter.set_show_branch_length(flag)

    def set_show_branch_support(self, flag: bool) -> None:
        self.adapter.set_show_branch_support(flag)

    def set_circular_enabled(self, enabled: bool) -> None:
        self.adapter.set_circular_enabled(enabled)

    def set_circular_arc(self, arc_start: int, arc_span: int) -> None:
        self.adapter.set_circular_arc(arc_start, arc_span)

    def zoom_in(self) -> None:
        if self.adapter._view is not None:
            self.adapter._view.scale(1.2, 1.2)

    def zoom_out(self) -> None:
        if self.adapter._view is not None:
            self.adapter._view.scale(1 / 1.2, 1 / 1.2)

    def fit_to_view(self) -> None:
        if self.adapter._view is not None and self.adapter._view.scene():
            self.adapter._view.resetTransform()
            self.adapter._view.fitInView(
                self.adapter._view.scene().sceneRect(),
                Qt.KeepAspectRatio,
            )

    def export_tree_png(self, file_path: str) -> None:
        self.adapter.export_png(file_path)

    def export_tree_svg(self, file_path: str) -> None:
        self.adapter.export_svg(file_path)

    def export_tree_pdf(self, file_path: str) -> None:
        self.adapter.export_pdf(file_path)

    def select_node_by_clade_key(self, clade_key: str):
        return self.adapter.select_node_by_clade_key(clade_key)

    def _sync_tree(self) -> None:
        if self._source_tree is None:
            return
        if self._result is None:
            self.adapter.set_tree(self._source_tree)
            return

        display_tree = self._copy_tree(self._source_tree)
        self._insert_gradient_segments(display_tree, self._result, self._segment_count)
        self._display_tree = display_tree
        self.adapter.set_tree(display_tree)
        self.adapter.apply_continuous_result(self._result)

    def _copy_tree(self, tree):
        try:
            return tree.copy(method="deepcopy")
        except Exception:
            import copy
            return copy.deepcopy(tree)

    def _insert_gradient_segments(self, tree, result, segment_count: int) -> None:
        try:
            from ete3 import TreeNode
        except Exception:
            return

        edges = []
        for parent in list(tree.traverse("preorder")):
            for child in list(getattr(parent, "children", []) or []):
                edges.append((parent, child))

        for parent, child in edges:
            parent_value = self._node_value(parent, result)
            child_value = self._node_value(child, result)
            if parent_value is None or child_value is None:
                continue
            original_length = float(getattr(child, "dist", 0.0) or 0.0)
            if segment_count <= 1:
                continue

            try:
                parent.remove_child(child)
            except Exception:
                continue

            prev = parent
            segment_length = original_length / float(segment_count)
            for index in range(1, segment_count):
                t = index / float(segment_count)
                value = float(parent_value) + (float(child_value) - float(parent_value)) * t
                dummy = TreeNode()
                dummy.name = ""
                dummy.dist = segment_length
                dummy.add_features(
                    _rasp_dummy=True,
                    _rasp_continuous_value=value,
                )
                prev.add_child(dummy)
                prev = dummy
            child.dist = segment_length
            prev.add_child(child)

    def _node_value(self, node, result):
        if hasattr(node, "_rasp_continuous_value"):
            try:
                return float(getattr(node, "_rasp_continuous_value"))
            except Exception:
                return None
        try:
            if node.is_leaf():
                name = str(getattr(node, "name", "") or "").strip()
                values = dict(getattr(result, "plot_tip_values", {}) or {}) or dict(getattr(result, "tip_values", {}) or {})
                return float(values[name]) if name in values else None
        except Exception:
            return None
        clade_key = self._clade_key(node)
        plot_node_values = dict(getattr(result, "plot_node_values", {}) or {})
        if clade_key in plot_node_values:
            try:
                return float(plot_node_values[clade_key])
            except Exception:
                return None
        node_result = result.get_node_result(clade_key)
        if node_result is None:
            return None
        try:
            return float(getattr(node_result, "mean", 0.0) or 0.0)
        except Exception:
            return None

    def _clade_key(self, node) -> str:
        try:
            names = [
                str(leaf.name).strip()
                for leaf in node.iter_leaves()
                if str(getattr(leaf, "name", "")).strip()
            ]
        except Exception:
            names = []
        return "|".join(sorted(names))

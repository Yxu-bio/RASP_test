from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget

from infrastructure.tree.ete_adapter import ETEAdapter
from visualization.renderers.base_result_renderer import BaseResultRenderer


class DivaResultRenderer(BaseResultRenderer):
    def __init__(self):
        self.adapter = ETEAdapter()
        self._diva_result = None
        self._tree = None
        self._leaf_state_map = {}
        self._state_colors = {}

    def set_tree(self, tree):
        self._tree = tree
        self.adapter.set_tree(tree)

        # 如果之前已经设置过叶节点状态或DIVA结果，这里重新应用一次
        if self._leaf_state_map or self._state_colors:
            self.adapter.apply_leaf_states(self._leaf_state_map, self._state_colors)
        if self._diva_result is not None:
            self.adapter.apply_diva_result(self._diva_result)

    def set_result(self, result):
        self._diva_result = result
        self.adapter.apply_diva_result(result)

    def apply_leaf_states(self, leaf_state_map: dict, state_colors: dict):
        self._leaf_state_map = dict(leaf_state_map or {})
        self._state_colors = dict(state_colors or {})
        self.adapter.apply_leaf_states(self._leaf_state_map, self._state_colors)

    def build_view(self) -> QWidget:
        return self.adapter.build_embedded_view()

    def bind_node_click_callback(self, callback):
        self.adapter.bind_click_callback(callback)

    def set_show_leaf_name(self, flag: bool):
        self.adapter.set_show_leaf_name(flag)

    def set_show_branch_length(self, flag: bool):
        self.adapter.set_show_branch_length(flag)

    def set_show_branch_support(self, flag: bool):
        self.adapter.set_show_branch_support(flag)

    def set_circular_enabled(self, enabled: bool) -> None:
        self.adapter.set_circular_enabled(enabled)

    def set_circular_arc(self, arc_start: int, arc_span: int) -> None:
        self.adapter.set_circular_arc(arc_start, arc_span)

    def set_branch_vertical_margin(self, value: int):
        self.adapter.set_branch_vertical_margin(value)

    def zoom_in(self):
        if self.adapter._view is not None:
            self.adapter._view.scale(1.2, 1.2)

    def zoom_out(self):
        if self.adapter._view is not None:
            self.adapter._view.scale(1 / 1.2, 1 / 1.2)

    def fit_to_view(self):
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


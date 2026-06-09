from typing import Callable

from infrastructure.tree.interfaces.tree_renderer import TreeRenderer
from infrastructure.tree.ete_adapter import ETEAdapter


class EteTreeRenderer(TreeRenderer):
    def __init__(self) -> None:
        self.adapter = ETEAdapter()

    def load_tree(self, tree_data: str) -> None:
        self.adapter.load_newick(tree_data)

    def render(self) -> str:
        return self.adapter.get_tree_summary()

    def show_graphics_tree(self) -> None:
        self.adapter.show_tree_window()

    def build_embedded_view(self):
        return self.adapter.build_embedded_view()

    def bind_click_callback(self, callback: Callable[[dict], None]) -> None:
        self.adapter.bind_click_callback(callback)

    def get_leaf_names(self):
        return self.adapter.get_leaf_names()

    def get_tree(self):
        return self.adapter.get_tree()

    def set_tree(self, tree) -> None:
        self.adapter.set_tree(tree)

    def set_show_leaf_name(self, flag: bool) -> None:
        self.adapter.set_show_leaf_name(flag)

    def set_show_branch_length(self, flag: bool) -> None:
        self.adapter.set_show_branch_length(flag)

    def set_show_branch_support(self, flag: bool) -> None:
        self.adapter.set_show_branch_support(flag)

    def set_branch_vertical_margin(self, value: int) -> None:
        self.adapter.set_branch_vertical_margin(value)

    def apply_diva_result(self, diva_result) -> None:
        self.adapter.apply_diva_result(diva_result)

    def apply_leaf_states(self, leaf_state_map: dict, state_colors: dict) -> None:
        self.adapter.apply_leaf_states(leaf_state_map, state_colors)
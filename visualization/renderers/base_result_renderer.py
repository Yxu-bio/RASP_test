from abc import ABC, abstractmethod

class BaseResultRenderer(ABC):
    @abstractmethod
    def set_tree(self, tree) -> None:
        pass

    @abstractmethod
    def set_result(self, result) -> None:
        pass

    @abstractmethod
    def build_view(self):
        """返回一个 QWidget 可嵌入 ResultViewWindow"""
        pass

    @abstractmethod
    def bind_node_click_callback(self, callback) -> None:
        pass

    @abstractmethod
    def apply_leaf_states(self, leaf_state_map: dict, state_color: dict) -> None:
        pass

    @abstractmethod
    def set_show_leaf_name(self, flag: bool) -> None:
        pass

    @abstractmethod
    def set_show_branch_length(self, flag: bool) -> None:
        pass

    @abstractmethod
    def set_show_branch_support(self, flag: bool) -> None:
        pass

    @abstractmethod
    def set_circular_enabled(self, enabled: bool) -> None:
        pass

    @abstractmethod
    def set_circular_arc(self, arc_start: int, arc_span: int) -> None:
        pass

    @abstractmethod
    def zoom_in(self) -> None:
        pass

    @abstractmethod
    def zoom_out(self) -> None:
        pass

    @abstractmethod
    def fit_to_view(self) -> None:
        pass

    @abstractmethod
    def export_tree_png(self, file_path: str) -> None:
        pass

    @abstractmethod
    def export_tree_svg(self, file_path: str) -> None:
        pass

    @abstractmethod
    def export_tree_pdf(self, file_path: str) -> None:
        pass

    @abstractmethod
    def select_node_by_clade_key(self, clade_key: str) -> None:
        pass
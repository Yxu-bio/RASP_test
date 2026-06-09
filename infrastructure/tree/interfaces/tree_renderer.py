from abc import ABC, abstractmethod
from typing import Callable


class TreeRenderer(ABC):
    @abstractmethod
    def load_tree(self, tree_data: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def render(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def show_graphics_tree(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def build_embedded_view(self):
        raise NotImplementedError

    @abstractmethod
    def bind_click_callback(self, callback: Callable[[dict], None]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_leaf_names(self):
        raise NotImplementedError

    @abstractmethod
    def get_tree(self):
        raise NotImplementedError

    @abstractmethod
    def set_tree(self, tree) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_show_leaf_name(self, flag: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_show_branch_length(self, flag: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_show_branch_support(self, flag: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_branch_vertical_margin(self, value: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def apply_diva_result(self, diva_result) -> None:
        raise NotImplementedError

    @abstractmethod
    def apply_leaf_states(self, leaf_state_map: dict, state_colors: dict) -> None:
        raise NotImplementedError
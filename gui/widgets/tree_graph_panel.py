from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout


class TreeGraphPanel(QWidget):
    node_clicked = pyqtSignal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.renderer = None
        self.tree_widget = None

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.setLayout(self.main_layout)

    def set_renderer(self, renderer) -> None:
        self.renderer = renderer
        self.refresh_tree()

    def refresh_tree(self, preserve_view: bool = False) -> None:
        if self.renderer is None:
            return

        old_transform = None
        old_h_value = None
        old_v_value = None

        # 保留当前缩放与滚动位置
        if preserve_view and self.tree_widget is not None:
            try:
                old_transform = self.tree_widget.transform()
                old_h_value = self.tree_widget.horizontalScrollBar().value()
                old_v_value = self.tree_widget.verticalScrollBar().value()
            except Exception:
                old_transform = None
                old_h_value = None
                old_v_value = None

        if self.tree_widget is not None:
            self.main_layout.removeWidget(self.tree_widget)
            self.tree_widget.setParent(None)
            self.tree_widget.deleteLater()
            self.tree_widget = None

        self.tree_widget = self.renderer.build_view()
        self.renderer.bind_node_click_callback(self.node_clicked.emit)
        self.main_layout.addWidget(self.tree_widget)

        if preserve_view and old_transform is not None:
            try:
                self.tree_widget.setTransform(old_transform)
                self.tree_widget.horizontalScrollBar().setValue(old_h_value)
                self.tree_widget.verticalScrollBar().setValue(old_v_value)
                self.tree_widget.viewport().update()
            except Exception:
                pass

    def zoom_in(self) -> None:
        if self.renderer is None:
            return
        self.renderer.zoom_in()

    def zoom_out(self) -> None:
        if self.renderer is None:
            return
        self.renderer.zoom_out()

    def fit_to_view(self) -> None:
        if self.renderer is None:
            return
        self.renderer.fit_to_view()

    def reset_zoom(self) -> None:
        if self.tree_widget is None:
            return

        try:
            self.tree_widget.resetTransform()
            self.tree_widget.viewport().update()
        except Exception:
            pass

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar


class ProgressPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.label = QLabel("空闲")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        layout = QHBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)

    def set_idle(self, message: str = "空闲") -> None:
        self.label.setText(message)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

    def set_busy_indeterminate(self, message: str) -> None:
        self.label.setText(message)
        self.progress_bar.setRange(0, 0)

    def set_progress(self, value: int, message: str = "") -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(max(0, min(100, int(value))))
        if message:
            self.label.setText(message)

    def set_done(self, message: str = "完成") -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.label.setText(message)

    def set_error(self, message: str = "失败") -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.label.setText(message)

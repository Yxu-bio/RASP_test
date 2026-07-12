from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar, QPushButton


class ProgressPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.label = QLabel("空闲")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._request_cancel)
        self._cancel_handler = None

        layout = QHBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.cancel_button)
        self.setLayout(layout)

    def set_cancel_handler(self, handler, text: str = "Cancel") -> None:
        self._cancel_handler = handler
        self.cancel_button.setText(text)
        self.cancel_button.setEnabled(handler is not None)
        self.cancel_button.setVisible(handler is not None)

    def clear_cancel_handler(self) -> None:
        self._cancel_handler = None
        self.cancel_button.setEnabled(False)
        self.cancel_button.setVisible(False)

    def _request_cancel(self) -> None:
        handler = self._cancel_handler
        if handler is None:
            return
        self.cancel_button.setEnabled(False)
        handler()

    def set_idle(self, message: str = "空闲") -> None:
        self.clear_cancel_handler()
        self.label.setText(message)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

    def set_busy_indeterminate(self, message: str) -> None:
        self.clear_cancel_handler()
        self.label.setText(message)
        self.progress_bar.setRange(0, 0)

    def set_progress(self, value: int, message: str = "") -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(max(0, min(100, int(value))))
        if message:
            self.label.setText(message)

    def set_done(self, message: str = "完成") -> None:
        self.clear_cancel_handler()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.label.setText(message)

    def set_error(self, message: str = "失败") -> None:
        self.clear_cancel_handler()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.label.setText(message)

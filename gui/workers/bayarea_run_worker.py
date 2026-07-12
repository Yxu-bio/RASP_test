import threading

from PyQt5.QtCore import QThread, pyqtSignal

from infrastructure.bayarea.bayarea_runner import BayAreaRunCancelled


class BayAreaRunWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal(str)
    progress = pyqtSignal(int, str)

    def __init__(
        self,
        *,
        service,
        tree,
        matrix,
        config,
        run_name=None,
    ):
        super().__init__()
        self.service = service
        self.tree = tree
        self.matrix = matrix
        self.config = config
        self.run_name = run_name
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def _is_cancelled(self):
        return self._cancel_event.is_set()

    def _report_progress(self, percent, message):
        self.progress.emit(int(percent), str(message or ""))

    def run(self):
        try:
            result = self.service.analyze(
                tree=self.tree,
                matrix=self.matrix,
                config=self.config,
                run_name=self.run_name,
                progress_callback=self._report_progress,
                cancel_callback=self._is_cancelled,
            )
        except BayAreaRunCancelled as exc:
            self.cancelled.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.succeeded.emit(result)

from PyQt5.QtCore import QThread, pyqtSignal


class SpatialAreaImportWorker(QThread):
    succeeded = pyqtSignal(str, object, object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)

    def __init__(self, *, service, file_path):
        super().__init__()
        self.service = service
        self.file_path = str(file_path or "")
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def _is_cancelled(self):
        return bool(self._cancel_requested)

    def run(self):
        try:
            areas, issues = self.service.import_area_geojson(
                self.file_path,
                progress_callback=self.progress.emit,
                cancel_callback=self._is_cancelled,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.succeeded.emit(self.file_path, areas, issues)

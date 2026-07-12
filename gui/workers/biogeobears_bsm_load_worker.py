from PyQt5.QtCore import QThread, pyqtSignal


class BioGeoBEARSBSMLoadWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, *, service, source_path):
        super().__init__()
        self.service = service
        self.source_path = source_path

    def run(self):
        try:
            result = self.service.load_existing_bsm_events(self.source_path)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)

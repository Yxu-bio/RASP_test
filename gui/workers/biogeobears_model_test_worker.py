from PyQt5.QtCore import QThread, pyqtSignal


class BioGeoBEARSModelTestWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)

    def __init__(
        self,
        *,
        service,
        tree,
        matrix,
        config,
        run_name_prefix="bgb_model_test",
    ):
        super().__init__()
        self.service = service
        self.tree = tree
        self.matrix = matrix
        self.run_name_prefix = run_name_prefix
        self.config = config

    def run(self):
        try:
            result = self.service.analyze(
                tree=self.tree,
                matrix=self.matrix,
                run_name_prefix=self.run_name_prefix,
                config=self.config,
                progress_callback=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.succeeded.emit(result)

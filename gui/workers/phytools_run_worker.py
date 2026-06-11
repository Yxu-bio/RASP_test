from PyQt5.QtCore import QThread, pyqtSignal


class PhytoolsRunWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, *, service, tree, matrix, config, run_name=None):
        super().__init__()
        self.service = service
        self.tree = tree
        self.matrix = matrix
        self.config = config
        self.run_name = run_name

    def run(self):
        try:
            result = self.service.analyze(
                tree=self.tree,
                matrix=self.matrix,
                config=self.config,
                run_name=self.run_name,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)

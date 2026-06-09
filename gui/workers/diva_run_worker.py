from PyQt5.QtCore import QThread, pyqtSignal


class DivaRunWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, service, tree, matrix, tree_name="t1", distribution_name="d1", config=None):
        super().__init__()
        self.service = service
        self.tree = tree
        self.matrix = matrix
        self.tree_name = tree_name
        self.distribution_name = distribution_name
        self.config = config

    def run(self):
        try:
            result = self.service.run(
                tree=self.tree,
                matrix=self.matrix,
                tree_name=self.tree_name,
                distribution_name=self.distribution_name,
                config=self.config,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.succeeded.emit(result)

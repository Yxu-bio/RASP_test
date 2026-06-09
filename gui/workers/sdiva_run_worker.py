from PyQt5.QtCore import QThread, pyqtSignal


class SDivaRunWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, service, tree_entries, matrix, reference_tree=None, distribution_name="d1", config=None):
        super().__init__()
        self.service = service
        self.tree_entries = tree_entries
        self.matrix = matrix
        self.reference_tree = reference_tree
        self.distribution_name = distribution_name
        self.config = config

    def run(self):
        try:
            result = self.service.run(
                tree_entries=self.tree_entries,
                matrix=self.matrix,
                reference_tree=self.reference_tree,
                distribution_name=self.distribution_name,
                config=self.config,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.succeeded.emit(result)

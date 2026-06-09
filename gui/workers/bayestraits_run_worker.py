from PyQt5.QtCore import QThread, pyqtSignal


class BayesTraitsRunWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        service,
        reference_tree,
        matrix,
        config,
        tree_entries=None,
        run_name=None,
    ):
        super().__init__()
        self.service = service
        self.reference_tree = reference_tree
        self.matrix = matrix
        self.config = config
        self.tree_entries = list(tree_entries or [])
        self.run_name = run_name

    def run(self):
        try:
            result = self.service.analyze(
                reference_tree=self.reference_tree,
                matrix=self.matrix,
                tree_entries=self.tree_entries,
                config=self.config,
                run_name=self.run_name,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.succeeded.emit(result)

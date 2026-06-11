from PyQt5.QtCore import QThread, pyqtSignal


class SDECRunWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)

    def __init__(
        self,
        *,
        service,
        reference_tree,
        matrix,
        tree_entries,
        run_name_prefix="sdec",
        config=None,
    ):
        super().__init__()
        self.service = service
        self.reference_tree = reference_tree
        self.matrix = matrix
        self.tree_entries = list(tree_entries or [])
        self.run_name_prefix = run_name_prefix
        self.config = config

    def run(self):
        try:
            result = self.service.analyze(
                reference_tree=self.reference_tree,
                matrix=self.matrix,
                tree_entries=self.tree_entries,
                run_name_prefix=self.run_name_prefix,
                config=self.config,
                progress_callback=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.succeeded.emit(result)

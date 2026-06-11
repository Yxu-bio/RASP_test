from PyQt5.QtCore import QThread, pyqtSignal


class SPhytoolsRunWorker(QThread):
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
        config,
        run_name_prefix="sphytools",
    ):
        super().__init__()
        self.service = service
        self.reference_tree = reference_tree
        self.matrix = matrix
        self.tree_entries = list(tree_entries or [])
        self.config = config
        self.run_name_prefix = run_name_prefix

    def run(self):
        try:
            result = self.service.analyze(
                reference_tree=self.reference_tree,
                matrix=self.matrix,
                tree_entries=self.tree_entries,
                config=self.config,
                run_name_prefix=self.run_name_prefix,
                progress_callback=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)

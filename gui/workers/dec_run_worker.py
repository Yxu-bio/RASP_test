from PyQt5.QtCore import QThread, pyqtSignal


class DECRunWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
            self,
            *,
            service,
            tree,
            matrix,
            run_name=None,
            config=None,
            scale_tree_to_root_age=False,
    ):
        super().__init__()
        self.service = service
        self.tree = tree
        self.matrix = matrix
        self.run_name = run_name
        self.config = config
        self.scale_tree_to_root_age = scale_tree_to_root_age

    def run(self):
        try:
            result = self.service.analyze(
                tree=self.tree,
                matrix=self.matrix,
                run_name=self.run_name,
                config=self.config,
                scale_tree_to_root_age=self.scale_tree_to_root_age,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.succeeded.emit(result)

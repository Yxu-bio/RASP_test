from PyQt5.QtCore import QThread, pyqtSignal


class BioGeoBEARSBSMEventWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        service,
        tree,
        matrix,
        config,
        run_name=None,
        nummaps=100,
        seed=12345,
        maxtries_per_branch=40000,
    ):
        super().__init__()
        self.service = service
        self.tree = tree
        self.matrix = matrix
        self.config = config
        self.run_name = run_name
        self.nummaps = nummaps
        self.seed = seed
        self.maxtries_per_branch = maxtries_per_branch

    def run(self):
        try:
            result = self.service.generate_bsm_events(
                tree=self.tree,
                matrix=self.matrix,
                config=self.config,
                run_name=self.run_name,
                nummaps=self.nummaps,
                seed=self.seed,
                maxtries_per_branch=self.maxtries_per_branch,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.succeeded.emit(result)

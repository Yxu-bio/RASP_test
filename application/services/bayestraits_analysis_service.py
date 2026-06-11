from datetime import datetime
from pathlib import Path

from application.services.bayestraits_dataset_builder import BayesTraitsDatasetBuilder
from infrastructure.bayestraits.bayestraits_output_parser import BayesTraitsOutputParser
from infrastructure.bayestraits.bayestraits_runner import BayesTraitsRunner


class BayesTraitsAnalysisService:
    def __init__(self, executable_path=None, work_root=None):
        self.dataset_builder = BayesTraitsDatasetBuilder()
        self.output_parser = BayesTraitsOutputParser()
        self.runner = BayesTraitsRunner(executable_path=executable_path)
        self.work_root = Path(work_root) if work_root else Path("runs") / "bayestraits"

    def set_executable_path(self, executable_path):
        self.runner.set_executable_path(executable_path)

    def analyze(self, *, reference_tree, matrix, config, tree_entries=None, run_name=None):
        if config is None:
            raise ValueError("BayesTraits config is required.")
        if run_name is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = "bayestraits_%s" % stamp

        self.work_root.mkdir(parents=True, exist_ok=True)
        run_files = self.dataset_builder.build(
            reference_tree=reference_tree,
            matrix=matrix,
            tree_entries=tree_entries,
            config=config,
            output_dir=self.work_root,
            run_name=run_name,
        )

        try:
            run_output = self.runner.run(run_files)
        except Exception as exc:
            raise RuntimeError(
                "BayesTraits run failed.\n"
                "workdir: {workdir}\n"
                "trees: {trees}\n"
                "data: {data}\n"
                "commands: {commands}\n"
                "{msg}".format(
                    workdir=run_files.workdir,
                    trees=run_files.trees_path,
                    data=run_files.data_path,
                    commands=run_files.commands_path,
                    msg=str(exc),
                )
            )

        result = self.output_parser.parse(
            reference_tree=reference_tree,
            run_files=run_files,
            run_output=run_output,
        )
        result.config = config
        return result

from datetime import datetime
from pathlib import Path

from application.services.bbm_dataset_builder import BBMDatasetBuilder
from infrastructure.mrbayes.bbm_output_parser import BBMOutputParser
from infrastructure.mrbayes.mrbayes_runner import MrBayesRunner


class BBMAnalysisService:
    def __init__(self, executable_path=None, work_root=None):
        self.dataset_builder = BBMDatasetBuilder()
        self.output_parser = BBMOutputParser()
        self.runner = MrBayesRunner(executable_path=executable_path)
        self.work_root = Path(work_root) if work_root else Path("runs") / "bbm"

    def set_executable_path(self, executable_path):
        self.runner.set_executable_path(executable_path)

    def analyze(self, *, tree, matrix, config, run_name=None):
        if config is None:
            raise ValueError("BBM config is required.")
        if run_name is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = "bbm_%s" % stamp

        self.work_root.mkdir(parents=True, exist_ok=True)
        run_files = self.dataset_builder.build(
            tree=tree,
            matrix=matrix,
            config=config,
            output_dir=self.work_root,
            run_name=run_name,
        )

        try:
            run_output = self.runner.run(run_files)
        except Exception as exc:
            raise RuntimeError(
                "BBM run failed.\n"
                "workdir: {workdir}\n"
                "nexus: {nexus}\n"
                "{msg}".format(
                    workdir=run_files.workdir,
                    nexus=run_files.nexus_path,
                    msg=str(exc),
                )
            )

        result = self.output_parser.parse(
            reference_tree=tree,
            run_files=run_files,
            run_output=run_output,
        )
        result.config = config
        return result

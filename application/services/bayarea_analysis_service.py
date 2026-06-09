import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from application.services.bayarea_dataset_builder import BayAreaDatasetBuilder, BayAreaRunFiles
from infrastructure.bayarea.bayarea_output_parser import BayAreaOutputParser
from infrastructure.bayarea.bayarea_runner import BayAreaRunner


class BayAreaAnalysisService:
    def __init__(self, executable_path=None, work_root=None):
        self.dataset_builder = BayAreaDatasetBuilder()
        self.output_parser = BayAreaOutputParser()
        self.runner = BayAreaRunner(executable_path=executable_path)
        self.work_root = Path(work_root) if work_root else Path("runs") / "bayarea"

    def set_executable_path(self, executable_path):
        self.runner.set_executable_path(executable_path)

    def analyze(self, *, tree, matrix, config, run_name=None):
        if config is None:
            raise ValueError("BayArea config is required.")
        if run_name is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = "bayarea_%s" % stamp

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
                "BayArea run failed.\n"
                "workdir: {workdir}\n"
                "areas: {areas}\n"
                "geo: {geo}\n"
                "tree: {tree}\n"
                "{msg}".format(
                    workdir=run_files.workdir,
                    areas=run_files.areas_path,
                    geo=run_files.geo_path,
                    tree=run_files.tree_path,
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

    def reparse_existing_result(self, *, reference_tree, result, burnin):
        stats = dict(getattr(result, "model_statistics", {}) or {})
        parameters_path = Path(str(stats.get("parameters_path", "") or ""))
        if not parameters_path.exists():
            raise FileNotFoundError("BayArea parameters file was not found.")

        workdir = parameters_path.parent
        manifest_path = workdir / "bayarea_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError("BayArea manifest file was not found: %s" % manifest_path)

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        runtime = dict(payload.get("runtime", {}) or {})
        config = deepcopy(getattr(result, "config", None))
        if config is not None:
            config.burnin = int(burnin or 0)

        run_files = BayAreaRunFiles(
            workdir=workdir,
            areas_path=workdir / "bayarea.areas.txt",
            geo_path=workdir / "bayarea.geo.txt",
            tree_path=workdir / "bayarea.tree.txt",
            manifest_path=manifest_path,
            stdout_log_path=workdir / "bayarea_stdout.log",
            stderr_log_path=workdir / "bayarea_stderr.log",
            area_names=list(payload.get("area_names", []) or []),
            taxon_names=list(payload.get("taxon_names", []) or []),
            taxon_ids=list(payload.get("taxon_ids", []) or []),
            taxon_count=int(payload.get("taxon_count", 0) or 0),
            node_index_to_clade={
                int(key): value
                for key, value in dict(payload.get("node_index_to_clade", {}) or {}).items()
            },
            clade_to_reference_node_id=self.dataset_builder._build_reference_node_id_map(reference_tree),
            burnin=int(burnin or 0),
            sample_frequency=int(payload.get("sample_frequency", stats.get("sample_frequency", 0)) or 0),
            chain_length=int(payload.get("chain_length", stats.get("chain_length", 0)) or 0),
            output_prefix=str(payload.get("output_prefix", "bayarea") or "bayarea"),
            parameters_path=parameters_path,
            area_states_path=Path(str(stats.get("area_states_path", "") or "")),
            area_probs_path=Path(str(stats.get("area_probs_path", "") or "")),
            nhx_path=Path(str(stats.get("nhx_path", "") or "")),
            config=config,
            extra_metadata=runtime,
        )
        stdout = ""
        if run_files.stdout_log_path.exists():
            stdout = run_files.stdout_log_path.read_text(encoding="utf-8", errors="replace")

        reparsed = self.output_parser.parse(
            reference_tree=reference_tree,
            run_files=run_files,
            run_output=SimpleNamespace(stdout=stdout),
        )
        reparsed.config = config
        return reparsed

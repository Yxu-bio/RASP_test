from datetime import datetime
from pathlib import Path

from application.services.biogeobears_dataset_builder import BioGeoBEARSDatasetBuilder
from infrastructure.biogeobears.biogeobears_output_parser import BioGeoBEARSOutputParser
from infrastructure.biogeobears.biogeobears_runner import BioGeoBEARSRunner


class BioGeoBEARSAnalysisService:
    def __init__(self, rscript_path=None, wrapper_script_path=None, work_root=None, site_library_path=None):
        self.dataset_builder = BioGeoBEARSDatasetBuilder()
        self.output_parser = BioGeoBEARSOutputParser()
        self.runner = BioGeoBEARSRunner(
            rscript_path=rscript_path,
            wrapper_script_path=wrapper_script_path,
            site_library_path=site_library_path,
        )
        self.work_root = Path(work_root) if work_root else Path("runs") / "biogeobears"

    def set_rscript_path(self, rscript_path):
        self.runner.set_rscript_path(rscript_path)

    def set_wrapper_script_path(self, wrapper_script_path):
        self.runner.set_wrapper_script_path(wrapper_script_path)

    def set_site_library_path(self, site_library_path):
        self.runner.set_site_library_path(site_library_path)

    def analyze(
        self,
        *,
        tree,
        matrix,
        config,
        run_name=None,
        scale_tree_to_root_age=False,
    ):
        if config is None:
            raise ValueError("BioGeoBEARS config is required.")

        config_kwargs = config.engine_kwargs()
        model_name = config_kwargs["model_name"]
        max_range_size = config_kwargs["max_range_size"]
        include_null_range = config_kwargs["include_null_range"]
        null_range_mode = config_kwargs["null_range_mode"]
        cores = config_kwargs["cores"]
        include_ranges = config_kwargs["include_ranges"]
        exclude_ranges = config_kwargs["exclude_ranges"]
        period_times = config_kwargs["period_times"]
        time_matrix_kind = config_kwargs["time_matrix_kind"]
        period_matrices = config_kwargs["period_matrices"]
        root_age = config_kwargs["root_age"]

        if run_name is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = "bgb_%s_%s" % (str(model_name).lower(), stamp)

        run_files = self.build_run_files(
            tree=tree,
            matrix=matrix,
            run_name=run_name,
            model_name=model_name,
            max_range_size=max_range_size,
            include_null_range=include_null_range,
            null_range_mode=null_range_mode,
            cores=cores,
            include_ranges=include_ranges,
            exclude_ranges=exclude_ranges,
            period_times=period_times,
            time_matrix_kind=time_matrix_kind,
            period_matrices=period_matrices,
            root_age=root_age,
            scale_tree_to_root_age=scale_tree_to_root_age,
        )

        try:
            run_output = self.runner.run(run_files)
        except Exception as exc:
            raise RuntimeError(
                "BioGeoBEARS 运行失败。\n"
                "workdir: {workdir}\n"
                "treefile: {treefile}\n"
                "geogfile: {geogfile}\n"
                "areas_json: {areas_json}\n"
                "model: {model}\n"
                "{msg}".format(
                    workdir=run_files.workdir,
                    treefile=run_files.tree_path,
                    geogfile=run_files.geog_path,
                    areas_json=run_files.areas_json_path,
                    model=run_files.model_name,
                    msg=str(exc),
                )
            )

        result = self.parse_run_files(tree=tree, run_files=run_files)
        result.config = config
        return result

    def build_run_files(
        self,
        *,
        tree,
        matrix,
        run_name,
        model_name,
        max_range_size,
        include_null_range,
        null_range_mode,
        cores,
        include_ranges,
        exclude_ranges,
        period_times,
        time_matrix_kind,
        period_matrices,
        root_age,
        scale_tree_to_root_age=False,
    ):
        self.work_root.mkdir(parents=True, exist_ok=True)
        return self.dataset_builder.build(
            tree=tree,
            matrix=matrix,
            output_dir=self.work_root,
            run_name=run_name,
            model_name=model_name,
            max_range_size=max_range_size,
            include_null_range=include_null_range,
            null_range_mode=null_range_mode,
            cores=cores,
            include_ranges=include_ranges,
            exclude_ranges=exclude_ranges,
            period_times=period_times,
            time_matrix_kind=time_matrix_kind,
            period_matrices=period_matrices,
            root_age=root_age,
            scale_tree_to_root_age=scale_tree_to_root_age,
        )

    def run_batch(
        self,
        run_files_list,
        *,
        batch_workdir,
        batch_name="batch",
        job_ids=None,
        progress_callback=None,
    ):
        return self.runner.run_batch(
            run_files_list,
            batch_workdir=batch_workdir,
            batch_name=batch_name,
            job_ids=job_ids,
            progress_callback=progress_callback,
        )

    def parse_run_files(self, *, tree, run_files):
        result = self.output_parser.parse(
            reference_tree=tree,
            output_json_path=run_files.output_json_path,
        )
        result.result_note += " workdir=%s" % run_files.workdir
        return result

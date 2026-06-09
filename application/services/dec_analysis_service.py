from datetime import datetime
from pathlib import Path

from application.services.dec_dataset_builder import DECDatasetBuilder
from infrastructure.dec.dec_output_parser import DECOutputParser
from infrastructure.dec.dec_runner import DECRunner


class DECAnalysisService:
    def __init__(self, engine_path=None, work_root=None):
        self.dataset_builder = DECDatasetBuilder()
        self.output_parser = DECOutputParser()
        self.runner = DECRunner(engine_path=engine_path)
        self.work_root = Path(work_root) if work_root else Path("runs") / "dec"

    def set_engine_path(self, engine_path) -> None:
        self.runner.set_engine_path(engine_path)

    def analyze(
        self,
        *,
        tree,
        matrix,
        run_name=None,
        scale_tree_to_root_age=False,
        config=None,
        runner_env_overrides=None,
    ):
        self.work_root.mkdir(parents=True, exist_ok=True)

        if run_name is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = f"dec_{stamp}"

        if config is not None:
            config_values = config.builder_kwargs()
            max_areas = config_values["max_areas"]
            workers = config_values["workers"]
            threads_per_worker = config_values["threads_per_worker"]
            include_splits = config_values["include_splits"]
            opt_method = config_values["opt_method"]
            mode = config_values["mode"]
            dispersion = config_values["dispersion"]
            extinction = config_values["extinction"]
            expm_mode = config_values["expm_mode"]
            allow_ambiguous = config_values["allow_ambiguous"]
            lwr_threshold = config_values["lwr_threshold"]
            extra_control_lines = config_values["extra_control_lines"]
            period_times = config_values["period_times"]
            dispersal_matrices = config_values["dispersal_matrices"]
            period_include_area_bits = config_values.get("period_include_area_bits")
            period_exclude_area_bits = config_values.get("period_exclude_area_bits")
            mrca_constraints = config_values["mrca_constraints"]
            root_age = config_values.get("root_age")
        else:
            raise ValueError("DEC analysis requires a DEC/S-DEC config object.")

        run_files = self.dataset_builder.build(
            tree=tree,
            matrix=matrix,
            output_dir=self.work_root,
            run_name=run_name,
            max_areas=max_areas,
            workers=workers,
            threads_per_worker=threads_per_worker,
            include_states=True,
            include_splits=include_splits,
            output_type="json",
            opt_method=opt_method,
            mode=mode,
            dispersion=dispersion,
            extinction=extinction,
            expm_mode=expm_mode,
            allow_ambiguous=allow_ambiguous,
            lwr_threshold=lwr_threshold,
            extra_control_lines=extra_control_lines,
            period_times=period_times,
            dispersal_matrices=dispersal_matrices,
            period_include_area_bits=period_include_area_bits,
            period_exclude_area_bits=period_exclude_area_bits,
            mrca_constraints=mrca_constraints,
            root_age=root_age,
            scale_tree_to_root_age=scale_tree_to_root_age,
        )

        run_output = self.runner.run(run_files, env_overrides=runner_env_overrides)

        result = self.output_parser.parse(
            reference_tree=tree,
            area_names=run_files.area_names,
            results_json_path=run_output.results_json_path,
            nodes_tree_path=run_output.nodes_tree_path,
        )

        if config is not None:
            for warning in list(config_values.get("native_range_constraint_warnings", []) or []):
                if warning not in result.parse_warnings:
                    result.parse_warnings.append(warning)

        result.result_note = (
            result.result_note
            + f" workdir={run_files.workdir}"
            + f" engine={run_output.engine_path.name}"
        )
        if self._has_period_area_bits(period_include_area_bits) or self._has_period_area_bits(period_exclude_area_bits):
            result.result_note += " native_range_constraints=lagrange-ng-period-area-mask"
        return result

    def _has_period_area_bits(self, value) -> bool:
        if isinstance(value, str):
            return "1" in value
        return any("1" in str(item or "") for item in list(value or []))

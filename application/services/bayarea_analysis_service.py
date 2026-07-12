import json
import math
import random
import shutil
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from application.services.bayarea_dataset_builder import BayAreaDatasetBuilder, BayAreaRunFiles
from domain.models.biogeobears_result import BioGeoBEARSNodeResult
from infrastructure.bayarea.bayarea_output_parser import BayAreaOutputParser
from infrastructure.bayarea.bayarea_runner import BayAreaRunCancelled, BayAreaRunner


class BayAreaAnalysisService:
    def __init__(self, executable_path=None, work_root=None):
        self.dataset_builder = BayAreaDatasetBuilder()
        self.output_parser = BayAreaOutputParser()
        self.runner = BayAreaRunner(executable_path=executable_path)
        self.work_root = Path(work_root) if work_root else Path("runs") / "bayarea"

    def set_executable_path(self, executable_path):
        self.runner.set_executable_path(executable_path)

    def analyze(self, *, tree, matrix, config, run_name=None, progress_callback=None, cancel_callback=None):
        if config is None:
            raise ValueError("BayArea config is required.")
        if run_name is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = "bayarea_%s" % stamp

        chain_count = max(1, int(getattr(config, "independent_chains", 1) or 1))
        if chain_count > 1:
            return self._analyze_multiple_chains(
                tree=tree,
                matrix=matrix,
                config=config,
                run_name=run_name,
                progress_callback=progress_callback,
                cancel_callback=cancel_callback,
            )

        result, _run_files = self._analyze_single(
            tree=tree,
            matrix=matrix,
            config=config,
            run_name=run_name,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
        )
        result.config = config
        result.model_statistics["bayarea_chain_count"] = 1
        result.model_statistics["bayarea_chain_parameters_paths"] = [
            str(result.model_statistics.get("parameters_path", "") or "")
        ]
        return result

    def _analyze_single(
        self,
        *,
        tree,
        matrix,
        config,
        run_name,
        progress_callback=None,
        cancel_callback=None
    ):
        self.work_root.mkdir(parents=True, exist_ok=True)
        run_files = self.dataset_builder.build(
            tree=tree,
            matrix=matrix,
            config=config,
            output_dir=self.work_root,
            run_name=run_name,
        )

        try:
            run_output = self.runner.run(
                run_files,
                progress_callback=progress_callback,
                cancel_callback=cancel_callback,
            )
        except BayAreaRunCancelled:
            raise
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
        return result, run_files

    def _analyze_multiple_chains(
        self,
        *,
        tree,
        matrix,
        config,
        run_name,
        progress_callback=None,
        cancel_callback=None
    ):
        chain_count = max(2, int(getattr(config, "independent_chains", 2) or 2))
        parallel = max(1, min(chain_count, int(getattr(config, "parallel_chains", chain_count) or chain_count)))
        base_seed = getattr(config, "seed", None)
        if base_seed is None:
            base_seed = random.SystemRandom().randint(1, 2000000000)

        stop_event = threading.Event()
        progress_lock = threading.Lock()
        chain_progress = [0 for _ in range(chain_count)]
        last_aggregate_progress = [-1]
        results = [None for _ in range(chain_count)]
        run_files_list = [None for _ in range(chain_count)]

        def combined_cancelled():
            return stop_event.is_set() or (cancel_callback is not None and bool(cancel_callback()))

        def chain_callback(index):
            def report(percent, message):
                with progress_lock:
                    chain_progress[index] = max(0, min(100, int(percent)))
                    aggregate = int(round(sum(chain_progress) / float(chain_count)))
                    should_report = aggregate != last_aggregate_progress[0]
                    if should_report:
                        last_aggregate_progress[0] = aggregate
                if progress_callback is not None and should_report:
                    progress_callback(
                        aggregate,
                        "Chain %d/%d: %s" % (index + 1, chain_count, str(message or "BayArea")),
                    )
            return report

        def run_chain(index):
            chain_config = deepcopy(config)
            chain_config.independent_chains = 1
            chain_config.parallel_chains = 1
            chain_config.seed = self._chain_seed(base_seed, index)
            # Multi-chain exports are copied after every chain has completed so
            # parallel workers cannot overwrite the same four output files.
            chain_config.save_original_results = False
            chain_config.save_original_results_path = ""
            return self._analyze_single(
                tree=tree,
                matrix=matrix,
                config=chain_config,
                run_name="%s_chain_%02d" % (run_name, index + 1),
                progress_callback=chain_callback(index),
                cancel_callback=combined_cancelled,
            )

        executor = ThreadPoolExecutor(max_workers=parallel)
        futures = {executor.submit(run_chain, index): index for index in range(chain_count)}
        first_error = None
        try:
            for future in as_completed(futures):
                index = futures[future]
                try:
                    result, run_files = future.result()
                    results[index] = result
                    run_files_list[index] = run_files
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
                    stop_event.set()
        finally:
            stop_event.set() if first_error is not None else None
            executor.shutdown(wait=True)

        if first_error is not None:
            raise first_error
        if combined_cancelled():
            raise BayAreaRunCancelled("BayArea multi-chain run cancelled.")

        combined = self._combine_chain_results(
            reference_tree=tree,
            config=config,
            results=results,
            run_files_list=run_files_list,
            combined_workdir=self.work_root / (run_name + "_combined"),
        )
        self._copy_multi_chain_original_outputs(config, run_files_list)
        if progress_callback is not None:
            progress_callback(100, "BayArea chains complete")
        return combined

    def _copy_multi_chain_original_outputs(self, config, run_files_list):
        if not bool(getattr(config, "save_original_results", False)):
            return
        target_text = str(getattr(config, "save_original_results_path", "") or "").strip()
        if not target_text:
            return
        target_root = Path(target_text)
        target_root.mkdir(parents=True, exist_ok=True)
        for index, run_files in enumerate(run_files_list):
            chain_target = target_root / ("chain_%02d" % (index + 1))
            chain_target.mkdir(parents=True, exist_ok=True)
            for path in [
                run_files.parameters_path,
                run_files.area_states_path,
                run_files.area_probs_path,
                run_files.nhx_path,
            ]:
                if path is None or not Path(path).exists():
                    continue
                target_path = chain_target / Path(path).name
                if run_files.nhx_path is not None and Path(path) == Path(run_files.nhx_path):
                    self.runner._copy_nhx_with_taxon_names(Path(path), target_path, run_files)
                else:
                    shutil.copy2(str(path), str(target_path))

    def _chain_seed(self, base_seed, index):
        maximum = 2147483646
        return ((int(base_seed) - 1 + int(index) * 1000003) % maximum) + 1

    def _combine_chain_results(self, *, reference_tree, config, results, run_files_list, combined_workdir):
        if not results or any(result is None for result in results):
            raise ValueError("BayArea chain results are incomplete.")
        combined = deepcopy(results[0])
        combined.node_results = {}
        combined.reference_node_ids = {}
        combined.state_order = []

        counts_by_node = {}
        bit_counts_by_node = {}
        samples_by_node = {}
        clade_keys = []
        for result in results:
            for clade_key in result.node_results.keys():
                if clade_key not in clade_keys:
                    clade_keys.append(clade_key)

        for clade_key in clade_keys:
            counts = Counter()
            bit_counts = Counter()
            total = 0
            template = None
            for result in results:
                node_result = result.node_results.get(clade_key)
                if node_result is None:
                    continue
                if template is None:
                    template = node_result
                raw = dict(node_result.raw_method_payload or {})
                counts.update(dict(raw.get("bayarea_counts", {}) or {}))
                bit_counts.update(dict(raw.get("bayarea_bit_counts", {}) or {}))
                total += int(raw.get("bayarea_samples", 0) or 0)
            if template is None or total <= 0:
                continue
            ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            states = [label for label, _count in ordered]
            supports = {label: float(count) * 100.0 / float(total) for label, count in ordered}
            for state in states:
                if state not in combined.state_order:
                    combined.state_order.append(state)
            node_result = BioGeoBEARSNodeResult(
                node_key=clade_key,
                display_node_id=str(template.display_node_id),
                states=states,
                state_supports=supports,
                pie_labels=states,
                pie_percents=[supports[state] for state in states],
                pie_colors=[],
                supporting_tree_count=1,
                total_tree_count=1,
                event_summary="BayArea posterior pooled across %d independent chains" % len(results),
                raw_method_payload={
                    "bayarea_counts": dict(counts),
                    "bayarea_bit_counts": dict(bit_counts),
                    "bayarea_samples": total,
                    "bayarea_chain_count": len(results),
                },
            )
            combined.node_results[clade_key] = node_result
            combined.reference_node_ids[clade_key] = node_result.display_node_id
            counts_by_node[clade_key] = counts
            bit_counts_by_node[clade_key] = bit_counts
            samples_by_node[clade_key] = total

        combined.state_colors = self.output_parser._build_state_colors(combined.state_order)
        for node_result in combined.node_results.values():
            node_result.pie_colors = [
                combined.state_colors.get(label, "#808080") for label in node_result.pie_labels
            ]

        chain_runs = [self._chain_run_record(result, run_files) for result, run_files in zip(results, run_files_list)]
        statistics = dict(results[0].model_statistics or {})
        chain_statistics = [dict(result.model_statistics or {}) for result in results]
        statistics.pop("bayarea_trace_diagnostics", None)
        statistics["bayarea_chain_statistics"] = chain_statistics
        statistics["bayarea_trace_diagnostics_by_chain"] = [
            dict(item.get("bayarea_trace_diagnostics", {}) or {}) for item in chain_statistics
        ]
        statistics["sampled_lnL_count"] = sum(
            int(item.get("sampled_lnL_count", 0) or 0) for item in chain_statistics
        )
        statistics["bayarea_last_lnL_by_chain"] = [item.get("last_lnL") for item in chain_statistics]
        statistics["bayarea_chain_count"] = len(results)
        statistics["bayarea_chain_runs"] = chain_runs
        statistics["bayarea_chain_parameters_paths"] = [record["parameters_path"] for record in chain_runs]
        statistics["bayarea_chain_seeds"] = [record.get("seed") for record in chain_runs]
        statistics["bayarea_split_rhat"] = self._multi_chain_rhat(chain_runs, int(getattr(config, "burnin", 0) or 0))
        statistics["bayarea_combined_workdir"] = str(combined_workdir)
        combined.model_statistics = statistics

        warnings = []
        for index, result in enumerate(results):
            for warning in list(result.parse_warnings or []):
                warnings.append("Chain %d: %s" % (index + 1, warning))
        for name, value in dict(statistics["bayarea_split_rhat"] or {}).items():
            if value is not None and float(value) > 1.05:
                warnings.append(
                    "BayArea %s split-Rhat is %.3f across %d chains; the chains have not converged."
                    % (name, value, len(results))
                )
        combined.parse_warnings = warnings
        combined.config = config
        combined.result_note = (
            "Parsed from RASP-patched BayArea v1.0.3 output and pooled across %d independent chains."
            % len(results)
        )

        combined_workdir = Path(combined_workdir)
        combined_workdir.mkdir(parents=True, exist_ok=True)
        first_run = deepcopy(run_files_list[0])
        first_run.workdir = combined_workdir
        for source, name in [
            (run_files_list[0].areas_path, "bayarea.areas.txt"),
            (run_files_list[0].geo_path, "bayarea.geo.txt"),
            (run_files_list[0].tree_path, "bayarea.tree.txt"),
        ]:
            target = combined_workdir / name
            shutil.copy2(str(source), str(target))
            if name == "bayarea.areas.txt":
                first_run.areas_path = target
            elif name == "bayarea.geo.txt":
                first_run.geo_path = target
            else:
                first_run.tree_path = target
        analysis_log = self.output_parser._write_legacy_analysis_log(
            reference_tree=reference_tree,
            run_files=first_run,
            counts_by_node=counts_by_node,
            bit_counts_by_node=bit_counts_by_node,
            samples_by_node=samples_by_node,
        )
        combined.analysis_log_path = str(analysis_log)
        combined.model_statistics["analysis_log_path"] = str(analysis_log)
        return combined

    def _chain_run_record(self, result, run_files):
        stats = dict(result.model_statistics or {})
        return {
            "workdir": str(run_files.workdir),
            "manifest_path": str(run_files.manifest_path),
            "parameters_path": str(stats.get("parameters_path", "") or ""),
            "area_states_path": str(stats.get("area_states_path", "") or ""),
            "area_probs_path": str(stats.get("area_probs_path", "") or ""),
            "nhx_path": str(stats.get("nhx_path", "") or ""),
            "seed": stats.get("seed"),
        }

    def _multi_chain_rhat(self, chain_runs, burnin):
        traces = {}
        rows_by_chain = [self._parameter_rows(record["parameters_path"], burnin) for record in chain_runs]
        names = ["lnL", "gain", "loss", "distP"]
        for name in names:
            values = [[row[name] for row in rows if name in row] for rows in rows_by_chain]
            if all(values):
                traces[name] = self._split_rhat(values)
        return traces

    def _parameter_rows(self, path, burnin):
        path = Path(str(path or ""))
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) < 2:
            return []
        header = lines[0].split("\t")
        rows = []
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) < len(header):
                continue
            try:
                row = {name: float(value) for name, value in zip(header, parts)}
            except Exception:
                continue
            if int(row.get("n", 0)) >= int(burnin or 0):
                rows.append(row)
        return rows

    def _split_rhat(self, chains):
        split_chains = []
        for values in chains:
            midpoint = len(values) // 2
            if midpoint < 2:
                return None
            split_chains.append(list(values[:midpoint]))
            split_chains.append(list(values[-midpoint:]))
        sample_count = min(len(values) for values in split_chains)
        if sample_count < 2:
            return None
        split_chains = [values[-sample_count:] for values in split_chains]
        means = [sum(values) / float(sample_count) for values in split_chains]
        variances = [
            sum((value - mean) ** 2 for value in values) / float(sample_count - 1)
            for values, mean in zip(split_chains, means)
        ]
        within = sum(variances) / float(len(variances))
        if within <= 0.0:
            return 1.0 if max(means) == min(means) else float("inf")
        grand_mean = sum(means) / float(len(means))
        between = sample_count * sum((mean - grand_mean) ** 2 for mean in means) / float(len(means) - 1)
        variance = ((sample_count - 1.0) / sample_count) * within + between / sample_count
        return max(1.0, math.sqrt(max(0.0, variance / within)))

    def reparse_existing_result(self, *, reference_tree, result, burnin):
        stats = dict(getattr(result, "model_statistics", {}) or {})
        config = deepcopy(getattr(result, "config", None))
        if config is not None:
            config.burnin = int(burnin or 0)

        chain_records = list(stats.get("bayarea_chain_runs", []) or [])
        if len(chain_records) > 1:
            chain_results = []
            run_files_list = []
            for record in chain_records:
                chain_result, run_files = self._parse_existing_chain(
                    reference_tree=reference_tree,
                    record=record,
                    burnin=burnin,
                    config=config,
                    fallback_stats=stats,
                )
                chain_results.append(chain_result)
                run_files_list.append(run_files)
            combined_workdir = Path(
                str(stats.get("bayarea_combined_workdir", "") or "")
                or str(Path(run_files_list[0].workdir).parent / "bayarea_reparsed_combined")
            )
            return self._combine_chain_results(
                reference_tree=reference_tree,
                config=config,
                results=chain_results,
                run_files_list=run_files_list,
                combined_workdir=combined_workdir,
            )

        parameters_path = str(stats.get("parameters_path", "") or "").strip()
        if not parameters_path:
            raise FileNotFoundError("BayArea parameters file was not found.")
        record = {
            "parameters_path": parameters_path,
            "area_states_path": stats.get("area_states_path", ""),
            "area_probs_path": stats.get("area_probs_path", ""),
            "nhx_path": stats.get("nhx_path", ""),
        }
        reparsed, _run_files = self._parse_existing_chain(
            reference_tree=reference_tree,
            record=record,
            burnin=burnin,
            config=config,
            fallback_stats=stats,
        )
        reparsed.model_statistics["bayarea_chain_count"] = 1
        reparsed.model_statistics["bayarea_chain_parameters_paths"] = [parameters_path]
        return reparsed

    def _parse_existing_chain(self, *, reference_tree, record, burnin, config, fallback_stats):
        parameters_text = str(dict(record or {}).get("parameters_path", "") or "").strip()
        if not parameters_text:
            raise FileNotFoundError("BayArea parameters file was not found for one chain.")
        parameters_path = Path(parameters_text)
        if not parameters_path.exists():
            raise FileNotFoundError("BayArea parameters file was not found: %s" % parameters_path)

        workdir_text = str(dict(record or {}).get("workdir", "") or "").strip()
        workdir = Path(workdir_text) if workdir_text else parameters_path.parent
        manifest_text = str(dict(record or {}).get("manifest_path", "") or "").strip()
        manifest_path = Path(manifest_text) if manifest_text else workdir / "bayarea_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError("BayArea manifest file was not found: %s" % manifest_path)

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        runtime = dict(payload.get("runtime", {}) or {})

        def output_path(name, fallback_name):
            text = str(dict(record or {}).get(name, "") or "").strip()
            if text:
                return Path(text)
            fallback = str(dict(fallback_stats or {}).get(name, "") or "").strip()
            return Path(fallback) if fallback else workdir / fallback_name

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
            sample_frequency=int(payload.get("sample_frequency", fallback_stats.get("sample_frequency", 0)) or 0),
            chain_length=int(payload.get("chain_length", fallback_stats.get("chain_length", 0)) or 0),
            output_prefix=str(payload.get("output_prefix", "bayarea") or "bayarea"),
            parameters_path=parameters_path,
            area_states_path=output_path("area_states_path", "bayarea.areas.txt.area_states.txt"),
            area_probs_path=output_path("area_probs_path", "bayarea.areas.txt.area_probs.txt"),
            nhx_path=output_path("nhx_path", "bayarea.areas.txt.nhx"),
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
        return reparsed, run_files

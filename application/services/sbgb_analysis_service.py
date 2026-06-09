from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Dict, List

from domain.models.sbgb_config import normalize_sbgb_null_range_mode
from domain.models.biogeobears_result import BioGeoBEARSResult, BioGeoBEARSNodeResult


class SBGBAnalysisService:
    """
    Legacy-style S-BioGeoBEARS coordinator.

    Old RASP runs BioGeoBEARS once per sampled tree, converts every per-tree
    result to a RASP intermediate .BGB.txt file, and then combines those files
    by matching clades against the reference tree.  This service keeps that
    orchestration and delegates each per-tree likelihood analysis to the
    current BioGeoBEARSAnalysisService wrapper.
    """

    PALETTE = [
        "#e41a1c",
        "#377eb8",
        "#4daf4a",
        "#984ea3",
        "#ff7f00",
        "#ffff33",
        "#a65628",
        "#f781bf",
        "#999999",
        "#66c2a5",
        "#fc8d62",
        "#8da0cb",
        "#e78ac3",
        "#a6d854",
        "#ffd92f",
        "#1b9e77",
        "#d95f02",
        "#7570b3",
        "#e7298a",
        "#66a61e",
    ]

    MODEL_DISPLAY_NAMES = {
        "DEC": "DEC",
        "DECJ": "DEC+J",
        "DIVALIKE": "DIVALIKE",
        "DIVALIKEJ": "DIVALIKE+J",
        "BAYAREALIKE": "BAYAREALIKE",
        "BAYAREALIKEJ": "BAYAREALIKE+J",
    }

    def __init__(self, biogeobears_service, project_root=None):
        self.biogeobears_service = biogeobears_service
        if project_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent
        self.project_root = Path(project_root)

    def analyze(
        self,
        *,
        reference_tree,
        matrix,
        tree_entries,
        config,
        run_name_prefix="sbgb",
        progress_callback=None,
    ):
        tree_entries = list(tree_entries or [])
        if not tree_entries:
            raise ValueError("S-BGB run failed: no tree-set input is available.")
        if reference_tree is None:
            raise ValueError("S-BGB run failed: reference tree is required.")
        if matrix is None:
            raise ValueError("S-BGB run failed: matrix is required.")

        if config is None:
            raise ValueError("S-BGB config is required.")

        config_kwargs = config.engine_kwargs()
        model_name = config_kwargs["model_name"]
        max_range_size = config_kwargs["max_range_size"]
        include_null_range = config_kwargs["include_null_range"]
        null_range_mode = config_kwargs["null_range_mode"]
        thread_count = config_kwargs.get("threads", config_kwargs["cores"])
        include_ranges = config_kwargs["include_ranges"]
        exclude_ranges = config_kwargs["exclude_ranges"]
        period_times = config_kwargs["period_times"]
        time_matrix_kind = config_kwargs["time_matrix_kind"]
        period_matrices = config_kwargs["period_matrices"]
        root_age = config_kwargs["root_age"]

        model_name = self._normalize_model_name(model_name)
        null_range_mode = normalize_sbgb_null_range_mode(null_range_mode, include_null_range)
        include_null_range = null_range_mode == "include"
        display_model = self._display_model_name(model_name, null_range_mode)

        taxa_order, name_to_index, index_to_name = self._build_global_taxon_order(matrix)
        self._validate_tree_taxa(reference_tree, name_to_index, "reference tree")

        run_dir = self._make_run_dir(model_name)
        reference_nodes = self._build_reference_nodes(reference_tree, name_to_index, index_to_name)
        reference_clades = {node["node_key"]: node for node in reference_nodes}

        result = BioGeoBEARSResult(reference_tree=reference_tree)
        result.model_name = "S-BioGeoBEARS-%s" % display_model
        result.input_tree_count = len(tree_entries)
        result.effective_tree_count = 0
        result.result_note = (
            "Legacy-style S-BGB aggregation; per-tree BioGeoBEARS analyses "
            "are combined only when a sampled-tree clade exactly matches the "
            "reference-tree clade."
        )
        result.model_statistics = {
            "model_name": model_name,
            "display_model_name": display_model,
            "max_range_size": int(max_range_size),
            "include_null_range": bool(include_null_range),
            "null_range_mode": null_range_mode,
            "requested_threads": max(1, int(thread_count or 1)),
            "threads": max(1, int(thread_count or 1)),
            "per_tree_cores": 1,
            "include_ranges": list(include_ranges or []),
            "exclude_ranges": list(exclude_ranges or []),
            "time_matrix_kind": time_matrix_kind,
            "period_times": list(period_times or []),
            "root_age": root_age,
            "scale_tree_to_root_age": bool(root_age),
            "aggregation_mode": "legacy_exact_clade",
        }
        if config is not None:
            result.config = config
        result.run_dir = str(run_dir)
        result.per_tree_result_paths = []
        result.per_tree_engine_result_paths = []

        for node in reference_nodes:
            clade_key = node["node_key"]
            display_id = str(node["display_id"])
            result.reference_node_ids[clade_key] = display_id
            result.node_results[clade_key] = BioGeoBEARSNodeResult(
                node_key=clade_key,
                display_node_id=display_id,
                supporting_tree_count=0,
                total_tree_count=0,
                raw_method_payload={"state_percent_sums": {}},
            )

        global_state_percent_sums = defaultdict(float)
        per_tree_outputs = []
        worker_count = min(max(1, int(thread_count or 1)), len(tree_entries))
        jobs = []
        for idx, entry in enumerate(tree_entries, start=1):
            tree = self._extract_tree(entry)
            self._validate_tree_taxa(tree, name_to_index, "tree %s" % idx)
            run_files = self.biogeobears_service.build_run_files(
                tree=tree,
                matrix=matrix,
                model_name=model_name,
                run_name="%s_%s_t%04d" % (run_name_prefix, run_dir.name, idx),
                max_range_size=max_range_size,
                include_null_range=include_null_range,
                null_range_mode=null_range_mode,
                cores=1,
                include_ranges=include_ranges,
                exclude_ranges=exclude_ranges,
                period_times=period_times,
                time_matrix_kind=time_matrix_kind,
                period_matrices=period_matrices,
                root_age=root_age,
                scale_tree_to_root_age=True,
            )
            jobs.append({"idx": idx, "tree": tree, "run_files": run_files})

        batches = [[] for _ in range(worker_count)]
        for job in jobs:
            batches[(int(job["idx"]) - 1) % worker_count].append(job)
        batches = [batch for batch in batches if batch]
        result.model_statistics["batch_runner"] = True
        result.model_statistics["batch_count"] = len(batches)

        progress_lock = Lock()
        completed_indices = set()

        def mark_tree_completed(idx, message):
            try:
                tree_index = int(idx)
            except Exception:
                return
            with progress_lock:
                if tree_index in completed_indices:
                    return
                completed_indices.add(tree_index)
                completed_count = len(completed_indices)
            self._emit_progress(
                progress_callback,
                completed_count,
                len(tree_entries),
                message,
            )

        def run_one_batch(batch_number, batch_jobs):
            batch_name = "batch_%04d" % batch_number

            def batch_progress(job_id, status, message):
                suffix = "finished" if str(status).upper() == "DONE" else "failed"
                mark_tree_completed(
                    job_id,
                    "S-BGB BioGeoBEARS tree %s/%s %s" % (job_id, len(tree_entries), suffix),
                )

            self.biogeobears_service.run_batch(
                [job["run_files"] for job in batch_jobs],
                batch_workdir=run_dir / batch_name,
                batch_name=batch_name,
                job_ids=[str(job["idx"]) for job in batch_jobs],
                progress_callback=batch_progress,
            )

            parsed = []
            for job in batch_jobs:
                idx = int(job["idx"])
                tree = job["tree"]
                run_files = job["run_files"]
                try:
                    if not run_files.output_json_path.exists():
                        raise FileNotFoundError(
                            "BioGeoBEARS did not produce output JSON: %s" % run_files.output_json_path
                        )
                    per_tree = self.biogeobears_service.parse_run_files(tree=tree, run_files=run_files)
                    parsed.append((idx, tree, per_tree, run_files, None))
                except Exception as exc:
                    parsed.append((idx, tree, None, run_files, str(exc)))
                mark_tree_completed(idx, "S-BGB BioGeoBEARS tree %s/%s finished" % (idx, len(tree_entries)))
            return parsed

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_index = {
                executor.submit(run_one_batch, batch_number, batch): batch
                for batch_number, batch in enumerate(batches, start=1)
            }
            for future in as_completed(future_to_index):
                batch_jobs = future_to_index[future]
                try:
                    for idx, tree, per_tree, run_files, warning in future.result():
                        if warning:
                            result.parse_warnings.append(
                                "Tree %s BioGeoBEARS failed: %s" % (idx, warning)
                            )
                        else:
                            per_tree_outputs.append((idx, tree, per_tree, run_files))
                except Exception as exc:
                    for job in batch_jobs:
                        idx = int(job["idx"])
                        result.parse_warnings.append(
                            "Tree %s BioGeoBEARS batch failed: %s" % (idx, exc)
                        )
                        mark_tree_completed(
                            idx,
                            "S-BGB BioGeoBEARS tree %s/%s failed" % (idx, len(tree_entries)),
                        )

        effective_count = 0
        for idx, tree, per_tree, run_files in sorted(per_tree_outputs, key=lambda item: item[0]):
            effective_count += 1
            intermediate_path = self._write_per_tree_intermediate(
                run_dir=run_dir,
                tree_index=idx,
                tree=tree,
                per_tree=per_tree,
                model_display=display_model,
                matrix=matrix,
                taxa_order=taxa_order,
                name_to_index=name_to_index,
                index_to_name=index_to_name,
            )
            result.per_tree_result_paths.append(str(intermediate_path))

            per_tree_note = str(getattr(per_tree, "result_note", "") or "")
            workdir = self._extract_workdir_from_note(per_tree_note)
            if workdir:
                result.per_tree_engine_result_paths.append(workdir)
            else:
                result.per_tree_engine_result_paths.append(str(run_files.workdir))

            per_tree_results = dict(getattr(per_tree, "node_results", {}) or {})
            for clade_key, reference_node in reference_clades.items():
                source_clade_key = self._find_source_mrca_clade_key(
                    tree,
                    reference_node.get("tip_names", []),
                )
                if not source_clade_key:
                    continue
                if source_clade_key != clade_key:
                    aggregate = result.node_results[clade_key]
                    aggregate.raw_method_payload["skipped_nonmatching_clade_count"] = (
                        aggregate.raw_method_payload.get("skipped_nonmatching_clade_count", 0) + 1
                    )
                    continue

                bgb_node = per_tree_results.get(clade_key)
                if bgb_node is None:
                    aggregate = result.node_results[clade_key]
                    aggregate.raw_method_payload["missing_exact_clade_result_count"] = (
                        aggregate.raw_method_payload.get("missing_exact_clade_result_count", 0) + 1
                    )
                    continue

                aggregate = result.node_results[clade_key]
                aggregate.supporting_tree_count += 1

                percentages = self._extract_state_percentages(bgb_node)
                state_percent_sums = aggregate.raw_method_payload.setdefault("state_percent_sums", {})
                source_clade_counts = aggregate.raw_method_payload.setdefault("source_clade_counts", {})
                source_clade_counts[source_clade_key] = source_clade_counts.get(source_clade_key, 0) + 1
                for state, percent in percentages.items():
                    state_percent_sums[state] = state_percent_sums.get(state, 0.0) + percent
                    global_state_percent_sums[state] += percent

        if effective_count == 0:
            raise RuntimeError("S-BGB run failed: all per-tree BioGeoBEARS analyses failed.")

        result.effective_tree_count = effective_count
        result.model_statistics["effective_tree_count"] = effective_count
        result.model_statistics["input_tree_count"] = len(tree_entries)

        self._finalize_node_results(result, effective_count, global_state_percent_sums)

        analysis_log = self._write_analysis_log(
            run_dir=run_dir,
            result=result,
            taxa_order=taxa_order,
            matrix=matrix,
            reference_numeric_newick=self._build_numeric_newick(reference_tree, name_to_index) + ";",
        )
        result.analysis_log_path = str(analysis_log)
        return result

    def _finalize_node_results(self, result, effective_count, global_state_percent_sums) -> None:
        result.state_order = [
            state
            for state, _weight in sorted(global_state_percent_sums.items(), key=lambda x: (-x[1], x[0]))
        ]
        result.state_colors = {}
        palette_index = 0
        for state in result.state_order:
            if state == "/":
                result.state_colors[state] = "#ffffff"
            elif state == "*":
                result.state_colors[state] = "#000000"
            else:
                result.state_colors[state] = self.PALETTE[palette_index % len(self.PALETTE)]
                palette_index += 1

        for node_result in result.node_results.values():
            node_result.total_tree_count = effective_count
            state_percent_sums = dict(node_result.raw_method_payload.get("state_percent_sums", {}) or {})

            if node_result.supporting_tree_count <= 0 or not state_percent_sums:
                node_result.states = []
                node_result.state_supports = {}
                node_result.pie_labels = []
                node_result.pie_percents = []
                node_result.pie_colors = []
                node_result.event_summary = "supporting trees 0/%s" % effective_count
                continue

            supports = {}
            for state, percent_sum in state_percent_sums.items():
                supports[state] = float(percent_sum) / float(node_result.supporting_tree_count)

            ordered = sorted(supports.items(), key=lambda x: (-x[1], x[0]))
            node_result.state_supports = dict(ordered)
            node_result.states = [state for state, _value in ordered]
            node_result.pie_labels = list(node_result.states)
            node_result.pie_percents = [value for _state, value in ordered]
            node_result.pie_colors = [
                result.state_colors.get(label, "#808080")
                for label in node_result.pie_labels
            ]
            node_result.event_summary = "supporting trees %s/%s" % (
                node_result.supporting_tree_count,
                effective_count,
            )
            node_result.raw_method_payload.update(
                {
                    "supporting_tree_count": node_result.supporting_tree_count,
                    "total_tree_count": node_result.total_tree_count,
                    "state_supports": dict(ordered),
                }
            )

        if result.parse_warnings:
            result.result_note += " effective_trees=%s/%s" % (
                effective_count,
                result.input_tree_count,
            )
        else:
            result.result_note += " effective_trees=%s" % effective_count

    def _write_per_tree_intermediate(
        self,
        *,
        run_dir: Path,
        tree_index: int,
        tree,
        per_tree,
        model_display: str,
        matrix,
        taxa_order: List[str],
        name_to_index: Dict[str, int],
        index_to_name: Dict[int, str],
    ) -> Path:
        lines = [
            "BioGeoBEARS result file of S-BGB",
            "[TAXON]",
        ]
        by_name = {str(row.get("Name", "")).strip(): row for row in list(getattr(matrix, "rows", []) or [])}
        state_columns = self._state_columns(matrix)
        for idx, name in enumerate(taxa_order, start=1):
            row = by_name.get(name, {})
            lines.append("%s\t%s\t%s" % (idx, name, self._row_to_distribution(row, state_columns)))

        lines.extend(
            [
                "[TREE]",
                "Tree=" + self._build_numeric_newick(tree, name_to_index) + ";",
                "[RESULT]",
                "%s results:" % model_display,
            ]
        )

        tree_nodes = self._build_reference_nodes(tree, name_to_index, index_to_name)
        per_tree_results = dict(getattr(per_tree, "node_results", {}) or {})
        for node in tree_nodes:
            node_key = node["node_key"]
            percentages = self._extract_state_percentages(per_tree_results.get(node_key))
            parts = []
            for state, percent in sorted(percentages.items(), key=lambda x: (-x[1], x[0])):
                parts.append(" %s %.6f" % (state, float(percent)))
            lines.append("node %s:%s" % (node["display_id"], "".join(parts)))

        path = run_dir / ("rasp_result.%s.BGB.txt" % tree_index)
        return self._write_text(path, "\n".join(lines) + "\n")

    def _write_analysis_log(
        self,
        *,
        run_dir: Path,
        result,
        taxa_order: List[str],
        matrix,
        reference_numeric_newick: str,
    ) -> Path:
        lines = [
            "Combined result file",
            "[TAXON]",
        ]
        by_name = {str(row.get("Name", "")).strip(): row for row in list(getattr(matrix, "rows", []) or [])}
        state_columns = self._state_columns(matrix)
        for idx, name in enumerate(taxa_order, start=1):
            row = by_name.get(name, {})
            lines.append("%s\t%s\t%s" % (idx, name, self._row_to_distribution(row, state_columns)))

        lines.extend(
            [
                "[TREE]",
                "Tree=" + reference_numeric_newick,
                "[RESULT]",
                "%s results:" % str(getattr(result, "model_name", "") or "S-BGB"),
            ]
        )

        ref_map = dict(getattr(result, "reference_node_ids", {}) or {})
        for node_key, node_result in result.node_results.items():
            display_id = ref_map.get(node_key, "")
            parts = []
            for state in node_result.states:
                parts.append(" %s %.2f" % (state, float(node_result.state_supports.get(state, 0.0))))
            lines.append("node %s:%s" % (display_id, "".join(parts)))

        return self._write_text(run_dir / "analysis_result.log", "\n".join(lines) + "\n")

    def _extract_tree(self, entry):
        for attr in ("tree", "ete_tree", "parsed_tree", "tree_obj"):
            if hasattr(entry, attr):
                value = getattr(entry, attr)
                if value is not None:
                    return value

        if hasattr(entry, "get_leaf_names"):
            return entry

        raise ValueError("Tree entry does not contain a usable tree object.")

    def _build_reference_nodes(self, tree, name_to_index: Dict[str, int], index_to_name: Dict[int, str]) -> List[dict]:
        nodes = []
        taxon_count = len(name_to_index)
        counter = 0
        for node in tree.traverse("postorder"):
            if node.is_leaf():
                continue
            counter += 1
            indices = [str(name_to_index[str(leaf.name).strip()]) for leaf in node.iter_leaves()]
            names = [index_to_name[int(x)] for x in indices]
            nodes.append(
                {
                    "node_key": "|".join(sorted(names)),
                    "display_id": taxon_count + counter,
                    "tip_names": sorted(names),
                }
            )
        return nodes

    def _find_source_mrca_clade_key(self, tree, tip_names) -> str:
        names = [str(name).strip() for name in list(tip_names or []) if str(name).strip()]
        if not names or tree is None or not hasattr(tree, "get_common_ancestor"):
            return ""

        try:
            node = tree.get_common_ancestor(names)
        except Exception:
            return ""

        try:
            return "|".join(sorted(str(leaf.name).strip() for leaf in node.iter_leaves()))
        except Exception:
            return ""

    def _build_global_taxon_order(self, matrix):
        rows = list(getattr(matrix, "rows", []) or [])
        taxa_order = []
        for row in rows:
            name = str(row.get("Name", "")).strip()
            if not name:
                raise ValueError("S-BGB run failed: matrix contains an empty Name.")
            if name in taxa_order:
                raise ValueError("S-BGB run failed: duplicate taxon in matrix: %s" % name)
            taxa_order.append(name)

        if not taxa_order:
            raise ValueError("S-BGB run failed: matrix has no taxa.")

        name_to_index = {name: idx for idx, name in enumerate(taxa_order, start=1)}
        index_to_name = {idx: name for name, idx in name_to_index.items()}
        return taxa_order, name_to_index, index_to_name

    def _validate_tree_taxa(self, tree, name_to_index: Dict[str, int], label: str) -> None:
        if tree is None or not hasattr(tree, "iter_leaves"):
            raise ValueError("S-BGB run failed: %s is not a usable tree." % label)

        leaf_names = {str(leaf.name).strip() for leaf in tree.iter_leaves()}
        matrix_names = set(name_to_index.keys())
        missing = sorted(matrix_names - leaf_names)
        extra = sorted(leaf_names - matrix_names)
        if missing or extra:
            parts = ["S-BGB run failed: %s taxa do not match matrix." % label]
            if missing:
                parts.append("Missing in tree: %s" % ", ".join(missing[:20]))
            if extra:
                parts.append("Extra in tree: %s" % ", ".join(extra[:20]))
            raise ValueError(" ".join(parts))

    def _extract_state_percentages(self, bgb_node) -> Dict[str, float]:
        if bgb_node is None:
            return {}

        labels = list(getattr(bgb_node, "pie_labels", []) or [])
        percents = list(getattr(bgb_node, "pie_percents", []) or [])

        if labels and percents and len(labels) == len(percents):
            return {
                label: float(percent)
                for label, percent in zip(labels, percents)
            }

        supports = dict(getattr(bgb_node, "state_supports", {}) or {})
        if supports:
            return {k: float(v) for k, v in supports.items()}

        states = list(getattr(bgb_node, "states", []) or [])
        if states:
            percent = 100.0 / float(len(states))
            return {state: percent for state in states}

        return {}

    def _state_columns(self, matrix) -> List[str]:
        return [
            str(col).strip()
            for col in list(getattr(matrix, "state_columns", []) or [])
            if str(col).strip() and str(col).strip() not in ("ID", "Name")
        ]

    def _row_to_distribution(self, row, state_columns: List[str]) -> str:
        parts = []
        for col in state_columns:
            value = str(row.get(col, "")).strip()
            if value and value not in ("0", "False", "false"):
                if value in ("1", "True", "true"):
                    parts.append(col)
                else:
                    parts.append(value)
        return "".join(parts)

    def _build_numeric_newick(self, tree, name_to_index: Dict[str, int]) -> str:
        def visit(node):
            if node.is_leaf():
                return str(name_to_index[str(node.name).strip()])
            return "(" + ",".join(visit(child) for child in node.children) + ")"

        return visit(tree)

    def _normalize_model_name(self, model_name: str) -> str:
        value = str(model_name or "DEC").upper().replace("+", "")
        if value == "DECJ":
            return "DECJ"
        if value == "DIVALIKEJ":
            return "DIVALIKEJ"
        if value == "BAYAREALIKEJ":
            return "BAYAREALIKEJ"
        if value in self.MODEL_DISPLAY_NAMES:
            return value
        raise ValueError("Unsupported S-BGB BioGeoBEARS model: %s" % model_name)

    def _display_model_name(self, model_name: str, null_range_mode: str) -> str:
        base = self.MODEL_DISPLAY_NAMES.get(model_name, model_name)
        if null_range_mode == "exclude":
            return "%s (no null range)" % base
        return base

    def _extract_workdir_from_note(self, note: str) -> str:
        marker = "workdir="
        if marker not in note:
            return ""
        return note.split(marker, 1)[1].strip()

    def _emit_progress(self, progress_callback, completed: int, total: int, message: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(int(completed), int(total), str(message))
        except Exception:
            pass

    def _make_run_dir(self, model_name: str) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run_dir = self.project_root / "runs" / "sbgb" / ("legacy_sbgb_%s_%s" % (model_name.lower(), stamp))
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _write_text(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

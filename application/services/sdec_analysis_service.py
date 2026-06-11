from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from domain.models.sdec_result import SDECResult, SDECNodeResult


class SDECAnalysisService:
    """
    Legacy-style S-DEC coordinator.

    Old RASP runs Lagrange once per tree, converts each result into a RASP
    intermediate DEC file, then combines those intermediates by matching clades
    against the reference tree.  The current project intentionally uses
    lagrange-ng.exe instead of the old Lagrange_Win.exe/LAGDLL backend, so this
    class follows the old orchestration and aggregation semantics while leaving
    the per-tree DEC calculation to the configured DECAnalysisService.
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

    def __init__(self, dec_service, project_root=None):
        self.dec_service = dec_service
        if project_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent
        self.project_root = Path(project_root)

    def analyze(
        self,
        *,
        reference_tree,
        matrix,
        tree_entries,
        run_name_prefix="sdec",
        config=None,
        progress_callback=None,
    ):
        tree_entries = list(tree_entries or [])
        if not tree_entries:
            raise ValueError("S-DEC run failed: no tree-set input is available.")
        if reference_tree is None:
            raise ValueError("S-DEC run failed: reference tree is required.")
        if matrix is None:
            raise ValueError("S-DEC run failed: matrix is required.")

        if config is not None:
            config_values = config.builder_kwargs()
            outer_workers = max(1, int(config_values["workers"] or 1))
            native_range_constraint_warnings = list(
                config_values.get("native_range_constraint_warnings", []) or []
            )
            native_range_constraints_active = bool(
                self._has_period_area_bits(config_values.get("period_include_area_bits"))
                or self._has_period_area_bits(config_values.get("period_exclude_area_bits"))
            )
        else:
            raise ValueError("S-DEC analysis requires an S-DEC config object.")

        taxa_order, name_to_index, index_to_name = self._build_global_taxon_order(matrix)
        self._validate_tree_taxa(reference_tree, name_to_index, "reference tree")

        run_dir = self._make_run_dir()
        reference_nodes = self._build_reference_nodes(reference_tree, name_to_index, index_to_name)
        reference_clades = {node["node_key"]: node for node in reference_nodes}

        result = SDECResult(reference_tree=reference_tree)
        result.input_tree_count = len(tree_entries)
        result.result_note = (
            "S-DEC aggregation; per-tree DEC is computed by lagrange-ng.exe."
        )
        if native_range_constraints_active:
            result.result_note += " native_range_constraints=lagrange-ng-period-area-mask"
        result.run_dir = str(run_dir)
        result.per_tree_result_paths = []
        result.config = config
        result.parse_warnings.extend(native_range_constraint_warnings)

        for node in reference_nodes:
            clade_key = node["node_key"]
            display_id = str(node["display_id"])
            result.reference_node_ids[clade_key] = display_id
            result.node_results[clade_key] = SDECNodeResult(
                node_key=clade_key,
                display_node_id=display_id,
            )

        global_state_percent_sums = defaultdict(float)
        effective_count = 0

        per_tree_runs = self._run_per_tree_dec_jobs(
            tree_entries=tree_entries,
            matrix=matrix,
            name_to_index=name_to_index,
            run_name_prefix=run_name_prefix,
            config=config,
            outer_workers=outer_workers,
            progress_callback=progress_callback,
        )

        for run in per_tree_runs:
            idx = run["tree_index"]
            if run.get("error"):
                result.parse_warnings.append("Tree %s DEC failed: %s" % (idx, run["error"]))
                continue

            tree = run["tree"]
            per_tree = run["per_tree"]
            effective_count += 1
            intermediate_path = self._write_per_tree_intermediate(
                run_dir=run_dir,
                tree_index=idx,
                tree=tree,
                per_tree=per_tree,
                matrix=matrix,
                taxa_order=taxa_order,
                name_to_index=name_to_index,
                index_to_name=index_to_name,
            )
            result.per_tree_result_paths.append(str(intermediate_path))

            for clade_key, dec_node in dict(getattr(per_tree, "node_results", {}) or {}).items():
                if clade_key not in reference_clades:
                    continue

                aggregate = result.node_results[clade_key]
                aggregate.supporting_tree_count += 1

                percentages = self._extract_state_percentages(dec_node)
                for state, percent in percentages.items():
                    aggregate.state_weights[state] = aggregate.state_weights.get(state, 0.0) + percent
                    global_state_percent_sums[state] += percent

        if effective_count == 0:
            raise RuntimeError("S-DEC run failed: all per-tree DEC analyses failed.")

        result.effective_tree_count = effective_count
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

    def _run_per_tree_dec_jobs(
        self,
        *,
        tree_entries,
        matrix,
        name_to_index,
        run_name_prefix,
        config,
        outer_workers,
        progress_callback=None,
    ) -> List[dict]:
        jobs = list(enumerate(tree_entries, start=1))
        if max(1, int(outer_workers or 1)) <= 1:
            results = []
            for done, (idx, entry) in enumerate(jobs, start=1):
                item = self._run_one_tree_dec(
                    idx=idx,
                    entry=entry,
                    matrix=matrix,
                    name_to_index=name_to_index,
                    run_name_prefix=run_name_prefix,
                    config=config,
                )
                results.append(item)
                self._emit_progress(progress_callback, done, len(jobs), item)
            return results

        results = []
        with ThreadPoolExecutor(max_workers=max(1, int(outer_workers or 1))) as executor:
            futures = [
                executor.submit(
                    self._run_one_tree_dec,
                    idx=idx,
                    entry=entry,
                    matrix=matrix,
                    name_to_index=name_to_index,
                    run_name_prefix=run_name_prefix,
                    config=config,
                )
                for idx, entry in jobs
            ]
            for future in as_completed(futures):
                item = future.result()
                results.append(item)
                self._emit_progress(progress_callback, len(results), len(jobs), item)
        return sorted(results, key=lambda item: item["tree_index"])

    def _emit_progress(self, progress_callback, done, total, item):
        if progress_callback is None:
            return
        idx = int(item.get("tree_index", done) or done)
        if item.get("error"):
            text = "S-DEC tree %s/%s failed" % (idx, total)
        else:
            text = "S-DEC tree %s/%s finished" % (idx, total)
        progress_callback(int(done), int(total), text)

    def _run_one_tree_dec(
        self,
        *,
        idx,
        entry,
        matrix,
        name_to_index,
        run_name_prefix,
        config,
    ) -> dict:
        try:
            tree = self._extract_tree(entry)
            self._validate_tree_taxa(tree, name_to_index, "tree %s" % idx)
            tree_config = copy.deepcopy(config) if config is not None else None
            if tree_config is not None:
                tree_config.threads = 1
            per_tree = self.dec_service.analyze(
                tree=tree,
                matrix=matrix,
                run_name="%s_t%04d" % (run_name_prefix, idx),
                scale_tree_to_root_age=True,
                config=tree_config,
                runner_env_overrides=self._per_tree_dec_env_overrides(),
            )
            return {
                "tree_index": idx,
                "tree": tree,
                "per_tree": per_tree,
                "error": "",
            }
        except Exception as exc:
            return {
                "tree_index": idx,
                "tree": None,
                "per_tree": None,
                "error": str(exc),
            }

    def _per_tree_dec_env_overrides(self) -> dict:
        return {
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }

    def _finalize_node_results(self, result, effective_count, global_state_percent_sums) -> None:
        result.state_order = [
            state
            for state, _weight in sorted(global_state_percent_sums.items(), key=lambda x: (-x[1], x[0]))
        ]
        result.state_colors = {
            state: self.PALETTE[i % len(self.PALETTE)]
            for i, state in enumerate(result.state_order)
        }

        for node_result in result.node_results.values():
            node_result.total_tree_count = effective_count

            if node_result.supporting_tree_count <= 0 or not node_result.state_weights:
                node_result.states = []
                node_result.state_supports = {}
                node_result.pie_labels = []
                node_result.pie_percents = []
                node_result.pie_colors = []
                node_result.event_summary = "supporting trees 0/%s" % effective_count
                continue

            supports = {}
            for state, percent_sum in node_result.state_weights.items():
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
            node_result.raw_method_payload = {
                "supporting_tree_count": node_result.supporting_tree_count,
                "total_tree_count": node_result.total_tree_count,
                "state_supports": dict(ordered),
            }

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
        matrix,
        taxa_order: List[str],
        name_to_index: Dict[str, int],
        index_to_name: Dict[int, str],
    ) -> Path:
        lines = [
            "DEC result file of S-DEC",
            "[TAXON]",
        ]
        by_name = {str(row.get("Name", "")).strip(): row for row in list(getattr(matrix, "rows", []) or [])}
        state_columns = self._state_columns(matrix)
        for idx, name in enumerate(taxa_order, start=1):
            row = by_name.get(name, {})
            lines.append("%s\t%s\t%s" % (idx, name, self._row_to_distribution(row, state_columns)))

        lines.extend([
            "[TREE]",
            "Tree=" + self._build_numeric_newick(tree, name_to_index) + ";",
            "[RESULT]",
            "DEC results:",
        ])

        tree_nodes = self._build_reference_nodes(tree, name_to_index, index_to_name)
        per_tree_results = dict(getattr(per_tree, "node_results", {}) or {})
        for node in tree_nodes:
            node_key = node["node_key"]
            percentages = self._extract_state_percentages(per_tree_results.get(node_key))
            parts = []
            for state, percent in sorted(percentages.items(), key=lambda x: (-x[1], x[0])):
                parts.append(" %s %.2f" % (state, float(percent)))
            lines.append("node %s (LR):%s" % (node["display_id"], "".join(parts)))

        path = run_dir / ("rasp_result.%s.DEC.txt" % tree_index)
        return self._write_text(path, "\n".join(lines) + "\n")

    def _has_period_area_bits(self, value) -> bool:
        if isinstance(value, str):
            return "1" in value
        return any("1" in str(item or "") for item in list(value or []))

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

        lines.extend([
            "[TREE]",
            "Tree=" + reference_numeric_newick,
            "[RESULT]",
            "SDEC results:",
        ])

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
                    "legacy_clade": self._legacy_clade(indices),
                    "node_key": "|".join(sorted(names)),
                    "display_id": taxon_count + counter,
                }
            )
        return nodes

    def _build_global_taxon_order(self, matrix):
        rows = list(getattr(matrix, "rows", []) or [])
        taxa_order = []
        for row in rows:
            name = str(row.get("Name", "")).strip()
            if not name:
                raise ValueError("S-DEC run failed: matrix contains an empty Name.")
            if name in taxa_order:
                raise ValueError("S-DEC run failed: duplicate taxon in matrix: %s" % name)
            taxa_order.append(name)

        if not taxa_order:
            raise ValueError("S-DEC run failed: matrix has no taxa.")

        name_to_index = {name: idx for idx, name in enumerate(taxa_order, start=1)}
        index_to_name = {idx: name for name, idx in name_to_index.items()}
        return taxa_order, name_to_index, index_to_name

    def _validate_tree_taxa(self, tree, name_to_index: Dict[str, int], label: str) -> None:
        if tree is None or not hasattr(tree, "iter_leaves"):
            raise ValueError("S-DEC run failed: %s is not a usable tree." % label)

        leaf_names = {str(leaf.name).strip() for leaf in tree.iter_leaves()}
        matrix_names = set(name_to_index.keys())
        missing = sorted(matrix_names - leaf_names)
        extra = sorted(leaf_names - matrix_names)
        if missing or extra:
            parts = ["S-DEC run failed: %s taxa do not match matrix." % label]
            if missing:
                parts.append("Missing in tree: %s" % ", ".join(missing[:20]))
            if extra:
                parts.append("Extra in tree: %s" % ", ".join(extra[:20]))
            raise ValueError(" ".join(parts))

    def _extract_state_percentages(self, dec_node) -> Dict[str, float]:
        if dec_node is None:
            return {}

        labels = list(getattr(dec_node, "pie_labels", []) or [])
        percents = list(getattr(dec_node, "pie_percents", []) or [])

        if labels and percents and len(labels) == len(percents):
            return {
                label: float(percent)
                for label, percent in zip(labels, percents)
            }

        supports = dict(getattr(dec_node, "state_supports", {}) or {})
        if supports:
            return {k: float(v) for k, v in supports.items()}

        states = list(getattr(dec_node, "states", []) or [])
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

    def _legacy_clade(self, values) -> str:
        clean = [str(value).strip() for value in values if str(value).strip()]
        return "#" + "#".join(sorted(clean, key=lambda x: int(x) if x.isdigit() else x)) + "#"

    def _make_run_dir(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run_dir = self.project_root / "runs" / "sdec" / ("sdec_%s" % stamp)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _write_text(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

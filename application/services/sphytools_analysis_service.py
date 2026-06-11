import copy
import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from domain.models.biogeobears_result import BioGeoBEARSNodeResult, BioGeoBEARSResult
from domain.models.continuous_trait_result import ContinuousTraitNodeResult, ContinuousTraitResult
from domain.models.phytools_config import (
    PHYTOOLS_CONTINUOUS_METHODS,
    PHYTOOLS_DISCRETE_METHODS,
    phytools_method_kind,
)


class SPhytoolsAnalysisService:
    PALETTE = [
        "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
        "#ffff33", "#a65628", "#f781bf", "#999999", "#66c2a5",
        "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854", "#ffd92f",
        "#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e",
    ]

    def __init__(self, phytools_service, work_root=None):
        self.phytools_service = phytools_service
        if work_root is None:
            work_root = Path("runs") / "sphytools"
        self.work_root = Path(work_root)

    def analyze(
        self,
        *,
        reference_tree,
        matrix,
        tree_entries,
        config,
        run_name_prefix="sphytools",
        progress_callback=None,
    ):
        if reference_tree is None:
            raise ValueError("S-phytools requires a reference/consensus tree.")
        if matrix is None:
            raise ValueError("S-phytools requires a trait matrix.")
        tree_entries = [
            entry for entry in list(tree_entries or [])
            if getattr(entry, "parsed_tree", None) is not None
        ]
        if not tree_entries:
            raise ValueError("S-phytools requires an imported tree set with prepared trees.")
        if config is None:
            raise ValueError("S-phytools config is required.")
        config.validate()

        method_kind = phytools_method_kind(config.method)
        run_label = "S-phytools" if method_kind == "continuous" else "S-ape"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_name_prefix = "%s_%s" % (str(run_name_prefix or "sphytools"), stamp)
        worker_count = min(max(1, int(getattr(config, "threads", 1) or 1)), len(tree_entries))

        reference_records = self.phytools_service.dataset_builder.build_node_records(reference_tree)
        reference_by_clade = {
            str(record.get("clade_key", "")): record
            for record in reference_records
            if str(record.get("clade_key", ""))
        }

        per_tree_runs = self._run_per_tree_jobs(
            tree_entries=tree_entries,
            matrix=matrix,
            config=config,
            run_name_prefix=run_name_prefix,
            worker_count=worker_count,
            progress_callback=progress_callback,
            run_label=run_label,
        )

        if method_kind == "continuous":
            return self._aggregate_continuous(
                reference_tree=reference_tree,
                reference_by_clade=reference_by_clade,
                tree_entries=tree_entries,
                per_tree_runs=per_tree_runs,
                config=config,
                worker_count=worker_count,
            )
        return self._aggregate_discrete(
            reference_tree=reference_tree,
            reference_by_clade=reference_by_clade,
            tree_entries=tree_entries,
            per_tree_runs=per_tree_runs,
            config=config,
            worker_count=worker_count,
        )

    def _run_per_tree_jobs(
        self,
        *,
        tree_entries,
        matrix,
        config,
        run_name_prefix,
        worker_count,
        progress_callback,
        run_label,
    ):
        jobs = list(enumerate(tree_entries, start=1))
        if worker_count <= 1:
            results = []
            for idx, entry in jobs:
                item = self._run_one_tree(
                    idx=idx,
                    entry=entry,
                    matrix=matrix,
                    config=config,
                    run_name_prefix=run_name_prefix,
                )
                results.append(item)
                self._emit_progress(progress_callback, len(results), len(jobs), item, run_label)
            return results

        results = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(
                    self._run_one_tree,
                    idx=idx,
                    entry=entry,
                    matrix=matrix,
                    config=config,
                    run_name_prefix=run_name_prefix,
                )
                for idx, entry in jobs
            ]
            for future in as_completed(futures):
                item = future.result()
                results.append(item)
                self._emit_progress(progress_callback, len(results), len(jobs), item, run_label)
        return sorted(results, key=lambda item: int(item.get("tree_index", 0) or 0))

    def _run_one_tree(self, *, idx, entry, matrix, config, run_name_prefix):
        tree = getattr(entry, "parsed_tree", None)
        try:
            tree_config = copy.deepcopy(config)
            tree_config.threads = 1
            result = self.phytools_service.analyze(
                tree=tree,
                matrix=matrix,
                config=tree_config,
                run_name="%s_t%04d" % (run_name_prefix, idx),
            )
            return {
                "tree_index": idx,
                "tree": tree,
                "result": result,
                "error": "",
            }
        except Exception as exc:
            return {
                "tree_index": idx,
                "tree": tree,
                "result": None,
                "error": str(exc),
            }

    def _emit_progress(self, progress_callback, done, total, item, run_label):
        if progress_callback is None:
            return
        idx = int(item.get("tree_index", done) or done)
        if item.get("error"):
            text = "%s tree %s/%s failed" % (run_label, idx, total)
        else:
            text = "%s tree %s/%s finished" % (run_label, idx, total)
        progress_callback(int(done), int(total), text)

    def _aggregate_continuous(
        self,
        *,
        reference_tree,
        reference_by_clade,
        tree_entries,
        per_tree_runs,
        config,
        worker_count,
    ):
        result = ContinuousTraitResult(reference_tree=reference_tree)
        method_label = PHYTOOLS_CONTINUOUS_METHODS.get(str(config.method), str(config.method))
        result.model_name = "S-%s" % method_label.replace("Continuous: ", "phytools ")
        result.input_tree_count = len(tree_entries)
        result.trait_name = str(config.trait_column or "")
        result.trait_transform = str(config.continuous_transform or "none")
        result.trait_display_scale = "original" if result.trait_transform != "none" else "analysis"
        result.trait_plot_scale = "analysis"
        result.result_note = (
            "S-phytools aggregates %s estimates from each sampled tree by exact reference clade matching."
            % method_label
        )
        result.config = config

        samples_by_clade = defaultdict(list)
        first_success = None
        effective_count = 0
        for run in per_tree_runs:
            if run.get("error"):
                result.parse_warnings.append("Tree %s phytools failed: %s" % (run.get("tree_index"), run.get("error")))
                continue
            per_tree = run.get("result")
            if per_tree is None:
                continue
            effective_count += 1
            if first_success is None:
                first_success = per_tree
            for clade_key, node_result in dict(getattr(per_tree, "node_results", {}) or {}).items():
                if clade_key in reference_by_clade:
                    samples_by_clade[clade_key].append(float(getattr(node_result, "mean", 0.0) or 0.0))

        if effective_count == 0:
            raise RuntimeError("S-phytools run failed: all per-tree phytools analyses failed.")
        result.effective_tree_count = effective_count

        if first_success is not None:
            result.tip_values = dict(getattr(first_success, "tip_values", {}) or {})
            result.original_tip_values = dict(getattr(first_success, "original_tip_values", {}) or {})
            result.plot_tip_values = dict(getattr(first_success, "plot_tip_values", {}) or {})

        for clade_key, record in reference_by_clade.items():
            samples = list(samples_by_clade.get(clade_key, []) or [])
            if not samples:
                continue
            samples.sort()
            mean_value = sum(samples) / float(len(samples))
            median_value = self._percentile(samples, 50.0)
            lower95 = self._percentile(samples, 2.5)
            upper95 = self._percentile(samples, 97.5)
            minimum = samples[0]
            maximum = samples[-1]
            original_mean = self._back_transform_value(mean_value, result.trait_transform)

            node_result = ContinuousTraitNodeResult(
                node_key=clade_key,
                display_node_id=str(record.get("display_node_id", "") or ""),
                trait_name=result.trait_name,
                mean=mean_value,
                median=median_value,
                lower95=lower95,
                upper95=upper95,
                minimum=minimum,
                maximum=maximum,
                sample_count=len(samples),
                raw_samples=samples,
                raw_method_payload={
                    "method": "S-phytools fastAnc",
                    "phytools_method": str(config.method),
                    "phytools_method_label": method_label,
                    "trait_name": result.trait_name,
                    "trait_transform": result.trait_transform,
                    "terminal_span": str(record.get("terminal_span", "") or ""),
                    "supporting_tree_count": len(samples),
                    "effective_tree_count": effective_count,
                    "display_scale": self._scale_label(result.trait_display_scale, result.trait_transform),
                    "plot_scale": self._scale_label(result.trait_plot_scale, result.trait_transform),
                    "analysis_mean": mean_value,
                    "analysis_median": median_value,
                    "analysis_lower95": lower95,
                    "analysis_upper95": upper95,
                    "original_mean": original_mean,
                    "original_median": self._back_transform_value(median_value, result.trait_transform),
                    "original_lower95": self._back_transform_value(lower95, result.trait_transform),
                    "original_upper95": self._back_transform_value(upper95, result.trait_transform),
                    "display_mean": original_mean if result.trait_display_scale == "original" else mean_value,
                    "plot_mean": mean_value,
                },
            )
            result.node_results[clade_key] = node_result
            result.reference_node_ids[clade_key] = str(record.get("display_node_id", "") or "")
            result.analysis_node_values[clade_key] = mean_value
            result.original_node_values[clade_key] = original_mean
            result.plot_node_values[clade_key] = mean_value

        values = list(result.plot_tip_values.values()) + list(result.plot_node_values.values())
        if values:
            result.color_scale_min = min(values)
            result.color_scale_max = max(values)
        result.model_statistics = {
            "model_name": "S-phytools",
            "phytools_method": str(config.method),
            "phytools_method_label": method_label,
            "trait_column": result.trait_name,
            "trait_transform": result.trait_transform,
            "input_tree_count": len(tree_entries),
            "effective_tree_count": effective_count,
            "threads": worker_count,
            "aggregation": "exact_reference_clade_match",
        }
        if not result.node_results:
            result.parse_warnings.append("S-phytools found no internal clades shared with the reference tree.")
        return result

    def _aggregate_discrete(
        self,
        *,
        reference_tree,
        reference_by_clade,
        tree_entries,
        per_tree_runs,
        config,
        worker_count,
    ):
        result = BioGeoBEARSResult(reference_tree=reference_tree)
        result.model_name = "S-ape ace"
        result.input_tree_count = len(tree_entries)
        result.result_note = (
            "S-ape aggregates ape::ace ancestral trait-state probabilities from each sampled tree "
            "by exact reference clade matching."
        )
        result.config = config

        state_order = []
        state_sums_by_clade = defaultdict(lambda: defaultdict(float))
        supporting_by_clade = defaultdict(int)
        effective_count = 0
        for run in per_tree_runs:
            if run.get("error"):
                result.parse_warnings.append("Tree %s phytools failed: %s" % (run.get("tree_index"), run.get("error")))
                continue
            per_tree = run.get("result")
            if per_tree is None:
                continue
            effective_count += 1
            for state in list(getattr(per_tree, "state_order", []) or []):
                state = str(state)
                if state and state not in state_order:
                    state_order.append(state)
            for clade_key, node_result in dict(getattr(per_tree, "node_results", {}) or {}).items():
                if clade_key not in reference_by_clade:
                    continue
                supporting_by_clade[clade_key] += 1
                for state, percent in dict(getattr(node_result, "state_supports", {}) or {}).items():
                    state_sums_by_clade[clade_key][str(state)] += float(percent)

        if effective_count == 0:
            raise RuntimeError("S-phytools run failed: all per-tree phytools analyses failed.")
        result.effective_tree_count = effective_count
        result.state_order = state_order
        result.state_colors = {
            state: self.PALETTE[i % len(self.PALETTE)]
            for i, state in enumerate(state_order)
        }

        for clade_key, record in reference_by_clade.items():
            supporting = int(supporting_by_clade.get(clade_key, 0) or 0)
            if supporting <= 0:
                continue
            probabilities = {}
            for state in state_order:
                probabilities[state] = float(state_sums_by_clade[clade_key].get(state, 0.0)) / float(supporting)
            total = sum(float(v) for v in probabilities.values())
            if total > 0:
                probabilities = {state: float(value) * 100.0 / total for state, value in probabilities.items()}
            labels = list(probabilities.keys())
            node_result = BioGeoBEARSNodeResult(
                node_key=clade_key,
                display_node_id=str(record.get("display_node_id", "") or ""),
                states=labels,
                state_supports=dict(probabilities),
                pie_labels=labels,
                pie_percents=[probabilities[state] for state in labels],
                pie_colors=[result.state_colors.get(state, "#808080") for state in labels],
                supporting_tree_count=supporting,
                total_tree_count=effective_count,
                event_summary="S-ape ace ancestral trait-state probabilities",
                raw_method_payload={
                    "method": "S-ape ace",
                    "trait_name": str(config.trait_column or ""),
                    "terminal_span": str(record.get("terminal_span", "") or ""),
                    "supporting_tree_count": supporting,
                    "effective_tree_count": effective_count,
                },
            )
            result.node_results[clade_key] = node_result
            result.reference_node_ids[clade_key] = str(record.get("display_node_id", "") or "")

        result.model_statistics = {
            "model_name": "S-ape",
            "phytools_method": str(config.method),
            "phytools_method_label": PHYTOOLS_DISCRETE_METHODS.get(str(config.method), str(config.method)),
            "trait_column": str(config.trait_column or ""),
            "input_tree_count": len(tree_entries),
            "effective_tree_count": effective_count,
            "threads": worker_count,
            "aggregation": "exact_reference_clade_match",
        }
        if not result.node_results:
            result.parse_warnings.append("S-phytools found no internal clades shared with the reference tree.")
        return result

    def _percentile(self, sorted_values, percent):
        values = list(sorted_values or [])
        if not values:
            return 0.0
        if len(values) == 1:
            return float(values[0])
        position = (float(percent) / 100.0) * (len(values) - 1)
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return float(values[lower])
        fraction = position - lower
        return float(values[lower]) * (1.0 - fraction) + float(values[upper]) * fraction

    def _back_transform_value(self, value, transform):
        transform = str(transform or "none")
        if transform == "log":
            return float(math.exp(float(value)))
        if transform == "log10":
            return float(10.0 ** float(value))
        return float(value)

    def _scale_label(self, scale, transform):
        if scale == "original" and str(transform or "none") != "none":
            return "Original scale (back-transformed)"
        if transform == "log":
            return "natural log"
        if transform == "log10":
            return "log10"
        return "original"

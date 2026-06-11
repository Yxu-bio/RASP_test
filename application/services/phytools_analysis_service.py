import json
import math
from datetime import datetime
from pathlib import Path

from application.services.phytools_dataset_builder import PhytoolsDatasetBuilder
from domain.models.biogeobears_result import BioGeoBEARSNodeResult, BioGeoBEARSResult
from domain.models.continuous_trait_result import ContinuousTraitNodeResult, ContinuousTraitResult
from domain.models.phytools_config import (
    PhytoolsConfig,
    PHYTOOLS_CONTINUOUS_METHODS,
    phytools_is_experimental,
)
from infrastructure.phytools.phytools_runner import PhytoolsRunner


class PhytoolsAnalysisService:
    PALETTE = [
        "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
        "#ffff33", "#a65628", "#f781bf", "#999999", "#66c2a5",
        "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854", "#ffd92f",
        "#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e",
    ]

    def __init__(self, rscript_path=None, site_library_path=None, work_root=None):
        self.dataset_builder = PhytoolsDatasetBuilder()
        self.runner = PhytoolsRunner(
            rscript_path=rscript_path,
            site_library_path=site_library_path,
        )
        self.work_root = Path(work_root) if work_root else Path("runs") / "phytools"

    def set_rscript_path(self, rscript_path):
        self.runner.set_rscript_path(rscript_path)

    def set_site_library_path(self, site_library_path):
        self.runner.set_site_library_path(site_library_path)

    def analyze(self, *, tree, matrix, config: PhytoolsConfig, run_name=None):
        if config is None:
            raise ValueError("phytools config is required.")
        config.validate()
        if run_name is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = "phytools_%s" % stamp

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
            diagnostic = self._diagnose_run_failure(tree=tree, run_files=run_files, message=str(exc))
            raise RuntimeError(
                "phytools run failed.\n"
                "workdir: {workdir}\n"
                "tree: {tree}\n"
                "traits: {traits}\n"
                "{msg}{diagnostic}".format(
                    workdir=run_files.workdir,
                    tree=run_files.tree_path,
                    traits=run_files.traits_path,
                    msg=str(exc),
                    diagnostic=diagnostic,
                )
            )

        result = self._parse_result(
            tree=tree,
            run_files=run_files,
            run_output=run_output,
        )
        result.config = config
        return result

    def _parse_result(self, *, tree, run_files, run_output):
        payload = json.loads(Path(run_files.output_json_path).read_text(encoding="utf-8"))
        config = run_files.config
        method = str(payload.get("method", "") or "")
        if method.startswith("ape.ace"):
            return self._parse_discrete_ace(
                tree=tree,
                run_files=run_files,
                run_output=run_output,
                payload=payload,
            )

        transform = str(config.continuous_transform or "none")
        trait_name = str(config.trait_column or "")
        trait_scale = self._transform_label(transform)
        display_scale = "original" if transform != "none" else "analysis"
        plot_scale = "analysis"
        method_key = str(config.method or "FASTANC")
        method_label = PHYTOOLS_CONTINUOUS_METHODS.get(method_key, method_key)
        r_method = str(payload.get("method", "") or "")
        is_bayesian = method_key == "ANC_BAYES"
        is_experimental = False
        try:
            is_experimental = phytools_is_experimental(method_key)
        except Exception:
            pass

        result = ContinuousTraitResult(reference_tree=tree)
        result.model_name = self._continuous_model_name(method_key, r_method)
        result.result_note = self._continuous_result_note(method_key, r_method, trait_scale, is_experimental)
        result.input_tree_count = 1
        result.effective_tree_count = 1
        result.trait_name = trait_name
        result.trait_transform = transform
        result.trait_display_scale = display_scale
        result.trait_plot_scale = plot_scale
        result.tip_values = dict(run_files.trait_values)
        result.original_tip_values = dict(run_files.original_trait_values)
        result.plot_tip_values = dict(run_files.trait_values)

        record_by_clade = {
            str(record.get("clade_key", "")): record
            for record in list(run_files.node_records or [])
            if str(record.get("clade_key", ""))
        }

        analysis_values = []
        for item in list(payload.get("nodes", []) or []):
            clade_key = str(item.get("clade_key", "") or "")
            if not clade_key:
                continue
            record = record_by_clade.get(clade_key)
            if record is None:
                result.parse_warnings.append("phytools node could not be mapped to reference clade: %s" % clade_key)
                continue
            analysis_summary = self._node_analysis_summary(item)
            value = float(analysis_summary["mean"])
            median = float(analysis_summary["median"])
            lower95 = float(analysis_summary["lower95"])
            upper95 = float(analysis_summary["upper95"])
            minimum = float(analysis_summary["minimum"])
            maximum = float(analysis_summary["maximum"])
            raw_samples = list(analysis_summary["raw_samples"])
            original_summary = self._original_summary(analysis_summary, transform)
            display_summary = original_summary if display_scale == "original" else analysis_summary
            plot_value = median if is_bayesian else value
            node_result = ContinuousTraitNodeResult(
                node_key=clade_key,
                display_node_id=str(record.get("display_node_id", "") or ""),
                trait_name=trait_name,
                mean=value,
                median=median,
                lower95=lower95,
                upper95=upper95,
                minimum=minimum,
                maximum=maximum,
                sample_count=int(analysis_summary["sample_count"]),
                raw_samples=raw_samples,
                raw_method_payload={
                    "continuous": True,
                    "method": r_method or method_label,
                    "phytools_method": method_key,
                    "phytools_method_label": method_label,
                    "experimental": is_experimental,
                    "ape_node": int(item.get("ape_node", 0) or 0),
                    "terminal_span": str(record.get("terminal_span", "") or ""),
                    "trait_name": trait_name,
                    "trait_transform": transform,
                    "trait_scale": trait_scale,
                    "trait_display_scale": display_scale,
                    "trait_plot_scale": plot_scale,
                    "display_scale": self._scale_label(display_scale, transform),
                    "plot_scale": self._scale_label(plot_scale, transform),
                    "analysis_mean": value,
                    "analysis_median": median,
                    "analysis_lower95": lower95,
                    "analysis_upper95": upper95,
                    "analysis_minimum": minimum,
                    "analysis_maximum": maximum,
                    "original_mean": original_summary["mean"],
                    "original_median": original_summary["median"],
                    "original_lower95": original_summary["lower95"],
                    "original_upper95": original_summary["upper95"],
                    "original_minimum": original_summary["minimum"],
                    "original_maximum": original_summary["maximum"],
                    "display_mean": display_summary["mean"],
                    "display_median": display_summary["median"],
                    "display_lower95": display_summary["lower95"],
                    "display_upper95": display_summary["upper95"],
                    "plot_mean": plot_value,
                    "mean": value,
                    "median": median,
                    "lower95": lower95,
                    "upper95": upper95,
                    "variance": self._optional_float(item.get("variance")),
                    "sample_count": int(analysis_summary["sample_count"]),
                    "source_json": str(run_files.output_json_path),
                },
            )
            result.node_results[clade_key] = node_result
            result.reference_node_ids[clade_key] = str(record.get("display_node_id", "") or "")
            result.analysis_node_values[clade_key] = value
            result.original_node_values[clade_key] = original_summary["mean"]
            result.plot_node_values[clade_key] = plot_value
            analysis_values.append(plot_value)

        if analysis_values:
            values = list(result.plot_tip_values.values()) + list(result.plot_node_values.values())
            result.color_scale_min = min(values)
            result.color_scale_max = max(values)
        result.model_statistics = {
            "model_name": "phytools",
            "phytools_method": method_key,
            "phytools_method_label": method_label,
            "r_method": r_method,
            "experimental": is_experimental,
            "trait_column": trait_name,
            "trait_transform": transform,
            "trait_scale": trait_scale,
            "display_scale": self._scale_label(display_scale, transform),
            "plot_scale": self._scale_label(plot_scale, transform),
            "anc_ml_maxit": int(getattr(config, "anc_ml_maxit", 2000) or 2000),
            "bayes_iterations": int(getattr(config, "bayes_iterations", 10000) or 10000),
            "bayes_sample_frequency": int(getattr(config, "bayes_sample_frequency", 1000) or 1000),
            "bayes_burnin": int(getattr(config, "bayes_burnin", 0) or 0),
            "seed": int(getattr(config, "seed", 1) or 0),
            "rscript_path": str(run_output.rscript_path),
            "output_json_path": str(run_files.output_json_path),
            "tree_path": str(run_files.tree_path),
            "traits_path": str(run_files.traits_path),
            "missing_trait_taxa": list(getattr(run_files, "missing_trait_taxa", []) or []),
        }
        if not result.node_results:
            result.parse_warnings.append("phytools output did not contain mappable internal node values.")
        return result

    def _diagnose_run_failure(self, *, tree, run_files, message):
        config = run_files.config
        method_key = str(getattr(config, "method", "") or "").upper()
        lines = []
        missing_taxa = list(getattr(run_files, "missing_trait_taxa", []) or [])
        if missing_taxa:
            lines.append(
                "Missing observed values were omitted from the trait vector and left as unknown tips: %s"
                % ", ".join(missing_taxa[:20])
            )
            if len(missing_taxa) > 20:
                lines[-1] += " ..."

        lower_message = str(message or "").lower()
        if method_key == "ANC_ML_EB" and missing_taxa:
            lines.append(
                "Possible cause: phytools::anc.ML(model='EB') uses anc.EB internally, and anc.EB does not "
                "estimate missing tip values from an incomplete trait vector. The upstream error usually says "
                "to try model='BM'."
            )
            tree_summary = self._tree_diagnostic_summary(tree)
            if tree_summary:
                lines.append(tree_summary)
            lines.append(
                "Recommended action: use BM/OU or fastAnc/fastAnc+CI when the selected trait column has missing "
                "tips. EB is still available for complete data, but remains experimental."
            )
        elif method_key == "ANC_ML_EB" or "exactly singular" in lower_message or "solve.default" in lower_message:
            lines.append(
                "Possible cause: phytools::anc.ML(model='EB') can produce a singular covariance matrix "
                "during optimization for some tree/data combinations, even when no trait values are missing."
            )
            tree_summary = self._tree_diagnostic_summary(tree)
            if tree_summary:
                lines.append(tree_summary)
            lines.append(
                "Recommended action: retry BM or OU for ML ancestral-state estimation, or use fastAnc/fastAnc+CI "
                "for a Brownian approximation. EB is kept as an experimental option."
            )
        elif "na/nan/inf" in lower_message or "non-finite" in lower_message:
            lines.append(
                "Possible cause: the selected trait/transform produced NA, NaN, or Inf values. "
                "Check missing cells and make sure log/log10 transforms only receive positive values."
            )

        if not lines:
            return ""
        return "\n\nDiagnostics:\n- " + "\n- ".join(lines)

    def _tree_diagnostic_summary(self, tree):
        try:
            tip_names = [str(leaf.name) for leaf in tree.iter_leaves()]
            duplicates = len(tip_names) - len(set(tip_names))
            zero_edges = 0
            negative_edges = 0
            polytomies = 0
            for node in tree.traverse():
                children = list(getattr(node, "children", []) or [])
                if children and len(children) != 2:
                    polytomies += 1
                if node is tree:
                    continue
                dist = float(getattr(node, "dist", 0.0) or 0.0)
                if abs(dist) < 1e-12:
                    zero_edges += 1
                elif dist < 0:
                    negative_edges += 1
            return (
                "Tree check: tips=%s, duplicate_tip_names=%s, zero_length_edges=%s, "
                "negative_edges=%s, non_binary_internal_nodes=%s."
                % (len(tip_names), duplicates, zero_edges, negative_edges, polytomies)
            )
        except Exception:
            return ""

    def _continuous_model_name(self, method_key, r_method):
        if method_key == "FASTANC":
            return "phytools fastAnc"
        if method_key == "FASTANC_CI":
            return "phytools fastAnc + 95% CI"
        if method_key == "ANC_BAYES":
            return "phytools anc.Bayes"
        if method_key.startswith("ANC_ML_"):
            suffix = str(r_method or method_key).split(".")[-1]
            return "phytools anc.ML (%s)" % suffix
        return "phytools"

    def _continuous_result_note(self, method_key, r_method, trait_scale, is_experimental):
        if method_key == "FASTANC":
            note = "Continuous ancestral values were estimated with phytools::fastAnc."
        elif method_key == "FASTANC_CI":
            note = "Continuous ancestral values and 95% confidence intervals were estimated with phytools::fastAnc(CI=TRUE, vars=TRUE)."
        elif method_key == "ANC_BAYES":
            note = "Continuous ancestral values were estimated with phytools::anc.Bayes MCMC."
        elif method_key.startswith("ANC_ML_"):
            note = "Continuous ancestral values were estimated with %s." % (r_method or "phytools::anc.ML")
        else:
            note = "Continuous ancestral values were estimated with phytools."
        if is_experimental:
            note += " This method is experimental in the current Windows bundled R runtime."
        note += " Model values are on the %s scale." % trait_scale
        return note

    def _node_analysis_summary(self, item):
        raw_samples = self._float_list(item.get("raw_samples", []))
        mean = self._required_float(item, "mean", self._required_float(item, "value", 0.0))
        median = self._required_float(item, "median", mean)
        lower95 = self._required_float(item, "lower95", median)
        upper95 = self._required_float(item, "upper95", median)
        minimum = self._required_float(item, "minimum", lower95)
        maximum = self._required_float(item, "maximum", upper95)
        sample_count = int(self._required_float(item, "sample_count", len(raw_samples) if raw_samples else 1))
        if not raw_samples:
            raw_samples = [median]
        return {
            "mean": mean,
            "median": median,
            "lower95": lower95,
            "upper95": upper95,
            "minimum": minimum,
            "maximum": maximum,
            "sample_count": max(1, sample_count),
            "raw_samples": raw_samples,
        }

    def _original_summary(self, analysis_summary, transform):
        samples = list(analysis_summary.get("raw_samples", []) or [])
        if samples and transform in ("log", "log10") and len(samples) > 1:
            original_samples = [self._back_transform_value(value, transform) for value in samples]
            return self._sample_summary(original_samples)
        return {
            "mean": self._back_transform_value(float(analysis_summary["mean"]), transform),
            "median": self._back_transform_value(float(analysis_summary["median"]), transform),
            "lower95": self._back_transform_value(float(analysis_summary["lower95"]), transform),
            "upper95": self._back_transform_value(float(analysis_summary["upper95"]), transform),
            "minimum": self._back_transform_value(float(analysis_summary["minimum"]), transform),
            "maximum": self._back_transform_value(float(analysis_summary["maximum"]), transform),
        }

    def _sample_summary(self, samples):
        values = sorted(float(x) for x in list(samples or []))
        if not values:
            return {"mean": 0.0, "median": 0.0, "lower95": 0.0, "upper95": 0.0, "minimum": 0.0, "maximum": 0.0}
        mean = sum(values) / float(len(values))
        return {
            "mean": mean,
            "median": self._percentile(values, 50.0),
            "lower95": self._percentile(values, 2.5),
            "upper95": self._percentile(values, 97.5),
            "minimum": values[0],
            "maximum": values[-1],
        }

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

    def _required_float(self, item, key, default):
        try:
            return float(item.get(key, default))
        except Exception:
            return float(default)

    def _optional_float(self, value):
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _float_list(self, values):
        out = []
        for value in list(values or []):
            try:
                out.append(float(value))
            except Exception:
                pass
        return out

    def _parse_discrete_ace(self, *, tree, run_files, run_output, payload):
        config = run_files.config
        trait_name = str(config.trait_column or "")
        method_label = str(payload.get("method", "") or "ape.ace")
        result = BioGeoBEARSResult(reference_tree=tree)
        result.model_name = "ape ace"
        result.result_note = (
            "Discrete ancestral state probabilities were estimated with %s." % method_label
        )
        result.input_tree_count = 1
        result.effective_tree_count = 1
        result.config = config

        state_order = [str(x) for x in list(payload.get("state_order", []) or []) if str(x)]
        if not state_order:
            seen = []
            for value in dict(run_files.trait_values or {}).values():
                value = str(value)
                if value not in seen:
                    seen.append(value)
            state_order = seen
        result.state_order = state_order
        result.state_colors = {
            state: self.PALETTE[i % len(self.PALETTE)]
            for i, state in enumerate(state_order)
        }

        record_by_clade = {
            str(record.get("clade_key", "")): record
            for record in list(run_files.node_records or [])
            if str(record.get("clade_key", ""))
        }

        for item in list(payload.get("nodes", []) or []):
            clade_key = str(item.get("clade_key", "") or "")
            record = record_by_clade.get(clade_key)
            if record is None:
                result.parse_warnings.append("ape ace node could not be mapped to reference clade: %s" % clade_key)
                continue
            raw_probs = dict(item.get("probabilities", {}) or {})
            probabilities = {}
            for state in state_order:
                try:
                    probabilities[state] = float(raw_probs.get(state, 0.0) or 0.0) * 100.0
                except Exception:
                    probabilities[state] = 0.0
            total = sum(float(v) for v in probabilities.values())
            if total > 0:
                probabilities = {k: float(v) * 100.0 / total for k, v in probabilities.items()}

            labels = list(probabilities.keys())
            node_result = BioGeoBEARSNodeResult(
                node_key=clade_key,
                display_node_id=str(record.get("display_node_id", "") or ""),
                states=labels,
                state_supports=dict(probabilities),
                pie_labels=labels,
                pie_percents=[probabilities[state] for state in labels],
                pie_colors=[result.state_colors.get(state, "#808080") for state in labels],
                supporting_tree_count=1,
                total_tree_count=1,
                event_summary="ape ace ancestral state probabilities",
                raw_method_payload={
                    "method": method_label,
                    "trait_name": trait_name,
                    "terminal_span": str(record.get("terminal_span", "") or ""),
                    "ape_node": int(item.get("ape_node", 0) or 0),
                    "source_json": str(run_files.output_json_path),
                },
            )
            result.node_results[clade_key] = node_result
            result.reference_node_ids[clade_key] = str(record.get("display_node_id", "") or "")

        result.model_statistics = {
            "model_name": "ape",
            "phytools_method": str(config.method),
            "trait_column": trait_name,
            "rscript_path": str(run_output.rscript_path),
            "output_json_path": str(run_files.output_json_path),
            "tree_path": str(run_files.tree_path),
            "traits_path": str(run_files.traits_path),
        }
        if not result.node_results:
            result.parse_warnings.append("ape ace output did not contain mappable internal node probabilities.")
        return result

    def _back_transform_value(self, value: float, transform: str) -> float:
        if transform == "log":
            return float(math.exp(value))
        if transform == "log10":
            return float(10.0 ** value)
        return float(value)

    def _transform_label(self, transform: str) -> str:
        if transform == "log":
            return "natural log"
        if transform == "log10":
            return "log10"
        return "original"

    def _scale_label(self, scale: str, transform: str) -> str:
        if scale == "original" and transform != "none":
            return "Original scale (back-transformed)"
        return self._transform_label(transform)

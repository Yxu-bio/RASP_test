import math
import re
from collections import OrderedDict
from pathlib import Path

from domain.models.biogeobears_result import BioGeoBEARSNodeResult, BioGeoBEARSResult
from domain.models.bayestraits_config import (
    BAYESTRAITS_CONTINUOUS_DISPLAY_SCALES,
    BAYESTRAITS_CONTINUOUS_PLOT_SCALES,
    BAYESTRAITS_CONTINUOUS_TRANSFORMS,
    BAYESTRAITS_MODELS,
    normalize_bayestraits_continuous_display_scale,
    normalize_bayestraits_continuous_plot_scale,
    normalize_bayestraits_continuous_transform,
    normalize_bayestraits_model,
)
from domain.models.continuous_trait_result import ContinuousTraitNodeResult, ContinuousTraitResult


class BayesTraitsOutputParser:
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

    def parse(self, *, reference_tree, run_files, run_output=None):
        output_log = Path(run_output.output_log_path if run_output is not None else run_files.output_log_path)
        if not output_log.exists():
            raise FileNotFoundError("BayesTraits log was not found: %s" % output_log)

        if bool(getattr(run_files, "continuous_asr", False)):
            return self._parse_continuous_asr(
                reference_tree=reference_tree,
                run_files=run_files,
                run_output=run_output,
                output_log=output_log,
            )

        header, data_rows = self._read_probability_table(output_log)
        if not header or not data_rows:
            return self._parse_statistical_table(
                reference_tree=reference_tree,
                run_files=run_files,
                run_output=run_output,
                output_log=output_log,
            )

        states_from_header = self._states_from_header(header)
        display_labels = dict(run_files.state_display_labels or {})
        if not display_labels:
            display_labels = {state: state for state in states_from_header}

        result = BioGeoBEARSResult(reference_tree=reference_tree)
        result.model_name = self._display_model_name(run_files)
        result.result_note = (
            "BayesTraits MultiState ancestral-state reconstruction. "
            "Node probabilities are averaged from the BayesTraits probability table."
        )
        result.input_tree_count = int(run_files.tree_count)
        result.effective_tree_count = len(data_rows)
        result.config = run_files.config

        global_states = []
        rows_for_log = []
        selected = set(str(x) for x in list(run_files.selected_node_ids or []))
        for record in list(run_files.node_records or []):
            display_id = str(record.get("display_node_id", "") or "")
            if display_id not in selected:
                continue
            probabilities = self._node_probabilities(
                header=header,
                rows=data_rows,
                node_id=display_id,
                states=states_from_header,
                display_labels=display_labels,
            )
            rows_for_log.append((record, probabilities))
            if not probabilities:
                continue

            for state in probabilities.keys():
                if state not in global_states:
                    global_states.append(state)

            clade_key = str(record.get("clade_key", ""))
            node_result = BioGeoBEARSNodeResult(
                node_key=clade_key,
                display_node_id=display_id,
                states=list(probabilities.keys()),
                state_supports=dict(probabilities),
                pie_labels=list(probabilities.keys()),
                pie_percents=[probabilities[state] for state in probabilities.keys()],
                pie_colors=[],
                supporting_tree_count=len(data_rows),
                total_tree_count=int(run_files.tree_count),
                event_summary="BayesTraits MultiState node probabilities",
                raw_method_payload={
                    "terminal_span": str(record.get("terminal_span", "")),
                    "source_log": str(output_log),
                    "tree_count": int(run_files.tree_count),
                    "sample_count": len(data_rows),
                },
            )
            result.node_results[clade_key] = node_result
            result.reference_node_ids[clade_key] = display_id

        result.state_order = global_states
        result.state_colors = self._build_state_colors(global_states)
        for node_result in result.node_results.values():
            node_result.pie_colors = [
                result.state_colors.get(label, "#808080")
                for label in node_result.pie_labels
            ]

        marginal_likelihood = self._read_marginal_likelihood(run_files.stones_path)
        self._write_analysis_log(run_files, rows_for_log, marginal_likelihood)
        result.analysis_log_path = str(run_files.analysis_log_path)
        result.model_statistics = {
            "model_name": "BayesTraits",
            "bayestraits_model": self._model_key(run_files),
            "analysis_method": str(run_files.config.analysis_method),
            "trait_column": str(run_files.config.trait_column),
            "trait_columns": list(getattr(run_files.config, "selected_trait_columns", []) or [getattr(run_files.config, "trait_column", "")]),
            "tree_count": int(run_files.tree_count),
            "sample_count": len(data_rows),
            "executable_path": str(run_output.executable_path) if run_output is not None else "",
            "executable_version": str(getattr(run_output, "executable_version", "") or ""),
            "output_log_path": str(output_log),
            "analysis_log_path": str(run_files.analysis_log_path),
            "commands_path": str(run_files.commands_path),
            "marginal_likelihood": marginal_likelihood,
        }
        if not result.node_results:
            result.parse_warnings.append("BayesTraits output did not contain selected-node probabilities.")
        return result

    def _parse_continuous_asr(self, *, reference_tree, run_files, run_output, output_log):
        header, rows = self._read_generic_table(output_log)
        if not header or not rows:
            raise ValueError("BayesTraits Continuous ASR log did not contain a parseable MCMC table.")

        trait_name = str(getattr(run_files.config, "trait_column", "") or "").strip()
        trait_transform = normalize_bayestraits_continuous_transform(
            getattr(run_files.config, "continuous_transform", "none")
        )
        trait_display_scale = "original" if trait_transform != "none" else "analysis"
        trait_plot_scale = "analysis"
        trait_scale = self._continuous_transform_label(trait_transform)
        display_scale_label = self._continuous_display_scale_label(trait_display_scale, trait_transform)
        plot_scale_label = self._continuous_plot_scale_label(trait_plot_scale, trait_transform)
        result = ContinuousTraitResult(reference_tree=reference_tree)
        result.model_name = "BayesTraits Continuous ASR"
        result.result_note = (
            "Continuous ancestral values were estimated by BayesTraits V5 unknown-value MCMC "
            "using SaveModels / LoadModels and AddMRCA tags. Model values are on the %s scale; "
            "colors use %s; displayed summaries use %s."
            % (trait_scale, plot_scale_label, display_scale_label)
        )
        result.input_tree_count = 1
        result.effective_tree_count = len(rows)
        result.config = run_files.config
        result.trait_name = trait_name
        result.trait_transform = trait_transform
        result.trait_display_scale = trait_display_scale
        result.trait_plot_scale = trait_plot_scale
        result.tip_values = {
            str(k): float(v)
            for k, v in dict((run_files.extra_metadata or {}).get("continuous_tip_values", {}) or {}).items()
        }
        result.original_tip_values = self._continuous_original_tip_values(result.tip_values, trait_transform)

        record_by_estimate = {}
        for record in list(run_files.node_records or []):
            node_id = str(record.get("display_node_id", "") or "").strip()
            if node_id:
                record_by_estimate["RASP_NODE_%s" % node_id] = record

        node_rows_for_log = []
        for col_idx, column_name in enumerate(list(header or [])):
            match = re.match(r"^Est\s+(RASP_NODE_\S+)\s+-\s+1$", str(column_name).strip())
            if not match:
                continue
            estimate_name = match.group(1)
            record = record_by_estimate.get(estimate_name)
            if record is None:
                continue
            samples = []
            for row in rows:
                if col_idx >= len(row):
                    continue
                try:
                    samples.append(float(row[col_idx]))
                except Exception:
                    pass
            if not samples:
                continue

            summary = self._continuous_sample_summary(samples)
            original_samples = self._back_transform_continuous_samples(samples, trait_transform)
            original_summary = self._fallback_original_summary(summary, original_samples, trait_transform)
            display_summary = original_summary if trait_display_scale == "original" and original_summary else summary
            plot_summary = original_summary if trait_plot_scale == "original" and original_summary else summary
            clade_key = str(record.get("clade_key", "") or "")
            display_id = str(record.get("display_node_id", "") or "")
            node_result = ContinuousTraitNodeResult(
                node_key=clade_key,
                display_node_id=display_id,
                trait_name=trait_name,
                mean=summary["mean"],
                median=summary["median"],
                lower95=summary["lower95"],
                upper95=summary["upper95"],
                minimum=summary["min"],
                maximum=summary["max"],
                sample_count=len(samples),
                raw_samples=samples,
                raw_method_payload={
                    "continuous": True,
                    "estimate_column": str(column_name),
                    "terminal_span": str(record.get("terminal_span", "")),
                    "trait_name": trait_name,
                    "trait_transform": trait_transform,
                    "trait_scale": trait_scale,
                    "trait_display_scale": trait_display_scale,
                    "trait_plot_scale": trait_plot_scale,
                    "display_scale": display_scale_label,
                    "plot_scale": plot_scale_label,
                    "analysis_mean": summary["mean"],
                    "analysis_median": summary["median"],
                    "analysis_lower95": summary["lower95"],
                    "analysis_upper95": summary["upper95"],
                    "original_mean": original_summary["mean"],
                    "original_median": original_summary["median"],
                    "original_lower95": original_summary["lower95"],
                    "original_upper95": original_summary["upper95"],
                    "display_mean": display_summary["mean"],
                    "display_median": display_summary["median"],
                    "display_lower95": display_summary["lower95"],
                    "display_upper95": display_summary["upper95"],
                    "plot_mean": plot_summary["mean"],
                    "mean": summary["mean"],
                    "median": summary["median"],
                    "lower95": summary["lower95"],
                    "upper95": summary["upper95"],
                    "sample_count": len(samples),
                },
            )
            result.node_results[clade_key] = node_result
            result.reference_node_ids[clade_key] = display_id
            result.analysis_node_values[clade_key] = float(summary["median"])
            result.original_node_values[clade_key] = float(original_summary["median"])
            node_rows_for_log.append((record, node_result))

        if not result.node_results:
            raise ValueError("BayesTraits Continuous ASR output did not contain Est RASP_NODE_* columns.")

        plot_tip_values = self._continuous_plot_tip_values(result.tip_values, trait_transform, trait_plot_scale)
        result.plot_tip_values = plot_tip_values
        plot_node_values = {}
        for key, node in result.node_results.items():
            payload = dict(getattr(node, "raw_method_payload", {}) or {})
            if trait_plot_scale == "original" and trait_transform != "none":
                value = float(payload.get("plot_median", payload.get("display_median", node.median)))
            else:
                value = float(node.median)
            plot_node_values[str(key)] = value
        result.plot_node_values = plot_node_values

        scale_values = list(plot_tip_values.values()) + list(plot_node_values.values())
        result.color_scale_min = min(scale_values)
        result.color_scale_max = max(scale_values)
        if result.color_scale_min == result.color_scale_max:
            result.color_scale_max = result.color_scale_min + 1.0

        self._write_continuous_asr_analysis_log(run_files, output_log, node_rows_for_log, result)
        result.analysis_log_path = str(run_files.analysis_log_path)
        result.model_statistics = {
            "model_name": "BayesTraits Continuous ASR",
            "bayestraits_model": self._model_key(run_files),
            "analysis_method": str(run_files.config.analysis_method),
            "trait_column": trait_name,
            "trait_transform": trait_transform,
            "trait_scale": trait_scale,
            "trait_display_scale": trait_display_scale,
            "display_scale": display_scale_label,
            "trait_plot_scale": trait_plot_scale,
            "plot_scale": plot_scale_label,
            "tree_count": 1,
            "sample_count": len(rows),
            "node_count": len(result.node_results),
            "executable_path": str(run_output.executable_path) if run_output is not None else "",
            "executable_version": str(getattr(run_output, "executable_version", "") or ""),
            "output_log_path": str(output_log),
            "analysis_log_path": str(run_files.analysis_log_path),
            "model_save_commands_path": str(run_files.model_save_commands_path or ""),
            "estimate_commands_path": str(run_files.estimate_commands_path or ""),
            "model_save_path": str(run_files.model_save_path or ""),
            "color_scale_min": result.color_scale_min,
            "color_scale_max": result.color_scale_max,
        }
        return result

    def _continuous_original_tip_values(self, tip_values, transform):
        transform = normalize_bayestraits_continuous_transform(transform)
        values = {str(k): float(v) for k, v in dict(tip_values or {}).items()}
        if transform == "none":
            return dict(values)
        return {
            taxon: self._back_transform_continuous_value(value, transform)
            for taxon, value in values.items()
        }

    def _continuous_plot_tip_values(self, tip_values, transform, plot_scale):
        plot_scale = normalize_bayestraits_continuous_plot_scale(plot_scale)
        transform = normalize_bayestraits_continuous_transform(transform)
        values = {str(k): float(v) for k, v in dict(tip_values or {}).items()}
        if plot_scale != "original" or transform == "none":
            return values
        return {
            taxon: self._back_transform_continuous_value(value, transform)
            for taxon, value in values.items()
        }

    def _back_transform_continuous_samples(self, samples, transform):
        transform = normalize_bayestraits_continuous_transform(transform)
        values = []
        for value in list(samples or []):
            try:
                number = float(value)
                if transform == "log":
                    transformed = math.exp(number)
                elif transform == "log10":
                    transformed = 10.0 ** number
                else:
                    transformed = number
            except (OverflowError, ValueError):
                continue
            if math.isfinite(transformed):
                values.append(float(transformed))
        return values

    def _back_transform_continuous_summary(self, summary, transform):
        transform = normalize_bayestraits_continuous_transform(transform)
        output = {}
        for key, value in dict(summary or {}).items():
            try:
                output[key] = self._back_transform_continuous_value(value, transform)
            except (OverflowError, ValueError):
                output[key] = float("nan")
        return output

    def _fallback_original_summary(self, analysis_summary, original_samples, transform):
        if original_samples:
            return self._continuous_sample_summary(original_samples)
        return self._back_transform_continuous_summary(analysis_summary, transform)

    def _back_transform_continuous_samples_legacy(self, samples, transform):
        transform = normalize_bayestraits_continuous_transform(transform)
        if transform == "log":
            return [math.exp(float(value)) for value in list(samples or [])]
        if transform == "log10":
            return [10.0 ** float(value) for value in list(samples or [])]
        return [float(value) for value in list(samples or [])]

    def _back_transform_continuous_value(self, value, transform):
        transform = normalize_bayestraits_continuous_transform(transform)
        number = float(value)
        if transform == "log":
            return math.exp(number)
        if transform == "log10":
            return 10.0 ** number
        return number

    def _continuous_sample_summary(self, samples):
        values = sorted(float(x) for x in list(samples or []))
        n = len(values)
        if n <= 0:
            raise ValueError("No samples to summarize.")
        return {
            "mean": sum(values) / float(n),
            "median": self._quantile(values, 0.5),
            "lower95": self._quantile(values, 0.025),
            "upper95": self._quantile(values, 0.975),
            "min": values[0],
            "max": values[-1],
        }

    def _quantile(self, sorted_values, q):
        values = list(sorted_values or [])
        if not values:
            return 0.0
        if len(values) == 1:
            return float(values[0])
        q = max(0.0, min(1.0, float(q)))
        pos = q * (len(values) - 1)
        lower = int(pos)
        upper = min(lower + 1, len(values) - 1)
        fraction = pos - lower
        return float(values[lower]) * (1.0 - fraction) + float(values[upper]) * fraction

    def _parse_statistical_table(self, *, reference_tree, run_files, run_output, output_log):
        header, rows = self._read_generic_table(output_log)
        if not header or not rows:
            raise ValueError("BayesTraits log did not contain a parseable result table.")

        result = BioGeoBEARSResult(reference_tree=reference_tree)
        result.model_name = self._display_model_name(run_files)
        result.result_note = (
            "BayesTraits statistical model output. This model does not produce "
            "MultiState node probability pies in the current RASP view."
        )
        result.input_tree_count = int(run_files.tree_count)
        result.effective_tree_count = len(rows)
        result.config = run_files.config
        result.state_order = []
        result.state_colors = {}

        summaries = self._numeric_column_summaries(header, rows)
        self._write_statistical_analysis_log(run_files, output_log, header, rows, summaries)
        result.analysis_log_path = str(run_files.analysis_log_path)
        result.model_statistics = {
            "model_name": "BayesTraits",
            "bayestraits_model": self._model_key(run_files),
            "analysis_method": str(run_files.config.analysis_method),
            "trait_column": str(run_files.config.trait_column),
            "trait_columns": list(getattr(run_files.config, "selected_trait_columns", []) or [getattr(run_files.config, "trait_column", "")]),
            "tree_count": int(run_files.tree_count),
            "sample_count": len(rows),
            "executable_path": str(run_output.executable_path) if run_output is not None else "",
            "executable_version": str(getattr(run_output, "executable_version", "") or ""),
            "output_log_path": str(output_log),
            "analysis_log_path": str(run_files.analysis_log_path),
            "commands_path": str(run_files.commands_path),
            "numeric_summaries": summaries,
        }
        result.parse_warnings.append(
            "%s completed, but this BayesTraits model has no MultiState node probability pies to draw."
            % self._display_model_name(run_files)
        )
        return result

    def _read_probability_table(self, path: Path):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        header_index = -1
        for index, line in enumerate(lines):
            if "\t" in line and "Root P(" in line:
                header_index = index
        if header_index < 0:
            return [], []

        header = lines[header_index].rstrip("\t").split("\t")
        rows = []
        for line in lines[header_index + 1:]:
            clean = line.strip()
            if not clean:
                continue
            if clean.startswith("Sec:"):
                break
            parts = line.rstrip("\t").split("\t")
            if not parts:
                continue
            try:
                float(parts[0])
            except Exception:
                continue
            rows.append(parts)
        return header, rows

    def _read_generic_table(self, path: Path):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        header_index = -1
        for index, line in enumerate(lines):
            if "\t" not in line:
                continue
            first = line.split("\t", 1)[0].strip()
            if first in ("Tree No", "Iteration"):
                header_index = index
        if header_index < 0:
            return [], []

        header = lines[header_index].rstrip("\t").split("\t")
        rows = []
        for line in lines[header_index + 1:]:
            clean = line.strip()
            if not clean:
                continue
            if clean.startswith("Sec:"):
                break
            parts = line.rstrip("\t").split("\t")
            if not parts:
                continue
            try:
                float(parts[0])
            except Exception:
                continue
            rows.append(parts)
        return header, rows

    def _numeric_column_summaries(self, header, rows):
        summaries = OrderedDict()
        for col_idx, name in enumerate(list(header or [])):
            values = []
            for row in rows:
                if col_idx >= len(row):
                    continue
                try:
                    values.append(float(row[col_idx]))
                except Exception:
                    pass
            if not values:
                continue
            summaries[str(name)] = {
                "mean": sum(values) / float(len(values)),
                "min": min(values),
                "max": max(values),
                "n": len(values),
            }
        return summaries

    def _states_from_header(self, header):
        states = []
        for item in header:
            m = re.match(r"Root P\((.+)\)$", str(item).strip())
            if not m:
                continue
            state = m.group(1)
            if state not in states:
                states.append(state)
        return states

    def _node_probabilities(self, *, header, rows, node_id, states, display_labels):
        raw = OrderedDict()
        for state in states:
            column_name = "Node%s P(%s)" % (node_id, state)
            try:
                column_index = header.index(column_name)
            except ValueError:
                continue
            values = []
            for row in rows:
                if column_index >= len(row):
                    continue
                try:
                    values.append(float(row[column_index]))
                except Exception:
                    pass
            if values:
                label = str(display_labels.get(state, state))
                raw[label] = sum(values) / float(len(values))

        total = sum(float(value) for value in raw.values())
        if total <= 0:
            return OrderedDict()
        normalized = OrderedDict()
        for label, value in sorted(raw.items(), key=lambda item: (-float(item[1]), item[0])):
            normalized[label] = float(value) * 100.0 / total
        return normalized

    def _read_marginal_likelihood(self, path):
        if path is None or not Path(path).exists():
            return None
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if "likelihood" not in line.lower():
                continue
            parts = line.split(":")
            if len(parts) < 2:
                continue
            try:
                return float(parts[-1].strip())
            except Exception:
                pass
        return None

    def _write_analysis_log(self, run_files, rows_for_log, marginal_likelihood):
        lines = ["BayesTraits Results"]
        lines.append("[MODEL]")
        lines.append("Model=%s" % self._display_model_name(run_files))
        lines.append("Traits=%s" % ", ".join(list(getattr(run_files.config, "selected_trait_columns", []) or [getattr(run_files.config, "trait_column", "")])))
        lines.append("[TAXON]")
        trait_map = self._read_trait_data(run_files)
        for taxon_id, taxon_name in zip(run_files.taxon_ids, run_files.taxon_names):
            lines.append("%s\t%s\t%s" % (taxon_id, taxon_name, trait_map.get(str(taxon_id), "")))
        lines.append("[TREE]")
        lines.append("Tree=" + str(run_files.numeric_reference_tree_text))
        lines.append("[RESULT]")
        if marginal_likelihood is not None:
            lines.append("Result of BayesTraits (Log marginal likelihood = %s):" % marginal_likelihood)
        else:
            lines.append("Result of BayesTraits:")

        for record, states in rows_for_log:
            prefix = "node %s (anc. of terminals %s):" % (
                str(record.get("display_node_id", "")),
                str(record.get("terminal_span", "")),
            )
            if not states:
                states = OrderedDict(
                    (
                        str(run_files.state_display_labels.get(symbol, symbol)),
                        0.0,
                    )
                    for symbol in list(run_files.state_symbols or [])
                )
            if states:
                prefix += " " + " ".join("%s %.2f" % (label, percent) for label, percent in states.items())
            lines.append(prefix)
        run_files.analysis_log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_statistical_analysis_log(self, run_files, output_log, header, rows, summaries):
        lines = ["BayesTraits Results"]
        lines.append("[MODEL]")
        lines.append("Model=%s" % self._display_model_name(run_files))
        lines.append("Analysis=%s" % str(getattr(run_files.config, "analysis_method", "")))
        lines.append("Traits=%s" % ", ".join(list(getattr(run_files.config, "selected_trait_columns", []) or [getattr(run_files.config, "trait_column", "")])))
        lines.append("Output=%s" % str(output_log))
        lines.append("[TAXON]")
        trait_map = self._read_trait_data(run_files)
        for taxon_id, taxon_name in zip(run_files.taxon_ids, run_files.taxon_names):
            lines.append("%s\t%s\t%s" % (taxon_id, taxon_name, trait_map.get(str(taxon_id), "")))
        lines.append("[TREE]")
        lines.append("Tree=" + str(run_files.numeric_reference_tree_text))
        lines.append("[RESULT]")
        lines.append("Result of %s:" % self._display_model_name(run_files))
        for name, summary in summaries.items():
            if name in ("Tree No", "Iteration"):
                continue
            lines.append(
                "%s mean %.6g min %.6g max %.6g n %s"
                % (name, summary["mean"], summary["min"], summary["max"], summary["n"])
            )
        lines.append("[TABLE]")
        lines.append("\t".join(str(x) for x in header))
        for row in rows[:200]:
            lines.append("\t".join(str(x) for x in row))
        if len(rows) > 200:
            lines.append("... truncated %s additional rows; see raw BayesTraits log." % (len(rows) - 200))
        run_files.analysis_log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_continuous_asr_analysis_log(self, run_files, output_log, node_rows_for_log, result):
        lines = ["BayesTraits Continuous ASR Results"]
        lines.append("[MODEL]")
        lines.append("Model=%s" % self._display_model_name(run_files))
        lines.append("Analysis=MCMC")
        lines.append("Trait=%s" % str(result.trait_name or ""))
        lines.append("TraitTransform=%s" % str(getattr(result, "trait_transform", "none") or "none"))
        lines.append("TraitDisplayScale=%s" % str(getattr(result, "trait_display_scale", "analysis") or "analysis"))
        lines.append("TraitPlotScale=%s" % str(getattr(result, "trait_plot_scale", "analysis") or "analysis"))
        lines.append("Output=%s" % str(output_log))
        lines.append("ModelSaveCommands=%s" % str(run_files.model_save_commands_path or ""))
        lines.append("EstimateCommands=%s" % str(run_files.estimate_commands_path or ""))
        lines.append("[TAXON]")
        for taxon_name in list(run_files.taxon_names or []):
            value = result.tip_values.get(str(taxon_name), "")
            lines.append("%s\t%s" % (taxon_name, value))
        lines.append("[TREE]")
        lines.append("Tree=" + str(run_files.numeric_reference_tree_text))
        lines.append("[RESULT]")
        lines.append("Result of BayesTraits Continuous ASR:")
        for record, node_result in node_rows_for_log:
            payload = dict(getattr(node_result, "raw_method_payload", {}) or {})
            display_mean = float(payload.get("display_mean", node_result.mean))
            display_median = float(payload.get("display_median", node_result.median))
            display_lower95 = float(payload.get("display_lower95", node_result.lower95))
            display_upper95 = float(payload.get("display_upper95", node_result.upper95))
            display_scale = str(payload.get("display_scale", "Analysis scale"))
            extra = ""
            if str(payload.get("trait_display_scale", "analysis")) == "original":
                extra = "; analysis mean %.6g median %.6g 95CI [%.6g, %.6g]" % (
                    float(node_result.mean),
                    float(node_result.median),
                    float(node_result.lower95),
                    float(node_result.upper95),
                )
            lines.append(
                "node %s (anc. of terminals %s): mean %.6g median %.6g 95CI [%.6g, %.6g] scale %s n %s%s"
                % (
                    str(record.get("display_node_id", "")),
                    str(record.get("terminal_span", "")),
                    display_mean,
                    display_median,
                    display_lower95,
                    display_upper95,
                    display_scale,
                    int(node_result.sample_count),
                    extra,
                )
            )
        run_files.analysis_log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _continuous_transform_label(self, transform) -> str:
        key = normalize_bayestraits_continuous_transform(transform)
        return str(BAYESTRAITS_CONTINUOUS_TRANSFORMS.get(key, "None"))

    def _continuous_display_scale_label(self, display_scale, transform) -> str:
        scale = normalize_bayestraits_continuous_display_scale(display_scale)
        transform = normalize_bayestraits_continuous_transform(transform)
        if transform == "none":
            scale = "analysis"
        return str(BAYESTRAITS_CONTINUOUS_DISPLAY_SCALES.get(scale, "Analysis scale"))

    def _continuous_plot_scale_label(self, plot_scale, transform) -> str:
        scale = normalize_bayestraits_continuous_plot_scale(plot_scale)
        transform = normalize_bayestraits_continuous_transform(transform)
        if transform == "none":
            scale = "analysis"
        return str(BAYESTRAITS_CONTINUOUS_PLOT_SCALES.get(scale, "Analysis scale"))

    def _read_trait_data(self, run_files):
        result = {}
        text = run_files.data_path.read_text(encoding="ascii", errors="ignore")
        for line in text.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                result[str(parts[0])] = "\t".join(str(x) for x in parts[1:])
        return result

    def _build_state_colors(self, states):
        colors = {}
        for idx, state in enumerate(list(states or [])):
            colors[state] = self.PALETTE[idx % len(self.PALETTE)]
        return colors

    def _model_key(self, run_files):
        try:
            return normalize_bayestraits_model(getattr(run_files.config, "model", "MULTISTATE"))
        except Exception:
            return "MULTISTATE"

    def _display_model_name(self, run_files):
        model = self._model_key(run_files)
        label = BAYESTRAITS_MODELS.get(model, BAYESTRAITS_MODELS["MULTISTATE"]).get("label", model)
        return "BayesTraits %s" % label

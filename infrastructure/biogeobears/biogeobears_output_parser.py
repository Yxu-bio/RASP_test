import json
from pathlib import Path

from domain.models.biogeobears_result import (
    BioGeoBEARSResult,
    BioGeoBEARSNodeResult,
)


class BioGeoBEARSOutputParser:
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

    def parse(self, *, reference_tree, output_json_path):
        output_json_path = Path(output_json_path)
        payload = json.loads(output_json_path.read_text(encoding="utf-8"))

        result = BioGeoBEARSResult(reference_tree=reference_tree)
        attrs = payload.get("attributes", {}) or {}
        model_name = str(attrs.get("model_name", "BioGeoBEARS") or "BioGeoBEARS")

        result.model_name = "BioGeoBEARS-" + self._pretty_model_name(model_name, attrs)
        result.result_note = "Parsed from BioGeoBEARS wrapper JSON."
        result.input_tree_count = 1
        result.effective_tree_count = 1
        result.model_statistics = self._extract_model_statistics(payload, model_name)

        reference_node_id_map = self._build_reference_node_id_map(reference_tree)
        all_states = []

        for entry in list(payload.get("node_results", []) or []):
            clade_key = str(entry.get("clade_key", "")).strip()
            raw_bgb_node_id = str(entry.get("display_node_id", "") or entry.get("number", "")).strip()
            if not clade_key:
                continue

            unified_display_node_id = reference_node_id_map.get(clade_key, raw_bgb_node_id)
            states = []
            supports = {}
            pie_labels = []
            pie_percents = []

            for state_item in list(entry.get("states", []) or []):
                label = str(state_item.get("label", "")).strip()
                if not label:
                    continue
                prob_percent = float(state_item.get("prob_percent", 0.0) or 0.0)
                states.append(label)
                supports[label] = prob_percent
                pie_labels.append(label)
                pie_percents.append(prob_percent)
                if label not in all_states:
                    all_states.append(label)

            raw_payload = dict(entry)
            raw_payload["bgb_node_id"] = raw_bgb_node_id
            node_result = BioGeoBEARSNodeResult(
                node_key=clade_key,
                display_node_id=unified_display_node_id,
                states=states,
                state_supports=supports,
                pie_labels=pie_labels,
                pie_percents=pie_percents,
                pie_colors=[],
                supporting_tree_count=1,
                total_tree_count=1,
                event_summary="BioGeoBEARS single-tree result",
                raw_method_payload=raw_payload,
            )
            result.node_results[clade_key] = node_result
            result.reference_node_ids[clade_key] = unified_display_node_id

        result.state_order = list(all_states)
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
            node_result.pie_colors = [
                result.state_colors.get(label, "#808080")
                for label in node_result.pie_labels
            ]

        if payload.get("optim_summary", None):
            result.result_note += " optim_summary_present=True"
        self._attach_information_text(result)
        return result

    def _pretty_model_name(self, model_name, attrs):
        pretty = {
            "DEC": "DEC",
            "DECJ": "DEC+J",
            "DIVALIKE": "DIVALIKE",
            "DIVALIKEJ": "DIVALIKE+J",
            "BAYAREALIKE": "BAYAREALIKE",
            "BAYAREALIKEJ": "BAYAREALIKE+J",
        }.get(model_name, model_name)
        if not self._safe_bool(attrs.get("include_null_range", True)):
            pretty = "%s (no null range)" % pretty
        return pretty

    def _build_reference_node_id_map(self, reference_tree):
        mapping = {}
        if reference_tree is None or not hasattr(reference_tree, "traverse"):
            return mapping

        try:
            taxon_count = len(reference_tree.get_leaf_names())
        except Exception:
            taxon_count = 0

        counter = 0
        for node in reference_tree.traverse("postorder"):
            if node.is_leaf():
                continue
            counter += 1
            clade_key = "|".join(sorted(node.get_leaf_names()))
            mapping[clade_key] = str(taxon_count + counter)
        return mapping

    def _safe_float(self, value):
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _safe_bool(self, value):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("0", "false", "f", "no", "n", "exclude"):
            return False
        if text in ("1", "true", "t", "yes", "y", "include"):
            return True
        return bool(value)

    def _extract_model_statistics(self, payload, model_name):
        attrs = payload.get("attributes", {}) or {}
        optim_summary = payload.get("optim_summary", {}) or {}

        optim_result = optim_summary.get("optim_result", None)
        optim_item = None
        if isinstance(optim_result, list) and optim_result:
            optim_item = optim_result[0]
        elif isinstance(optim_result, dict):
            optim_item = optim_result

        log_likelihood = None
        if isinstance(optim_item, dict):
            for key in ("value", "LnL", "lnL", "loglik", "log_likelihood"):
                if key in optim_item:
                    log_likelihood = self._safe_float(optim_item.get(key))
                    if log_likelihood is not None:
                        break
        if log_likelihood is None:
            for key in ("total_loglik", "LnL", "lnL", "log_likelihood"):
                if key in optim_summary:
                    log_likelihood = self._safe_float(optim_summary.get(key))
                    if log_likelihood is not None:
                        break

        num_params = 3 if str(model_name).upper().endswith("J") else 2
        sample_size = self._safe_float(attrs.get("tip_count", None))
        if sample_size is not None:
            sample_size = int(sample_size)

        return {
            "model_name": model_name,
            "log_likelihood": log_likelihood,
            "num_params": num_params,
            "sample_size": sample_size,
            "j_parameter_mode": attrs.get("j_parameter_mode", ""),
            "j_parameter_init": attrs.get("j_parameter_init", ""),
            "j_parameter_est": attrs.get("j_parameter_est", ""),
            "nested_start_used": self._safe_bool(attrs.get("nested_start_used", False)),
            "nested_base_model": attrs.get("nested_base_model", ""),
            "nested_dstart": self._safe_float(attrs.get("nested_dstart", None)),
            "nested_estart": self._safe_float(attrs.get("nested_estart", None)),
            "nested_jstart": self._safe_float(attrs.get("nested_jstart", None)),
            "nested_base_loglik": self._safe_float(attrs.get("nested_base_loglik", None)),
            "nested_base_reused": self._safe_bool(attrs.get("nested_base_reused", False)),
            "include_null_range": self._safe_bool(attrs.get("include_null_range", True)),
            "null_range_mode": attrs.get("null_range_mode", "include"),
            "requested_cores": attrs.get("requested_cores", attrs.get("cores", "")),
            "cores": attrs.get("cores", ""),
            "requested_threads": attrs.get("requested_cores", attrs.get("cores", "")),
            "threads": attrs.get("cores", ""),
            "cores_fallback_to_one": self._safe_bool(attrs.get("cores_fallback_to_one", False)),
        }

    def _attach_information_text(self, result):
        lines = []
        method_name = str(getattr(result, "model_name", "") or "BioGeoBEARS")
        lines.append("%s result summary" % method_name)
        lines.append("")
        lines.append("Internal nodes: %d" % len(getattr(result, "node_results", {}) or {}))

        stats = dict(getattr(result, "model_statistics", {}) or {})
        if stats:
            for key in ["log_likelihood", "num_params", "sample_size", "include_null_range", "null_range_mode", "cores"]:
                if key in stats and stats.get(key) not in (None, ""):
                    lines.append("%s: %s" % (key, stats.get(key)))

        node_results = list((getattr(result, "node_results", {}) or {}).values())
        if node_results:
            lines.append("")
            lines.append("Top ancestral range per node")
            for node in sorted(node_results, key=lambda n: self._node_id_sort_key(getattr(n, "display_node_id", ""))):
                states = list(getattr(node, "states", []) or [])
                if not states:
                    continue
                supports = dict(getattr(node, "state_supports", {}) or {})
                best = states[0]
                best_support = supports.get(best, "")
                if best_support != "":
                    lines.append("node %s: %s %.2f" % (getattr(node, "display_node_id", ""), best, float(best_support)))
                else:
                    lines.append("node %s: %s" % (getattr(node, "display_node_id", ""), best))

        result.information_text = "\n".join(lines)
        result.time_summary_text = "No structured event/time data is attached to this result."

    def _node_id_sort_key(self, value):
        text = str(value or "").strip()
        try:
            return (0, int(text))
        except Exception:
            return (1, text)

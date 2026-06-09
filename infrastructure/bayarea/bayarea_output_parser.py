import re
from collections import Counter, defaultdict
from pathlib import Path

from domain.models.biogeobears_result import BioGeoBEARSNodeResult, BioGeoBEARSResult


class BayAreaOutputParser:
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
        if run_files.area_states_path is None or not run_files.area_states_path.exists():
            raise FileNotFoundError("BayArea area_states output was not found.")

        result = BioGeoBEARSResult(reference_tree=reference_tree)
        result.model_name = "BayArea"
        result.result_note = "Parsed from BayArea v1.0.3 output. workdir=%s" % run_files.workdir
        result.input_tree_count = 1
        result.effective_tree_count = 1

        counts_by_node = defaultdict(Counter)
        bit_counts_by_node = defaultdict(Counter)
        samples_by_node = defaultdict(int)
        ln_likelihood_by_cycle = {}

        lines = run_files.area_states_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            try:
                cycle = int(float(parts[0]))
                ln_likelihood = float(parts[1])
                node_index = int(parts[2])
            except Exception:
                continue
            if not self._include_sample(cycle, run_files.burnin):
                continue
            ln_likelihood_by_cycle[cycle] = ln_likelihood
            if node_index < int(run_files.taxon_count):
                continue
            clade_key = run_files.node_index_to_clade.get(node_index)
            if not clade_key:
                continue
            bits = self._normalize_bits(str(parts[3]).strip(), len(run_files.area_names))
            label = self._bits_to_label(bits, run_files.area_names)
            counts_by_node[clade_key][label] += 1
            bit_counts_by_node[clade_key][bits] += 1
            samples_by_node[clade_key] += 1

        all_states = []
        for clade_key, counter in counts_by_node.items():
            total = max(1, int(samples_by_node.get(clade_key, 0) or 0))
            ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
            states = [label for label, _count in ordered]
            supports = {
                label: float(count) * 100.0 / float(total)
                for label, count in ordered
            }
            for state in states:
                if state not in all_states:
                    all_states.append(state)
            raw_payload = {
                "bayarea_counts": dict(counter),
                "bayarea_bit_counts": dict(bit_counts_by_node.get(clade_key, {})),
                "bayarea_samples": total,
                "source_area_states": str(run_files.area_states_path),
            }
            node_result = BioGeoBEARSNodeResult(
                node_key=clade_key,
                display_node_id=str(run_files.clade_to_reference_node_id.get(clade_key, "")),
                states=states,
                state_supports=supports,
                pie_labels=states,
                pie_percents=[supports[state] for state in states],
                pie_colors=[],
                supporting_tree_count=1,
                total_tree_count=1,
                event_summary="BayArea posterior ancestral range probabilities",
                raw_method_payload=raw_payload,
            )
            result.node_results[clade_key] = node_result
            result.reference_node_ids[clade_key] = node_result.display_node_id

        result.state_order = all_states
        result.state_colors = self._build_state_colors(all_states)
        for node_result in result.node_results.values():
            node_result.pie_colors = [
                result.state_colors.get(label, "#808080")
                for label in node_result.pie_labels
            ]

        ln_likelihoods = [
            ln_likelihood_by_cycle[key]
            for key in sorted(ln_likelihood_by_cycle.keys())
        ]
        result.model_statistics = self._build_model_statistics(run_files, run_output, ln_likelihoods)
        try:
            analysis_log_path = self._write_legacy_analysis_log(
                reference_tree=reference_tree,
                run_files=run_files,
                counts_by_node=counts_by_node,
                bit_counts_by_node=bit_counts_by_node,
                samples_by_node=samples_by_node,
            )
            result.analysis_log_path = str(analysis_log_path)
            result.model_statistics["analysis_log_path"] = str(analysis_log_path)
            run_files.analysis_log_path = analysis_log_path
        except Exception as exc:
            result.parse_warnings.append("Could not write legacy BayArea analysis_result.log: %s" % exc)
        if not result.node_results:
            result.parse_warnings.append("BayArea output did not contain any internal-node state samples.")
        return result

    def _include_sample(self, cycle: int, burnin: int) -> bool:
        burnin = int(burnin or 0)
        if burnin <= 0:
            return True
        return int(cycle) >= burnin

    def _bits_to_label(self, bits: str, area_names) -> str:
        labels = []
        for area, bit in zip(list(area_names or []), str(bits or "")):
            if str(bit) == "1":
                labels.append(str(area))
        return "".join(labels) if labels else "/"

    def _normalize_bits(self, bits: str, area_count: int) -> str:
        text = "".join(ch for ch in str(bits or "").strip() if ch in ("0", "1"))
        area_count = max(0, int(area_count or 0))
        if len(text) < area_count:
            text = text + ("0" * (area_count - len(text)))
        if len(text) > area_count:
            text = text[:area_count]
        return text

    def _build_state_colors(self, states):
        colors = {}
        palette_index = 0
        for state in states:
            if state == "/":
                colors[state] = "#ffffff"
            else:
                colors[state] = self.PALETTE[palette_index % len(self.PALETTE)]
                palette_index += 1
        return colors

    def _build_model_statistics(self, run_files, run_output, ln_likelihoods):
        metadata = dict(getattr(run_files, "extra_metadata", {}) or {})
        stdout = str(getattr(run_output, "stdout", "") or "")
        seed = metadata.get("seed", None)
        match = re.search(r"Random number seed\s*=\s*(\d+)", stdout)
        if match:
            seed = int(match.group(1))
        return {
            "model_name": "BayArea",
            "bayarea_model_type": metadata.get("model_type", ""),
            "chain_length": int(run_files.chain_length),
            "sample_frequency": int(run_files.sample_frequency),
            "burnin": int(run_files.burnin),
            "sampled_lnL_count": len(ln_likelihoods),
            "last_lnL": float(ln_likelihoods[-1]) if ln_likelihoods else None,
            "seed": seed,
            "parameters_path": str(run_files.parameters_path or ""),
            "area_states_path": str(run_files.area_states_path or ""),
            "area_probs_path": str(run_files.area_probs_path or ""),
            "nhx_path": str(run_files.nhx_path or ""),
            "analysis_log_path": str(getattr(run_files, "analysis_log_path", "") or ""),
        }

    def _write_legacy_analysis_log(
        self,
        *,
        reference_tree,
        run_files,
        counts_by_node,
        bit_counts_by_node,
        samples_by_node,
    ) -> Path:
        path = Path(run_files.workdir) / "analysis_result.log"
        area_names = list(run_files.area_names or [])
        clade_rows = self._legacy_clade_rows(reference_tree, run_files)

        lines = ["Bayarea Analysis Result file"]
        lines.append("[TAXON]")
        lines.extend(self._legacy_taxon_lines(run_files))
        lines.append("[TREE]")
        lines.append("Tree=" + self._legacy_tree_line(reference_tree, run_files))
        lines.append("[RESULT]")
        lines.append("Result of Bayarea:")

        for clade_key, display_id, terminal_span in clade_rows:
            counts = counts_by_node.get(clade_key, Counter())
            total = int(samples_by_node.get(clade_key, 0) or 0)
            prefix = "node %s (anc. of terminals %s):" % (display_id, terminal_span)
            if total <= 0:
                lines.append(prefix)
                continue
            parts = []
            for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
                parts.append("%s %.2f" % (label, float(count) * 100.0 / float(total)))
            lines.append(prefix + (" " + " ".join(parts) if parts else ""))

        lines.append("[PROBABILITY]")
        header = "\t"
        for area in area_names:
            header += "%s(0)\t%s(1)\t" % (area, area)
        lines.append(header)

        for clade_key, display_id, _terminal_span in clade_rows:
            bit_counts = bit_counts_by_node.get(clade_key, Counter())
            total = int(samples_by_node.get(clade_key, 0) or 0)
            probabilities = self._legacy_area_probabilities(bit_counts, total, len(area_names))
            line = "node %s:" % display_id
            for p0, p1 in probabilities:
                line += "\t%.6f\t%.6f" % (p0, p1)
            lines.append(line)

        lines.append("[END]")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _legacy_taxon_lines(self, run_files):
        bits_by_id = {}
        areas_path = Path(run_files.areas_path)
        if areas_path.exists():
            for line in areas_path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    bits_by_id[str(parts[0])] = self._normalize_bits(parts[1], len(run_files.area_names))

        lines = []
        for taxon_id, taxon_name in zip(list(run_files.taxon_ids or []), list(run_files.taxon_names or [])):
            bits = bits_by_id.get(str(taxon_id), "")
            distribution = self._bits_to_label(bits, run_files.area_names) if bits else ""
            lines.append("%s\t%s\t%s" % (taxon_id, taxon_name, distribution))
        return lines

    def _legacy_tree_line(self, reference_tree, run_files):
        id_by_name = {
            str(name): str(taxon_id)
            for name, taxon_id in zip(list(run_files.taxon_names or []), list(run_files.taxon_ids or []))
        }
        return self._node_to_legacy_newick(reference_tree, id_by_name, is_root=True) + ";"

    def _node_to_legacy_newick(self, node, id_by_name, is_root=False) -> str:
        if self._is_leaf(node):
            name = str(getattr(node, "name", "") or "").strip()
            label = id_by_name.get(name, name)
            return "%s:%s" % (self._safe_newick_label(label), self._format_float(self._node_dist(node)))

        children = list(getattr(node, "children", []) or [])
        child_text = ",".join(self._node_to_legacy_newick(child, id_by_name, is_root=False) for child in children)
        if is_root:
            return "(%s)" % child_text
        return "(%s):%s" % (child_text, self._format_float(self._node_dist(node)))

    def _legacy_clade_rows(self, reference_tree, run_files):
        rows = []
        display_by_clade = dict(run_files.clade_to_reference_node_id or {})
        for clade_key, display_id in display_by_clade.items():
            rows.append((clade_key, str(display_id), self._terminal_span(clade_key, run_files)))
        return sorted(rows, key=lambda item: self._display_sort_key(item[1]))

    def _terminal_span(self, clade_key, run_files) -> str:
        id_by_name = {
            str(name): str(taxon_id)
            for name, taxon_id in zip(list(run_files.taxon_names or []), list(run_files.taxon_ids or []))
        }
        ids = []
        for name in str(clade_key or "").split("|"):
            clean = str(name).strip()
            if clean:
                ids.append(id_by_name.get(clean, clean))
        ids = sorted(ids, key=self._display_sort_key)
        if not ids:
            return ""
        return "%s-%s" % (ids[0], ids[-1])

    def _legacy_area_probabilities(self, bit_counts, total, area_count):
        if total <= 0:
            return [(1.0, 0.0) for _ in range(int(area_count or 0))]

        present = [0 for _ in range(int(area_count or 0))]
        for bits, count in dict(bit_counts or {}).items():
            norm = self._normalize_bits(bits, area_count)
            for idx, bit in enumerate(norm):
                if bit == "1":
                    present[idx] += int(count)

        probabilities = []
        denom = float(total)
        for count in present:
            p1 = float(count) / denom
            probabilities.append((1.0 - p1, p1))
        return probabilities

    def _display_sort_key(self, value):
        text = str(value or "").strip()
        try:
            return (0, int(text))
        except Exception:
            return (1, text)

    def _is_leaf(self, node) -> bool:
        try:
            return bool(node.is_leaf())
        except Exception:
            return not bool(getattr(node, "children", []) or [])

    def _node_dist(self, node) -> float:
        try:
            return float(getattr(node, "dist", 0.0) or 0.0)
        except Exception:
            return 0.0

    def _safe_newick_label(self, label: str) -> str:
        text = str(label or "").strip()
        if not text:
            return ""
        if any(ch in text for ch in [" ", "\t", "\n", "\r", "(", ")", ",", ":", ";"]):
            return "'" + text.replace("'", "_") + "'"
        return text

    def _format_float(self, value) -> str:
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return "%.12g" % number

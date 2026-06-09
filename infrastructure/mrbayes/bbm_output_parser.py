import itertools
from collections import OrderedDict
from pathlib import Path

from domain.models.biogeobears_result import BioGeoBEARSNodeResult, BioGeoBEARSResult


class BBMOutputParser:
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
        run1 = self._read_run_probabilities(run_files.run1_p_path, run_files)
        run2 = self._read_run_probabilities(run_files.run2_p_path, run_files)
        combined = self._combine_runs(run1, run2)

        self._write_clade_log(run_files, run1, run2, combined)

        result = BioGeoBEARSResult(reference_tree=reference_tree)
        result.model_name = "BBM"
        result.result_note = (
            "Bayesian Binary MCMC via MrBayes restriction data; ancestral ranges "
            "are reconstructed from area-wise posterior marginals."
        )
        result.input_tree_count = 1
        result.effective_tree_count = 1
        result.config = run_files.config

        all_states = []
        global_sums = {}
        rows_for_log = []
        for record in list(run_files.node_records or []):
            display_id = str(record["display_node_id"])
            clade_key = str(record["clade_key"])
            probabilities = combined.get(display_id, self._absent_probabilities(len(run_files.area_names)))
            states = self._range_probabilities(probabilities, run_files.config, run_files.area_names)
            rows_for_log.append((record, states, probabilities))
            if not states:
                continue

            for state in states.keys():
                if state not in all_states:
                    all_states.append(state)
                global_sums[state] = global_sums.get(state, 0.0) + float(states[state])

            node_result = BioGeoBEARSNodeResult(
                node_key=clade_key,
                display_node_id=display_id,
                states=list(states.keys()),
                state_supports=dict(states),
                pie_labels=list(states.keys()),
                pie_percents=[states[state] for state in states.keys()],
                pie_colors=[],
                supporting_tree_count=1,
                total_tree_count=1,
                event_summary="BBM posterior ancestral range probabilities",
                raw_method_payload={
                    "area_marginals": self._area_marginal_payload(probabilities, run_files.area_names),
                    "run1_area_marginals": self._area_marginal_payload(
                        run1.get(display_id, self._absent_probabilities(len(run_files.area_names))),
                        run_files.area_names,
                    ),
                    "run2_area_marginals": self._area_marginal_payload(
                        run2.get(display_id, self._absent_probabilities(len(run_files.area_names))),
                        run_files.area_names,
                    ),
                    "terminal_span": str(record.get("terminal_span", "")),
                    "source_run1_p": str(run_files.run1_p_path or ""),
                    "source_run2_p": str(run_files.run2_p_path or ""),
                },
            )
            result.node_results[clade_key] = node_result
            result.reference_node_ids[clade_key] = display_id

        result.state_order = all_states
        result.state_colors = self._build_state_colors(all_states)
        for node_result in result.node_results.values():
            node_result.pie_colors = [
                result.state_colors.get(label, "#808080")
                for label in node_result.pie_labels
            ]

        self._write_analysis_log(run_files, rows_for_log, run1, run2, combined)
        result.analysis_log_path = str(run_files.analysis_log_path)
        result.model_statistics = {
            "model_name": "BBM",
            "chain_length": int(run_files.config.chain_length),
            "sample_frequency": int(run_files.config.sample_frequency),
            "discard_samples": int(run_files.config.discard_samples),
            "chains": int(run_files.config.chains),
            "temperature": float(run_files.config.temperature),
            "selected_node_count": len(run_files.selected_node_ids),
            "node_count": len(run_files.node_records),
            "run1_p_path": str(run_files.run1_p_path or ""),
            "run2_p_path": str(run_files.run2_p_path or ""),
            "mcmc_path": str(run_files.mcmc_path or ""),
            "clade_log_path": str(run_files.clade_log_path or ""),
            "analysis_log_path": str(run_files.analysis_log_path or ""),
        }
        if not result.node_results:
            result.parse_warnings.append("BBM output did not contain any selected-node state probabilities.")
        return result

    def _read_run_probabilities(self, path: Path, run_files) -> dict:
        if path is None or not Path(path).exists():
            raise FileNotFoundError("MrBayes .p output was not found: %s" % path)

        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        header_index = self._find_header_index(lines)
        if header_index < 0:
            raise ValueError("Could not find MrBayes .p header in %s" % path)

        header = lines[header_index].split("\t")
        data_lines = []
        for line in lines[header_index + 1:]:
            if not line.strip() or line.lstrip().startswith("["):
                continue
            parts = line.split("\t")
            if not parts:
                continue
            try:
                float(parts[0])
            except Exception:
                continue
            data_lines.append(parts)

        skip_count = int(run_files.config.discard_samples) + 1
        kept = data_lines[skip_count:]
        if not kept:
            raise ValueError("No BBM samples remain after discarding %s samples." % run_files.config.discard_samples)

        selected_records = [
            record
            for record in list(run_files.node_records or [])
            if str(record["display_node_id"]) in set(run_files.selected_node_ids)
        ]
        area_count = len(run_files.area_names)
        values = {}
        for selected_index, record in enumerate(selected_records):
            node_id = str(record["display_node_id"])
            sums = [[0.0, 0.0] for _ in range(area_count)]
            counts = [[0, 0] for _ in range(area_count)]
            for parts in kept:
                for area_index in range(area_count):
                    p0_index, p1_index = self._column_indexes(
                        header=header,
                        area_index=area_index,
                        selected_index=selected_index,
                        area_count=area_count,
                    )
                    for state_index, col_index in enumerate([p0_index, p1_index]):
                        if col_index < len(parts):
                            try:
                                sums[area_index][state_index] += float(parts[col_index])
                                counts[area_index][state_index] += 1
                            except Exception:
                                pass
            values[node_id] = [
                (
                    sums[idx][0] / counts[idx][0] if counts[idx][0] else 1.0,
                    sums[idx][1] / counts[idx][1] if counts[idx][1] else 0.0,
                )
                for idx in range(area_count)
            ]

        for record in list(run_files.node_records or []):
            node_id = str(record["display_node_id"])
            if node_id not in values:
                values[node_id] = self._absent_probabilities(area_count)
        return values

    def _find_header_index(self, lines) -> int:
        for index, line in enumerate(lines):
            parts = line.split("\t")
            if not parts:
                continue
            first = parts[0].strip().lower()
            if first in ("gen", "generation", "state"):
                return index
        for index, line in enumerate(lines):
            if "\t" in line and "p(" in line:
                return index
        return -1

    def _column_indexes(self, *, header, area_index, selected_index, area_count):
        # Legacy RASP reads MrBayes .p files by column position.  The first
        # ancestral-state probability starts after the fixed run-stat columns,
        # with optional lnPr/alpha columns shifting the block.
        with_g = 0
        if len(header) > 2 and header[2].strip().lower() == "lnpr":
            with_g += 1
        alpha_index = 5 + with_g
        if len(header) > alpha_index and header[alpha_index].strip().lower() == "alpha":
            with_g += 1
        base = 5 + with_g
        offset = selected_index * area_count * 2 + area_index * 2
        return base + offset, base + offset + 1

    def _combine_runs(self, run1, run2):
        combined = {}
        for node_id in sorted(set(run1.keys()) | set(run2.keys()), key=self._display_sort_key):
            p1 = run1.get(node_id)
            p2 = run2.get(node_id)
            if p1 is None:
                combined[node_id] = p2
                continue
            if p2 is None:
                combined[node_id] = p1
                continue
            combined[node_id] = [
                ((a0 + b0) / 2.0, (a1 + b1) / 2.0)
                for (a0, a1), (b0, b1) in zip(p1, p2)
            ]
        return combined

    def _range_probabilities(self, area_probabilities, config, area_names):
        area_names = list(area_names or [])
        max_areas = min(int(config.max_areas), len(area_names))
        raw = []
        for size in range(1, max_areas + 1):
            for combo in itertools.combinations(range(len(area_names)), size):
                combo_set = set(combo)
                probability = 1.0
                label_parts = []
                for idx, area in enumerate(area_names):
                    p0, p1 = area_probabilities[idx]
                    if idx in combo_set:
                        probability *= float(p1)
                        label_parts.append(str(area))
                    else:
                        probability *= float(p0)
                raw.append(("".join(label_parts), probability))

        if bool(config.include_null_range):
            probability = 1.0
            for p0, _p1 in area_probabilities:
                probability *= float(p0)
            raw.append(("/", probability))

        total = sum(probability for _label, probability in raw)
        if total <= 0:
            return OrderedDict()

        ordered = sorted(raw, key=lambda item: (-float(item[1]), item[0]))
        result = OrderedDict()
        for label, probability in ordered:
            result[label] = float(probability) * 100.0 / float(total)
        return result

    def _write_clade_log(self, run_files, run1, run2, combined):
        lines = []
        for source in [run1, run2, combined]:
            for record in list(run_files.node_records or []):
                node_id = str(record["display_node_id"])
                suffix = ""
                if source is run1:
                    suffix = ".run1.p"
                elif source is run2:
                    suffix = ".run2.p"
                values = source.get(node_id, self._absent_probabilities(len(run_files.area_names)))
                line = "clade%s%s =" % (record["node_index"], suffix)
                for p0, p1 in values:
                    line += "\t%.6f\t%.6f" % (float(p0), float(p1))
                lines.append(line)
            lines.append("------------------")
        run_files.clade_log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_analysis_log(self, run_files, rows_for_log, run1, run2, combined):
        lines = ["Bayesian Analysis result file"]
        lines.append("[TAXON]")
        distributions = self._read_taxon_distributions(run_files)
        for taxon_id, taxon_name in zip(run_files.taxon_ids, run_files.taxon_names):
            lines.append("%s\t%s\t%s" % (taxon_id, taxon_name, distributions.get(str(taxon_id), "")))
        lines.append("[TREE]")
        lines.append("Tree=" + str(run_files.numeric_tree_text))
        lines.append("[RESULT]")

        for title, source in [
            ("Result of combined:", combined),
            ("Result of run 1:", run1),
            ("Result of run 2:", run2),
        ]:
            lines.append(title)
            for record, _states, _probabilities in rows_for_log:
                node_id = str(record["display_node_id"])
                states = self._range_probabilities(
                    source.get(node_id, self._absent_probabilities(len(run_files.area_names))),
                    run_files.config,
                    run_files.area_names,
                )
                prefix = "node %s (anc. of terminals %s):" % (
                    node_id,
                    str(record.get("terminal_span", "")),
                )
                if states:
                    prefix += " " + " ".join(
                        "%s %.2f" % (label, percent)
                        for label, percent in states.items()
                    )
                lines.append(prefix)

        lines.append("[PROBABILITY]")
        header = "\t"
        for area in run_files.area_names:
            header += "%s(0)\t%s(1)\t" % (area, area)
        lines.append(header)
        for record, _states, _probabilities in rows_for_log:
            node_id = str(record["display_node_id"])
            line = "node %s:" % node_id
            for p0, p1 in combined.get(node_id, self._absent_probabilities(len(run_files.area_names))):
                line += "\t%.6f\t%.6f" % (float(p0), float(p1))
            lines.append(line)

        lines.append("[END]")
        run_files.analysis_log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _read_taxon_distributions(self, run_files):
        distributions = {}
        for taxon_id, taxon_name in zip(run_files.taxon_ids, run_files.taxon_names):
            distributions[str(taxon_id)] = ""
        # Reconstruct from the generated NEXUS matrix so the log matches the
        # exact input passed to MrBayes.
        text = run_files.nexus_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            clean = line.strip()
            if not clean.startswith("TID"):
                continue
            parts = clean.split()
            if len(parts) < 2:
                continue
            taxon_id = parts[0][3:]
            distributions[taxon_id] = self._bits_to_label(parts[1], run_files.area_names)
        return distributions

    def _area_marginal_payload(self, values, area_names):
        payload = {}
        for area, (p0, p1) in zip(list(area_names or []), list(values or [])):
            payload[str(area)] = {"0": float(p0), "1": float(p1)}
        return payload

    def _bits_to_label(self, bits, area_names):
        labels = []
        for area, bit in zip(list(area_names or []), str(bits or "")):
            if bit == "1":
                labels.append(str(area))
        return "".join(labels) if labels else "/"

    def _absent_probabilities(self, area_count):
        return [(1.0, 0.0) for _ in range(int(area_count or 0))]

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

    def _display_sort_key(self, value):
        text = str(value or "").strip()
        try:
            return (0, int(text))
        except Exception:
            return (1, text)

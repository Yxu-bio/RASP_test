import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from domain.models.bayestraits_config import (
    BAYESTRAITS_MODELS,
    BayesTraitsConfig,
    normalize_bayestraits_continuous_transform,
    normalize_bayestraits_model,
)


@dataclass
class BayesTraitsRunFiles:
    workdir: Path
    trees_path: Path
    data_path: Path
    commands_path: Path
    manifest_path: Path
    stdout_log_path: Path
    stderr_log_path: Path
    analysis_log_path: Path

    taxon_names: List[str]
    taxon_ids: List[str]
    taxon_count: int
    node_records: List[Dict[str, object]]
    selected_node_ids: List[str]
    state_symbols: List[str]
    state_display_labels: Dict[str, str]
    numeric_reference_tree_text: str
    tree_count: int
    config: BayesTraitsConfig

    output_log_path: Optional[Path] = None
    stones_path: Optional[Path] = None
    model_save_commands_path: Optional[Path] = None
    estimate_commands_path: Optional[Path] = None
    model_save_path: Optional[Path] = None
    continuous_asr: bool = False
    extra_metadata: Dict[str, object] = field(default_factory=dict)


class BayesTraitsDatasetBuilder:
    """
    Build the legacy BayesTraits input triplet used by RASP:
    trait.trees, trait.dat and trait.ini.
    """

    MISSING_TOKENS = {"", "-", "\\", "?", "NA", "N/A", "NULL", "NONE", "NAN"}
    PALETTE_SYMBOLS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    def build(
        self,
        *,
        reference_tree,
        matrix,
        tree_entries=None,
        config: BayesTraitsConfig,
        output_dir,
        run_name="bayestraits_run",
    ) -> BayesTraitsRunFiles:
        config.validate()
        workdir = Path(output_dir) / run_name
        workdir.mkdir(parents=True, exist_ok=True)

        if reference_tree is None:
            raise ValueError("BayesTraits requires a reference/consensus tree.")
        if matrix is None:
            raise ValueError("BayesTraits requires a trait matrix.")

        model = normalize_bayestraits_model(getattr(config, "model", "MULTISTATE"))
        model_spec = BAYESTRAITS_MODELS[model]
        continuous_asr = bool(getattr(config, "continuous_asr", False))

        taxon_names = self._leaf_names(reference_tree)
        taxon_id_map = self._collect_taxon_ids(matrix, taxon_names)
        node_records = self.build_node_records(reference_tree, taxon_id_map)

        valid_node_ids = {str(item["display_node_id"]) for item in node_records}
        selected_node_ids = [str(x).strip() for x in list(config.selected_node_ids or []) if str(x).strip()]
        selected_node_ids = [node_id for node_id in selected_node_ids if node_id in valid_node_ids]
        if continuous_asr:
            selected_node_ids = [str(item["display_node_id"]) for item in node_records]
        if bool(model_spec.get("supports_nodes", False)) and not selected_node_ids:
            raise ValueError("Select one node at least.")

        selected_entries = [reference_tree] if continuous_asr else self._select_tree_entries(reference_tree, tree_entries, config)
        for idx, tree in enumerate(selected_entries, start=1):
            missing = sorted(set(taxon_names) ^ set(self._leaf_names(tree)))
            if missing:
                raise ValueError("BayesTraits tree %s taxa do not match the reference tree: %s" % (idx, ", ".join(missing)))

        trait_rows, state_symbols, state_display_labels, raw_state_map = self._collect_trait_rows(
            matrix=matrix,
            taxon_names=taxon_names,
            taxon_id_map=taxon_id_map,
            config=config,
        )

        trees_path = workdir / "trait.trees"
        data_path = workdir / "trait.dat"
        commands_path = workdir / "trait.ini"
        model_save_commands_path = workdir / "trait_save_models.ini"
        estimate_commands_path = workdir / "trait_estimate_nodes.ini"
        model_save_path = workdir / "RASP_continuous_models.bin"
        manifest_path = workdir / "bayestraits_manifest.json"
        stdout_log_path = workdir / "bayestraits_stdout.log"
        stderr_log_path = workdir / "bayestraits_stderr.log"
        analysis_log_path = workdir / "analysis_result.log"

        self._remove_stale_outputs(workdir)

        numeric_reference_tree_text = self._node_to_translated_newick(reference_tree, taxon_id_map, is_root=True) + ";"
        self._write_trees_file(trees_path, selected_entries, taxon_id_map)
        self._write_trait_data(data_path, trait_rows)
        if continuous_asr:
            self._validate_continuous_asr_trait_rows(trait_rows)
            self._write_continuous_asr_commands(
                model_save_commands_path=model_save_commands_path,
                estimate_commands_path=estimate_commands_path,
                model_save_path=model_save_path,
                config=config,
                node_records=node_records,
            )
            commands_path = estimate_commands_path
        else:
            self._write_commands(
                commands_path=commands_path,
                config=config,
                node_records=node_records,
                selected_node_ids=selected_node_ids,
                state_display_labels=state_display_labels,
            )

        run_files = BayesTraitsRunFiles(
            workdir=workdir,
            trees_path=trees_path,
            data_path=data_path,
            commands_path=commands_path,
            manifest_path=manifest_path,
            stdout_log_path=stdout_log_path,
            stderr_log_path=stderr_log_path,
            analysis_log_path=analysis_log_path,
            taxon_names=taxon_names,
            taxon_ids=[taxon_id_map[name] for name in taxon_names],
            taxon_count=len(taxon_names),
            node_records=node_records,
            selected_node_ids=selected_node_ids,
            state_symbols=state_symbols,
            state_display_labels=state_display_labels,
            numeric_reference_tree_text=numeric_reference_tree_text,
            tree_count=len(selected_entries),
            config=config,
            model_save_commands_path=model_save_commands_path if continuous_asr else None,
            estimate_commands_path=estimate_commands_path if continuous_asr else None,
            model_save_path=model_save_path if continuous_asr else None,
            continuous_asr=continuous_asr,
            extra_metadata={
                "taxon_id_map": dict(taxon_id_map),
                "raw_state_map": dict(raw_state_map),
                "continuous_tip_values": self._continuous_tip_values(
                    trait_rows=trait_rows,
                    taxon_names=taxon_names,
                    taxon_id_map=taxon_id_map,
                ) if continuous_asr else {},
            },
        )
        self._write_manifest(run_files)
        return run_files

    def build_node_records(self, tree, taxon_id_map: Dict[str, str]) -> List[Dict[str, object]]:
        taxon_count = len(self._leaf_names(tree))
        records = []
        counter = 0
        try:
            iterator = tree.traverse("postorder")
        except TypeError:
            iterator = tree.traverse()

        for node in iterator:
            if self._is_leaf(node):
                continue
            counter += 1
            leaves = list(self._iter_leaves(node))
            leaf_names = [str(getattr(leaf, "name", "") or "").strip() for leaf in leaves]
            leaf_ids = [str(taxon_id_map.get(name, name)) for name in leaf_names]
            display_id = str(taxon_count + counter)
            records.append({
                "display_node_id": display_id,
                "node_index": counter,
                "clade_key": "|".join(sorted(leaf_names)),
                "leaf_names": leaf_names,
                "leaf_ids": leaf_ids,
                "constraint_taxa": leaf_ids,
                "terminal_span": self._terminal_span(leaf_ids),
                "support": self._node_support_percent(node),
            })
        return records

    def _select_tree_entries(self, reference_tree, tree_entries, config):
        if bool(getattr(config, "use_tree_collection", False)):
            entries = [
                getattr(entry, "parsed_tree", None)
                for entry in list(tree_entries or [])
                if getattr(entry, "parsed_tree", None) is not None
            ]
            if entries:
                return entries
        return [reference_tree]

    def _collect_taxon_ids(self, matrix, taxon_names: List[str]) -> Dict[str, str]:
        name_to_id = {}
        seen_ids = set()
        for row in list(getattr(matrix, "rows", []) or []):
            name = str(row.get("Name", "") or "").strip()
            row_id = str(row.get("ID", "") or "").strip()
            if not name:
                continue
            if not row_id:
                raise ValueError("BayesTraits requires a non-empty ID for taxon '%s'." % name)
            if self._has_unsafe_label_chars(row_id):
                raise ValueError("BayesTraits taxon ID contains unsupported whitespace or punctuation: %s" % row_id)
            if row_id in seen_ids:
                raise ValueError("BayesTraits taxon ID '%s' is duplicated." % row_id)
            seen_ids.add(row_id)
            name_to_id[name] = row_id

        missing = [name for name in taxon_names if name not in name_to_id]
        if missing:
            raise ValueError("BayesTraits could not find matrix IDs for taxa: %s." % ", ".join(sorted(missing)))
        return {name: name_to_id[name] for name in taxon_names}

    def _collect_trait_rows(self, *, matrix, taxon_names, taxon_id_map, config):
        model = normalize_bayestraits_model(getattr(config, "model", "MULTISTATE"))
        model_spec = BAYESTRAITS_MODELS[model]
        trait_columns = [
            str(x).strip()
            for x in list(getattr(config, "selected_trait_columns", []) or [getattr(config, "trait_column", "")])
            if str(x).strip()
        ]
        if not trait_columns:
            trait_columns = [str(config.trait_column or "").strip()]

        if str(model_spec.get("trait_kind", "")) == "continuous":
            return self._collect_continuous_trait_rows(
                matrix=matrix,
                taxon_names=taxon_names,
                taxon_id_map=taxon_id_map,
                config=config,
                trait_columns=trait_columns,
                model_spec=model_spec,
            )

        return self._collect_multistate_trait_rows(
            matrix=matrix,
            taxon_names=taxon_names,
            taxon_id_map=taxon_id_map,
            config=config,
            column=trait_columns[0],
        )

    def _collect_multistate_trait_rows(self, *, matrix, taxon_names, taxon_id_map, config, column):
        column = str(column or "").strip()
        raw_by_taxon = {}
        for row in list(getattr(matrix, "rows", []) or []):
            name = str(row.get("Name", "") or "").strip()
            if name:
                raw_by_taxon[name] = str(row.get(column, "") or "").strip()

        raw_values = []
        for name in taxon_names:
            value = self._normalize_raw_trait_value(raw_by_taxon.get(name, ""))
            if self._is_missing(value):
                continue
            raw_values.append(value)

        if not raw_values:
            raise ValueError("BayesTraits trait column '%s' contains no usable states." % column)

        if not bool(config.auto_map_categorical) and self._looks_like_continuous_numeric(raw_values):
            raise ValueError(
                "BayesTraits MultiState requires categorical states, but trait column '%s' "
                "looks like continuous numeric data. Select a categorical trait column, or "
                "use a future Continuous BayesTraits model. Decimal values such as '%s' "
                "would otherwise be interpreted as multiple character states by BayesTraits."
                % (column, raw_values[0])
            )

        raw_state_map = {}
        state_display_labels = {}
        if bool(config.auto_map_categorical):
            unique = []
            for value in raw_values:
                if value not in unique:
                    unique.append(value)
            if len(unique) > len(self.PALETTE_SYMBOLS):
                raise ValueError("BayesTraits categorical auto-map supports at most 26 states.")
            raw_state_map = {value: self.PALETTE_SYMBOLS[idx] for idx, value in enumerate(unique)}
            state_display_labels = {symbol: raw for raw, symbol in raw_state_map.items()}
        else:
            state_display_labels = {}

        rows = []
        state_symbols = []
        for name in taxon_names:
            taxon_id = taxon_id_map[name]
            raw_value = self._normalize_raw_trait_value(raw_by_taxon.get(name, ""))
            if self._is_missing(raw_value):
                value = "-"
            elif raw_state_map:
                value = raw_state_map[raw_value]
            else:
                value = self._normalize_legacy_state_text(raw_value)
            rows.append((taxon_id, value))
            for symbol in self._state_symbols_from_value(value):
                if symbol not in state_symbols:
                    state_symbols.append(symbol)
                    state_display_labels.setdefault(symbol, symbol)

        if len(state_symbols) < 2:
            raise ValueError("BayesTraits MultiState requires at least two observed states.")
        return rows, state_symbols, state_display_labels, raw_state_map

    def _collect_continuous_trait_rows(self, *, matrix, taxon_names, taxon_id_map, config, trait_columns, model_spec):
        min_traits = int(model_spec.get("min_traits", 1) or 1)
        max_traits = int(model_spec.get("max_traits", 0) or 0)
        transform = normalize_bayestraits_continuous_transform(getattr(config, "continuous_transform", "none"))
        trait_columns = [str(x).strip() for x in list(trait_columns or []) if str(x).strip()]
        if max_traits > 0:
            trait_columns = trait_columns[:max_traits]
        if len(trait_columns) < min_traits:
            raise ValueError("%s requires at least %s trait column(s)." % (model_spec["label"], min_traits))

        rows_by_taxon = {}
        for row in list(getattr(matrix, "rows", []) or []):
            name = str(row.get("Name", "") or "").strip()
            if name:
                rows_by_taxon[name] = row

        output_rows = []
        usable_by_trait = {column: 0 for column in trait_columns}
        for name in taxon_names:
            taxon_id = taxon_id_map[name]
            row = rows_by_taxon.get(name, {})
            values = []
            for column in trait_columns:
                raw_value = self._normalize_raw_trait_value(row.get(column, ""))
                if self._is_missing(raw_value):
                    values.append("-")
                    continue
                if not self._is_decimal_number(raw_value):
                    raise ValueError(
                        "%s requires continuous numeric data, but taxon '%s' has '%s' in column '%s'."
                        % (model_spec["label"], name, raw_value, column)
                    )
                values.append(self._transform_continuous_value(raw_value, transform, name, column))
                usable_by_trait[column] += 1
            output_rows.append((taxon_id, values))

        missing_traits = [column for column, count in usable_by_trait.items() if count == 0]
        if missing_traits:
            raise ValueError("Continuous BayesTraits model has no usable values for: %s" % ", ".join(missing_traits))
        return output_rows, [], {}, {}

    def _transform_continuous_value(self, raw_value, transform, taxon_name, column) -> str:
        transform = normalize_bayestraits_continuous_transform(transform)
        number = float(raw_value)
        if transform == "none":
            return self._format_float(number)
        if number <= 0.0:
            label = "natural log" if transform == "log" else "log10"
            raise ValueError(
                "Continuous trait transform '%s' requires positive values, but taxon '%s' has %s in column '%s'."
                % (label, taxon_name, raw_value, column)
            )
        if transform == "log":
            return self._format_float(math.log(number))
        if transform == "log10":
            return self._format_float(math.log10(number))
        return self._format_float(number)

    def _write_trees_file(self, path: Path, trees, taxon_id_map: Dict[str, str]) -> None:
        sorted_taxa = sorted(taxon_id_map.keys(), key=lambda name: self._display_sort_key(taxon_id_map[name]))
        translate_lines = []
        for idx, taxon_name in enumerate(sorted_taxa, start=1):
            suffix = "," if idx < len(sorted_taxa) else ";"
            translate_lines.append("  %s %s%s" % (idx, self._safe_label(taxon_id_map[taxon_name]), suffix))

        token_map = {name: str(idx) for idx, name in enumerate(sorted_taxa, start=1)}
        lines = ["#NEXUS", "Begin trees;", "Translate"]
        lines.extend(translate_lines)
        for idx, tree in enumerate(trees, start=1):
            lines.append("tree tree_%s = %s" % (
                idx,
                self._node_to_translated_newick(tree, token_map, is_root=True) + ";",
            ))
        lines.append("End;")
        path.write_text("\n".join(lines) + "\n", encoding="ascii", errors="ignore")

    def _write_trait_data(self, path: Path, rows) -> None:
        lines = []
        for taxon_id, values in rows:
            if isinstance(values, (list, tuple)):
                lines.append("%s\t%s" % (taxon_id, "\t".join(str(value) for value in values)))
            else:
                lines.append("%s\t%s" % (taxon_id, values))
        path.write_text("\n".join(lines) + "\n", encoding="ascii", errors="ignore")

    def _write_commands(self, *, commands_path, config, node_records, selected_node_ids, state_display_labels) -> None:
        selected = [record for record in node_records if str(record["display_node_id"]) in set(selected_node_ids)]
        model = normalize_bayestraits_model(getattr(config, "model", "MULTISTATE"))
        model_spec = BAYESTRAITS_MODELS[model]
        lines = [str(int(model_spec["code"]))]
        lines.append("1" if str(config.analysis_method).upper() == "ML" else "2")

        fossils = dict(config.fossil_states or {})
        if bool(model_spec.get("supports_nodes", False)):
            for record in selected:
                node_id = str(record["display_node_id"])
                tag_name = "TNode%s" % node_id
                lines.append("AddTag %s %s" % (tag_name, " ".join(str(x) for x in record.get("constraint_taxa", []))))
                lines.append("AddNode Node%s %s" % (node_id, tag_name))
                fossil_state = str(fossils.get(node_id, "") or "").strip()
                if fossil_state:
                    state_text = self._normalize_fossil_state(fossil_state, state_display_labels)
                    lines.append("Fossil FNode%s %s %s" % (node_id, tag_name, state_text))

        if str(config.analysis_method).upper() == "ML":
            lines.append("MLTries %s" % int(config.ml_tries))
        else:
            seed = int(getattr(config, "random_seed", 0) or 0)
            if seed > 0:
                lines.append("Seed %s" % seed)
            lines.append("Sample %s" % int(config.sample_frequency))
            lines.append("Iterations %s" % int(config.iterations))
            lines.append("BurnIn %s" % int(config.burnin))
            for optional in [config.hyper_prior_all, config.revjump_hp, config.stones, config.restrict_all]:
                if str(optional or "").strip():
                    lines.append(str(optional).strip())

        for line in str(config.extra_commands or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
            clean = line.strip()
            if clean:
                lines.append(clean)
        lines.append("run")
        commands_path.write_text("\n".join(lines) + "\n", encoding="ascii", errors="ignore")

    def _write_continuous_asr_commands(self, *, model_save_commands_path, estimate_commands_path, model_save_path, config, node_records) -> None:
        model = normalize_bayestraits_model(getattr(config, "model", "CONTINUOUS_RANDOM_WALK"))
        model_spec = BAYESTRAITS_MODELS[model]

        build_lines = [str(int(model_spec["code"])), "2"]
        self._append_mcmc_lines(build_lines, config, include_stones=False)
        self._append_extra_command_lines(build_lines, config)
        build_lines.append("SaveModels %s" % Path(model_save_path).name)
        build_lines.append("run")
        Path(model_save_commands_path).write_text("\n".join(build_lines) + "\n", encoding="ascii", errors="ignore")

        estimate_lines = [str(int(model_spec["code"])), "2"]
        self._append_mcmc_lines(estimate_lines, config, include_stones=False)
        self._append_extra_command_lines(estimate_lines, config)
        estimate_lines.append("LoadModels %s" % Path(model_save_path).name)
        for record in list(node_records or []):
            node_id = str(record.get("display_node_id", "") or "").strip()
            if not node_id:
                continue
            tag_name = "RASP_TAG_%s" % node_id
            estimate_name = "RASP_NODE_%s" % node_id
            taxa = " ".join(str(x) for x in record.get("constraint_taxa", []) if str(x))
            if not taxa:
                continue
            estimate_lines.append("AddTag %s %s" % (tag_name, taxa))
            estimate_lines.append("AddMRCA %s %s" % (estimate_name, tag_name))
        estimate_lines.append("run")
        Path(estimate_commands_path).write_text("\n".join(estimate_lines) + "\n", encoding="ascii", errors="ignore")

    def _append_mcmc_lines(self, lines, config, include_stones=True) -> None:
        seed = int(getattr(config, "random_seed", 0) or 0)
        if seed > 0:
            lines.append("Seed %s" % seed)
        lines.append("Sample %s" % int(config.sample_frequency))
        lines.append("Iterations %s" % int(config.iterations))
        lines.append("BurnIn %s" % int(config.burnin))
        optional_commands = [config.hyper_prior_all, config.revjump_hp, config.restrict_all]
        if include_stones:
            optional_commands.append(config.stones)
        for optional in optional_commands:
            if str(optional or "").strip():
                lines.append(str(optional).strip())

    def _append_extra_command_lines(self, lines, config) -> None:
        for line in str(config.extra_commands or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
            clean = line.strip()
            if clean:
                lines.append(clean)

    def _validate_continuous_asr_trait_rows(self, trait_rows) -> None:
        missing = []
        for taxon_id, values in list(trait_rows or []):
            value = values[0] if isinstance(values, (list, tuple)) and values else values
            if self._is_missing(value):
                missing.append(str(taxon_id))
        if missing:
            raise ValueError(
                "Continuous ASR visualization currently requires a numeric value for every tip. Missing: %s"
                % ", ".join(missing[:20])
            )

    def _continuous_tip_values(self, *, trait_rows, taxon_names, taxon_id_map):
        id_to_name = {str(taxon_id): str(name) for name, taxon_id in dict(taxon_id_map or {}).items()}
        values = {}
        for taxon_id, row_values in list(trait_rows or []):
            raw = row_values[0] if isinstance(row_values, (list, tuple)) and row_values else row_values
            if self._is_missing(raw):
                continue
            try:
                value = float(raw)
            except Exception:
                continue
            name = id_to_name.get(str(taxon_id), str(taxon_id))
            values[str(name)] = value
        return values

    def _normalize_fossil_state(self, value, state_display_labels):
        text = self._normalize_raw_trait_value(value)
        if not text:
            return ""
        reverse = {str(v): str(k) for k, v in dict(state_display_labels or {}).items()}
        if text in reverse:
            return reverse[text]
        return self._normalize_legacy_state_text(text)

    def _write_manifest(self, run_files: BayesTraitsRunFiles) -> None:
        payload = {
            "taxon_names": list(run_files.taxon_names),
            "taxon_ids": list(run_files.taxon_ids),
            "taxon_count": int(run_files.taxon_count),
            "node_records": list(run_files.node_records),
            "selected_node_ids": list(run_files.selected_node_ids),
            "state_symbols": list(run_files.state_symbols),
            "state_display_labels": dict(run_files.state_display_labels or {}),
            "numeric_reference_tree_text": str(run_files.numeric_reference_tree_text),
            "tree_count": int(run_files.tree_count),
            "config": run_files.config.to_preset_dict(),
            "engine": {
                "target": "BayesTraits V5",
            },
            "runtime": dict(run_files.extra_metadata or {}),
        }
        run_files.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _remove_stale_outputs(self, workdir: Path) -> None:
        patterns = [
            "trait.trees",
            "trait.dat",
            "trait.ini",
            "trait_save_models.ini",
            "trait_estimate_nodes.ini",
            "RASP_continuous_models.bin",
            "trait.dat*.txt",
            "model_build_trait.dat*.txt",
            "trait.dat*.Schedule.txt",
            "bayestraits_stdout.log",
            "bayestraits_stdout_stage1.log",
            "bayestraits_stdout_stage2.log",
            "bayestraits_stderr.log",
            "bayestraits_stderr_stage1.log",
            "bayestraits_stderr_stage2.log",
            "analysis_result.log",
            "bayestraits_manifest.json",
        ]
        for pattern in patterns:
            for path in workdir.glob(pattern):
                try:
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass

    def _node_to_translated_newick(self, node, label_map, is_root=False) -> str:
        if self._is_leaf(node):
            name = str(getattr(node, "name", "") or "").strip()
            label = str(label_map.get(name, name))
            return "%s:%s" % (self._safe_label(label), self._format_float(self._node_dist(node)))

        children = list(getattr(node, "children", []) or [])
        child_text = ",".join(self._node_to_translated_newick(child, label_map, is_root=False) for child in children)
        if is_root:
            return "(%s)" % child_text
        return "(%s):%s" % (child_text, self._format_float(self._node_dist(node)))

    def _leaf_names(self, tree) -> List[str]:
        try:
            return [str(x).strip() for x in tree.get_leaf_names()]
        except Exception:
            return [str(getattr(leaf, "name", "") or "").strip() for leaf in self._iter_leaves(tree)]

    def _iter_leaves(self, node):
        if hasattr(node, "iter_leaves"):
            return node.iter_leaves()
        if self._is_leaf(node):
            return [node]
        leaves = []
        for child in list(getattr(node, "children", []) or []):
            leaves.extend(list(self._iter_leaves(child)))
        return leaves

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

    def _terminal_span(self, leaf_ids) -> str:
        values = [str(x) for x in list(leaf_ids or []) if str(x)]
        if not values:
            return ""
        ordered = sorted(values, key=self._display_sort_key)
        return "%s-%s" % (ordered[0], ordered[-1])

    def _node_support_percent(self, node) -> float:
        text = str(getattr(node, "name", "") or "").strip()
        if not text:
            return 100.0
        try:
            value = float(text)
        except Exception:
            return 100.0
        if value <= 1.0:
            return value * 100.0
        return value

    def _normalize_raw_trait_value(self, value) -> str:
        return str(value or "").strip()

    def _normalize_legacy_state_text(self, value) -> str:
        text = str(value or "").strip().upper()
        text = re.sub(r"[\s,;/|+]+", "", text)
        if not text:
            return "-"
        if self._has_unsafe_label_chars(text):
            raise ValueError("BayesTraits state contains unsupported characters: %s" % value)
        return text

    def _looks_like_continuous_numeric(self, values) -> bool:
        cleaned = [str(value or "").strip() for value in list(values or []) if str(value or "").strip()]
        if not cleaned:
            return False
        numeric_count = 0
        decimal_count = 0
        for value in cleaned:
            if self._is_decimal_number(value):
                numeric_count += 1
                if "." in value or "e" in value.lower():
                    decimal_count += 1
        return numeric_count == len(cleaned) and decimal_count > 0

    def _is_decimal_number(self, value) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        try:
            float(text)
        except Exception:
            return False
        return bool(re.match(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$", text))

    def _state_symbols_from_value(self, value):
        text = str(value or "").strip()
        if self._is_missing(text):
            return []
        return [ch for ch in text]

    def _is_missing(self, value) -> bool:
        return str(value or "").strip().upper() in self.MISSING_TOKENS

    def _has_unsafe_label_chars(self, text) -> bool:
        value = str(text or "")
        return bool(re.search(r"[\s\t\r\n,;:=()\[\]']", value))

    def _safe_label(self, label) -> str:
        text = str(label or "").strip()
        if not text:
            return ""
        return text

    def _format_float(self, value) -> str:
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return "%.12g" % number

    def _display_sort_key(self, value):
        text = str(value or "").strip()
        try:
            return (0, int(text))
        except Exception:
            return (1, text)

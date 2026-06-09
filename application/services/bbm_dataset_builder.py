import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from application.services.dec_dataset_builder import DECDatasetBuilder
from domain.models.bbm_config import (
    BBM_RATE_VARIATION_MODELS,
    BBM_ROOT_DISTRIBUTIONS,
    BBM_STATE_FREQUENCY_MODELS,
    BBMConfig,
)


@dataclass
class BBMRunFiles:
    workdir: Path
    nexus_path: Path
    manifest_path: Path
    stdout_log_path: Path
    stderr_log_path: Path
    clade_log_path: Path
    analysis_log_path: Path

    area_names: List[str]
    taxon_names: List[str]
    taxon_ids: List[str]
    taxon_count: int
    node_records: List[Dict[str, object]]
    selected_node_ids: List[str]
    numeric_tree_text: str
    config: BBMConfig

    run1_p_path: Optional[Path] = None
    run2_p_path: Optional[Path] = None
    mcmc_path: Optional[Path] = None
    extra_metadata: Dict[str, object] = field(default_factory=dict)


class BBMDatasetBuilder:
    def __init__(self):
        self._dec_builder = DECDatasetBuilder()

    def build(self, *, tree, matrix, config: BBMConfig, output_dir, run_name="bbm_run") -> BBMRunFiles:
        config.validate()
        workdir = Path(output_dir) / run_name
        workdir.mkdir(parents=True, exist_ok=True)

        area_names, rows = self._dec_builder._collect_area_names_and_rows(matrix)
        self._dec_builder._validate_tree_and_matrix(tree, rows)
        if list(area_names) != list(config.area_names):
            raise ValueError(
                "BBM config areas (%s) do not match matrix areas (%s)."
                % (", ".join(config.area_names), ", ".join(area_names))
            )

        taxon_names = [taxon for taxon, _bits in rows]
        taxon_id_map = self._collect_taxon_ids(matrix, taxon_names)
        node_records = self.build_node_records(tree, taxon_id_map)

        valid_node_ids = {str(item["display_node_id"]) for item in node_records}
        selected_node_ids = [str(x).strip() for x in list(config.selected_node_ids or []) if str(x).strip()]
        selected_node_ids = [node_id for node_id in selected_node_ids if node_id in valid_node_ids]
        if not selected_node_ids:
            raise ValueError("Select one node at least.")

        nexus_path = workdir / "clade1.nex"
        manifest_path = workdir / "bbm_manifest.json"
        stdout_log_path = workdir / "mrbayes_stdout.log"
        stderr_log_path = workdir / "mrbayes_stderr.log"
        clade_log_path = workdir / "clade_b.log"
        analysis_log_path = workdir / "analysis_result.log"

        self._remove_stale_outputs(workdir)
        numeric_tree_text = self._node_to_numeric_newick(tree, taxon_id_map, is_root=True) + ";"
        self._write_nexus(
            path=nexus_path,
            rows=rows,
            area_names=area_names,
            taxon_id_map=taxon_id_map,
            node_records=node_records,
            selected_node_ids=selected_node_ids,
            config=config,
        )

        run_files = BBMRunFiles(
            workdir=workdir,
            nexus_path=nexus_path,
            manifest_path=manifest_path,
            stdout_log_path=stdout_log_path,
            stderr_log_path=stderr_log_path,
            clade_log_path=clade_log_path,
            analysis_log_path=analysis_log_path,
            area_names=list(area_names),
            taxon_names=taxon_names,
            taxon_ids=[taxon_id_map[name] for name in taxon_names],
            taxon_count=len(taxon_names),
            node_records=node_records,
            selected_node_ids=selected_node_ids,
            numeric_tree_text=numeric_tree_text,
            config=config,
            extra_metadata={
                "taxon_id_map": dict(taxon_id_map),
            },
        )
        self._write_manifest(run_files)
        return run_files

    def build_node_records(self, tree, taxon_id_map: Dict[str, str]) -> List[Dict[str, object]]:
        try:
            taxon_count = len(tree.get_leaf_names())
        except Exception:
            taxon_count = len(taxon_id_map)

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
            label_ids = ["TID%s" % taxon_id for taxon_id in leaf_ids]
            display_id = str(taxon_count + counter)
            records.append({
                "display_node_id": display_id,
                "node_index": counter,
                "clade_key": "|".join(sorted(leaf_names)),
                "leaf_names": leaf_names,
                "leaf_ids": leaf_ids,
                "constraint_taxa": label_ids,
                "terminal_span": self._terminal_span(leaf_ids),
                "support": self._node_support_percent(node),
            })
        return records

    def _collect_taxon_ids(self, matrix, taxon_names: List[str]) -> Dict[str, str]:
        name_to_id = {}
        seen_ids = set()
        for row in list(getattr(matrix, "rows", []) or []):
            name = str(row.get("Name", "") or "").strip()
            row_id = str(row.get("ID", "") or "").strip()
            if not name:
                continue
            if not row_id:
                raise ValueError("BBM requires a non-empty ID for taxon '%s'." % name)
            if row_id in seen_ids:
                raise ValueError("BBM taxon ID '%s' is duplicated." % row_id)
            seen_ids.add(row_id)
            name_to_id[name] = row_id

        missing = [name for name in taxon_names if name not in name_to_id]
        if missing:
            raise ValueError("BBM could not find matrix IDs for taxa: %s." % ", ".join(sorted(missing)))
        return {name: name_to_id[name] for name in taxon_names}

    def _remove_stale_outputs(self, workdir: Path) -> None:
        for pattern in [
            "clade1.nex*",
            "bbm_manifest.json",
            "mrbayes_stdout.log",
            "mrbayes_stderr.log",
            "clade_b.log",
            "analysis_result.log",
        ]:
            for path in workdir.glob(pattern):
                try:
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass

    def _write_nexus(
        self,
        *,
        path: Path,
        rows,
        area_names,
        taxon_id_map,
        node_records,
        selected_node_ids,
        config: BBMConfig,
    ) -> None:
        selected = [record for record in node_records if str(record["display_node_id"]) in selected_node_ids]
        ntax = len(rows) + 2 + (1 if bool(config.large_dataset_mode) else 0)
        root_bits = self._root_distribution_bits(config, area_names)

        lines = [
            "#NEXUS",
            "Begin data;",
            "Dimensions ntax=%s nchar=%s;" % (ntax, len(area_names)),
            "Format datatype=restriction;",
            "Matrix",
        ]
        for taxon, bits in rows:
            taxon_id = taxon_id_map[taxon]
            lines.append("TID%s    %s" % (taxon_id, bits))

        if bool(config.large_dataset_mode):
            lines.append("OG0    %s" % root_bits)
        lines.append("OG1    %s" % root_bits)
        lines.append("OG2    %s" % root_bits)
        lines.extend([";", "End;", "begin mrbayes;"])

        lines.extend(self._mrbayes_commands(config, selected, len(rows)))
        lines.append("[burnin=%s,taxonnum=%s,node_num=%s]" % (
            int(config.discard_samples),
            len(area_names),
            len(node_records),
        ))
        lines.append("End;")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _mrbayes_commands(self, config: BBMConfig, selected_records, taxon_count: int) -> List[str]:
        commands = ["outgroup %s;" % (taxon_count + 2)]

        if config.state_frequency_model == "JC":
            commands.append("lset nst=1 rates=equal;")
        else:
            commands.append("lset nst=1 rates=equal;")
            commands.append(
                "prset statefreqpr=dirichlet(%s,%s);"
                % (self._format_float(config.dirichlet_alpha), self._format_float(config.dirichlet_beta))
            )

        if config.rate_variation_model == "GAMMA":
            commands.append("lset nst=1 rates=gamma;")
            commands.append(
                "prset Shapepr=Uniform(%s,%s);"
                % (self._format_float(config.gamma_min), self._format_float(config.gamma_max))
            )

        constraint_names = []
        for record in selected_records:
            name = "c%s" % record["node_index"]
            constraint_names.append(name)
            commands.append(
                "constraint %s -1 = %s;"
                % (name, " ".join(str(x) for x in record.get("constraint_taxa", [])))
            )
        if constraint_names:
            commands.append("prset topologypr=constraints(%s);" % ",".join(constraint_names))

        commands.extend([
            "lset coding=variable;",
            "set autoclose=yes nowarn=yes;",
            "report ancstates=yes;",
            (
                "mcmc printfreq=1000 diagnfreq=1000 Ordertaxa=Yes "
                "Samplefreq=%s ngen=%s nchains=%s Temp=%s;"
            ) % (
                int(config.sample_frequency),
                int(config.chain_length),
                int(config.chains),
                self._format_float(config.temperature),
            ),
        ])
        return commands

    def _root_distribution_bits(self, config: BBMConfig, area_names) -> str:
        mode = str(config.root_distribution or "NULL").upper()
        if mode == "WIDE":
            return "1" * len(area_names)
        if mode == "CUSTOM":
            custom = str(config.custom_root_distribution or "").upper()
            return "".join("1" if area in custom else "0" for area in area_names)
        return "0" * len(area_names)

    def _write_manifest(self, run_files: BBMRunFiles) -> None:
        payload = {
            "area_names": list(run_files.area_names),
            "taxon_names": list(run_files.taxon_names),
            "taxon_ids": list(run_files.taxon_ids),
            "taxon_count": int(run_files.taxon_count),
            "selected_node_ids": list(run_files.selected_node_ids),
            "node_records": list(run_files.node_records),
            "numeric_tree_text": str(run_files.numeric_tree_text),
            "config": run_files.config.to_preset_dict(),
            "runtime": dict(run_files.extra_metadata or {}),
        }
        run_files.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _node_to_numeric_newick(self, node, taxon_id_map, is_root=False) -> str:
        if self._is_leaf(node):
            name = str(getattr(node, "name", "") or "").strip()
            label = str(taxon_id_map.get(name, name))
            return "%s:%s" % (self._safe_newick_label(label), self._format_float(self._node_dist(node)))

        children = list(getattr(node, "children", []) or [])
        child_text = ",".join(self._node_to_numeric_newick(child, taxon_id_map, is_root=False) for child in children)
        if is_root:
            return "(%s)" % child_text
        return "(%s):%s" % (child_text, self._format_float(self._node_dist(node)))

    def _terminal_span(self, leaf_ids) -> str:
        values = [str(x) for x in list(leaf_ids or []) if str(x)]
        if not values:
            return ""
        ordered = sorted(values, key=self._display_sort_key)
        return "%s-%s" % (ordered[0], ordered[-1])

    def _display_sort_key(self, value):
        text = str(value or "").strip()
        try:
            return (0, int(text))
        except Exception:
            return (1, text)

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

    def describe_model(self, config: BBMConfig) -> str:
        base = BBM_STATE_FREQUENCY_MODELS.get(config.state_frequency_model, config.state_frequency_model)
        rates = BBM_RATE_VARIATION_MODELS.get(config.rate_variation_model, config.rate_variation_model)
        root = BBM_ROOT_DISTRIBUTIONS.get(config.root_distribution, config.root_distribution)
        return "%s / %s / root=%s" % (base, rates, root)

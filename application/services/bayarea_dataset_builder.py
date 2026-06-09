import json
import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from application.services.dec_dataset_builder import DECDatasetBuilder


@dataclass
class BayAreaRunFiles:
    workdir: Path
    areas_path: Path
    geo_path: Path
    tree_path: Path
    manifest_path: Path
    stdout_log_path: Path
    stderr_log_path: Path

    area_names: List[str]
    taxon_names: List[str]
    taxon_ids: List[str]
    taxon_count: int
    node_index_to_clade: Dict[int, str]
    clade_to_reference_node_id: Dict[str, str]
    burnin: int
    sample_frequency: int
    chain_length: int
    output_prefix: str = "bayarea"

    parameters_path: Optional[Path] = None
    area_states_path: Optional[Path] = None
    area_probs_path: Optional[Path] = None
    nhx_path: Optional[Path] = None
    analysis_log_path: Optional[Path] = None
    config: object = None
    extra_metadata: Dict[str, object] = field(default_factory=dict)


class BayAreaDatasetBuilder:
    def __init__(self):
        self._dec_builder = DECDatasetBuilder()

    def build(
        self,
        *,
        tree,
        matrix,
        config,
        output_dir,
        run_name: str = "bayarea_run",
    ) -> BayAreaRunFiles:
        config.validate()
        workdir = Path(output_dir) / run_name
        workdir.mkdir(parents=True, exist_ok=True)

        area_names, rows = self._dec_builder._collect_area_names_and_rows(matrix)
        self._dec_builder._validate_tree_and_matrix(tree, rows)
        if list(area_names) != list(config.area_names):
            raise ValueError(
                "BayArea config areas (%s) do not match matrix areas (%s)."
                % (", ".join(config.area_names), ", ".join(area_names))
            )

        areas_path = workdir / "bayarea.areas.txt"
        geo_path = workdir / "bayarea.geo.txt"
        tree_path = workdir / "bayarea.tree.txt"
        manifest_path = workdir / "bayarea_manifest.json"
        stdout_log_path = workdir / "bayarea_stdout.log"
        stderr_log_path = workdir / "bayarea_stderr.log"

        self._remove_stale_outputs(workdir)
        taxon_names = [taxon for taxon, _bits in rows]
        taxon_id_map = self._collect_taxon_ids(matrix, taxon_names)

        self._write_areas(rows, area_names, areas_path, taxon_id_map)
        self._write_geo(area_names, config.coordinates, geo_path)
        self._write_bayarea_tree(tree, tree_path, taxon_id_map)

        node_index_to_clade = self._build_bayarea_node_index_map(tree, len(taxon_names))
        clade_to_reference_node_id = self._build_reference_node_id_map(tree)

        run_files = BayAreaRunFiles(
            workdir=workdir,
            areas_path=areas_path,
            geo_path=geo_path,
            tree_path=tree_path,
            manifest_path=manifest_path,
            stdout_log_path=stdout_log_path,
            stderr_log_path=stderr_log_path,
            area_names=list(area_names),
            taxon_names=taxon_names,
            taxon_ids=[taxon_id_map[name] for name in taxon_names],
            taxon_count=len(taxon_names),
            node_index_to_clade=node_index_to_clade,
            clade_to_reference_node_id=clade_to_reference_node_id,
            burnin=int(config.burnin),
            sample_frequency=int(config.sample_frequency),
            chain_length=int(config.chain_length),
            config=config,
            extra_metadata={
                **config.engine_kwargs(),
                "taxon_id_map": dict(taxon_id_map),
            },
        )
        self._write_manifest(run_files)
        return run_files

    def _remove_stale_outputs(self, workdir: Path) -> None:
        for pattern in [
            "*.parameters.txt",
            "*.area_states.txt",
            "*.area_probs.txt",
            "*.nhx",
            "bayarea_stdout.log",
            "bayarea_stderr.log",
            "bayarea_manifest.json",
        ]:
            for path in workdir.glob(pattern):
                try:
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass

    def _collect_taxon_ids(self, matrix, taxon_names: List[str]) -> Dict[str, str]:
        name_to_id = {}
        seen_ids = set()
        for row in list(getattr(matrix, "rows", []) or []):
            name = str(row.get("Name", "") or "").strip()
            row_id = str(row.get("ID", "") or "").strip()
            if not name:
                continue
            if not row_id:
                raise ValueError("BayArea requires a non-empty ID for taxon '%s'." % name)
            if not row_id.isdigit():
                raise ValueError(
                    "BayArea follows legacy RASP input and requires numeric taxon IDs; "
                    "taxon '%s' has ID '%s'." % (name, row_id)
                )
            if row_id in seen_ids:
                raise ValueError("BayArea taxon ID '%s' is duplicated." % row_id)
            seen_ids.add(row_id)
            name_to_id[name] = row_id

        missing = [name for name in taxon_names if name not in name_to_id]
        if missing:
            raise ValueError(
                "BayArea could not find matrix IDs for taxa: %s."
                % ", ".join(sorted(missing))
            )
        return {name: name_to_id[name] for name in taxon_names}

    def _write_areas(self, rows, area_names, path: Path, taxon_id_map: Dict[str, str]) -> None:
        lines = ["%s %s" % (len(rows), len(area_names))]
        for taxon, bits in rows:
            lines.append("%s\t%s" % (taxon_id_map[taxon], bits))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_geo(self, area_names, coordinates, path: Path) -> None:
        lines = ["# 0.0"]
        for area in area_names:
            lat, lon = coordinates.get(area, (0.0, 0.0))
            lat = float(lat)
            lon = float(lon)
            lines.append("%s %s" % (self._format_float(lat), self._format_float(lon)))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_bayarea_tree(self, tree, path: Path, taxon_id_map: Dict[str, str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tree_for_engine = self._copy_tree(tree)
        for leaf in self._iter_leaves(tree_for_engine):
            name = str(getattr(leaf, "name", "") or "").strip()
            leaf.name = taxon_id_map.get(name, name)
        newick = self._node_to_newick(tree_for_engine, is_root=True)
        path.write_text(newick + ";\n", encoding="utf-8")

    def _copy_tree(self, tree):
        try:
            return tree.copy(method="deepcopy")
        except Exception:
            return copy.deepcopy(tree)

    def _node_to_newick(self, node, is_root=False) -> str:
        if self._is_leaf(node):
            label = self._safe_newick_label(str(getattr(node, "name", "") or "").strip())
            return "%s:%s" % (label, self._format_float(self._node_dist(node)))

        children = list(getattr(node, "children", []) or [])
        child_text = ",".join(self._node_to_newick(child, is_root=False) for child in children)
        if is_root:
            root_dist = self._node_dist(node)
            if root_dist == 0.0:
                root_dist = self._legacy_root_stub_length(node)
            if root_dist != 0.0:
                return "(%s):%s" % (child_text, self._format_float(root_dist))
            return "(%s)" % child_text
        return "(%s):%s" % (child_text, self._format_float(self._node_dist(node)))

    def _legacy_root_stub_length(self, root) -> float:
        root_time = self._max_root_to_tip_length(root)
        if root_time <= 0.0:
            return 0.0
        return float(int(root_time * 2.0))

    def _max_root_to_tip_length(self, root) -> float:
        def walk(node, current):
            children = list(getattr(node, "children", []) or [])
            if not children:
                return float(current)
            values = []
            for child in children:
                values.append(walk(child, float(current) + self._node_dist(child)))
            return max(values) if values else float(current)

        return walk(root, 0.0)

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

    def _build_bayarea_node_index_map(self, tree, taxon_count: int) -> Dict[int, str]:
        mapping = {}
        counter = [int(taxon_count)]

        def visit(node):
            if self._is_leaf(node):
                return
            node_index = counter[0]
            counter[0] += 1
            mapping[node_index] = self._clade_key(node)
            for child in list(getattr(node, "children", []) or []):
                visit(child)

        visit(tree)
        return mapping

    def _build_reference_node_id_map(self, tree) -> Dict[str, str]:
        mapping = {}
        if tree is None or not hasattr(tree, "traverse"):
            return mapping
        try:
            taxon_count = len(tree.get_leaf_names())
        except Exception:
            taxon_count = 0

        counter = 0
        for node in tree.traverse("postorder"):
            if self._is_leaf(node):
                continue
            counter += 1
            mapping[self._clade_key(node)] = str(taxon_count + counter)
        return mapping

    def _clade_key(self, node) -> str:
        try:
            return "|".join(sorted(node.get_leaf_names()))
        except Exception:
            names = []
            for leaf in self._iter_leaves(node):
                name = str(getattr(leaf, "name", "") or "").strip()
                if name:
                    names.append(name)
            return "|".join(sorted(names))

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

    def _write_manifest(self, run_files: BayAreaRunFiles) -> None:
        payload = {
            "area_names": list(run_files.area_names),
            "taxon_names": list(run_files.taxon_names),
            "taxon_ids": list(run_files.taxon_ids),
            "taxon_count": int(run_files.taxon_count),
            "burnin": int(run_files.burnin),
            "sample_frequency": int(run_files.sample_frequency),
            "chain_length": int(run_files.chain_length),
            "output_prefix": str(run_files.output_prefix),
            "node_index_to_clade": {
                str(key): value
                for key, value in dict(run_files.node_index_to_clade).items()
            },
            "runtime": dict(run_files.extra_metadata or {}),
        }
        run_files.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _format_float(self, value) -> str:
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return "%.12g" % number

import json
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from application.services.dec_dataset_builder import DECDatasetBuilder
from domain.models.sbgb_config import normalize_sbgb_null_range_mode


@dataclass
class BioGeoBEARSRunFiles:
    workdir: Path
    tree_path: Path
    geog_path: Path
    areas_json_path: Path
    output_json_path: Path
    stdout_log_path: Path
    stderr_log_path: Path

    area_names: List[str]
    max_range_size: int
    taxon_count: int
    model_name: str
    include_null_range: bool
    null_range_mode: str
    cores: int
    include_ranges: List[str]
    exclude_ranges: List[str]
    time_matrix_kind: str
    period_times: List[float]
    period_matrix_path: Optional[Path]
    timeperiods_path: Optional[Path]
    scale_tree_to_root_age: bool = False
    root_age: Optional[float] = None
    tree_scale_factor: Optional[float] = None


class BioGeoBEARSDatasetBuilder:
    """
    第一版复用 DEC builder 的矩阵解析逻辑，但输出 BioGeoBEARS 运行所需文件：
    - input_tree.nwk
    - geog.data
    - areas.json
    """

    def __init__(self):
        self._dec_builder = DECDatasetBuilder()

    def build(
        self,
        *,
        tree,
        matrix,
        output_dir,
        run_name,
        model_name,
        max_range_size,
        include_null_range,
        null_range_mode,
        cores,
        include_ranges,
        exclude_ranges,
        period_times,
        time_matrix_kind,
        period_matrices,
        root_age,
        scale_tree_to_root_age=False,
    ) -> BioGeoBEARSRunFiles:
        workdir = Path(output_dir) / run_name
        workdir.mkdir(parents=True, exist_ok=True)

        area_names, rows = self._dec_builder._collect_area_names_and_rows(matrix)
        self._dec_builder._validate_tree_and_matrix(tree, rows)

        area_count = len(area_names)
        min_range_size = max([1] + [str(bits).count("1") for _taxon, bits in rows])
        if max_range_size is None:
            chosen_max = min(max(4, min_range_size), area_count)
        else:
            chosen_max = max(min_range_size, min(int(max_range_size), area_count))
        effective_null_range_mode = normalize_sbgb_null_range_mode(
            null_range_mode,
            include_null_range,
        )
        effective_include_null_range = effective_null_range_mode == "include"

        tree_path = workdir / "input_tree.nwk"
        geog_path = workdir / "geog.data"
        areas_json_path = workdir / "areas.json"
        output_json_path = workdir / "bgb_result.json"
        stdout_log_path = workdir / "bgb_stdout.log"
        stderr_log_path = workdir / "bgb_stderr.log"
        normalized_period_times = self._normalize_period_times(period_times)
        normalized_period_matrices = self._normalize_period_matrices(
            period_matrices,
            len(area_names),
            normalized_period_times,
        )
        normalized_time_kind = self._normalize_time_matrix_kind(time_matrix_kind)
        normalized_root_age = self._normalize_root_age(root_age)
        timeperiods_path, period_matrix_path = self._write_time_stratified_files(
            workdir=workdir,
            area_names=area_names,
            period_times=normalized_period_times,
            period_matrices=normalized_period_matrices,
            time_matrix_kind=normalized_time_kind,
        )

        written_tree, tree_scale_factor = self._prepare_tree_for_bgb(
            tree,
            root_age=normalized_root_age,
            scale_tree_to_root_age=scale_tree_to_root_age,
        )
        self._dec_builder._write_tree(written_tree, tree_path)
        self._write_geog_data(rows, area_names, geog_path)
        self._write_areas_json(
            areas_json_path=areas_json_path,
            area_names=area_names,
            model_name=model_name,
            max_range_size=chosen_max,
            include_null_range=effective_include_null_range,
            null_range_mode=effective_null_range_mode,
            cores=cores,
            include_ranges=include_ranges,
            exclude_ranges=exclude_ranges,
            period_times=normalized_period_times,
            time_matrix_kind=normalized_time_kind,
            timeperiods_path=timeperiods_path,
            period_matrix_path=period_matrix_path,
            root_age=normalized_root_age,
            scale_tree_to_root_age=bool(scale_tree_to_root_age and normalized_root_age),
            tree_scale_factor=tree_scale_factor,
        )

        return BioGeoBEARSRunFiles(
            workdir=workdir,
            tree_path=tree_path,
            geog_path=geog_path,
            areas_json_path=areas_json_path,
            output_json_path=output_json_path,
            stdout_log_path=stdout_log_path,
            stderr_log_path=stderr_log_path,
            area_names=area_names,
            max_range_size=chosen_max,
            taxon_count=len(rows),
            model_name=str(model_name).upper(),
            include_null_range=effective_include_null_range,
            null_range_mode=effective_null_range_mode,
            cores=max(1, int(cores or 1)),
            include_ranges=self._normalize_ranges(include_ranges),
            exclude_ranges=self._normalize_ranges(exclude_ranges),
            time_matrix_kind=normalized_time_kind,
            period_times=normalized_period_times,
            period_matrix_path=period_matrix_path,
            timeperiods_path=timeperiods_path,
            scale_tree_to_root_age=bool(scale_tree_to_root_age and normalized_root_age),
            root_age=normalized_root_age,
            tree_scale_factor=tree_scale_factor,
        )

    def _write_geog_data(self, rows, area_names, geog_path: Path) -> None:
        lines = [f"{len(rows)} {len(area_names)}"]
        for taxon, bits in rows:
            lines.append(f"{taxon}\t{bits}")
        geog_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_areas_json(
        self,
        *,
        areas_json_path: Path,
        area_names,
        model_name,
        max_range_size,
        include_null_range,
        null_range_mode,
        cores,
        include_ranges,
        exclude_ranges,
        period_times,
        time_matrix_kind,
        timeperiods_path,
        period_matrix_path,
        root_age,
        scale_tree_to_root_age,
        tree_scale_factor,
    ) -> None:
        payload = {
            "area_names": list(area_names),
            "model_name": str(model_name).upper(),
            "max_range_size": int(max_range_size),
            "include_null_range": bool(include_null_range),
            "null_range_mode": str(null_range_mode or ("include" if include_null_range else "exclude")),
            "cores": max(1, int(cores or 1)),
            "include_ranges": self._normalize_ranges(include_ranges),
            "exclude_ranges": self._normalize_ranges(exclude_ranges),
            "period_times": [float(x) for x in list(period_times or [])],
            "time_matrix_kind": str(time_matrix_kind or "dispersal_multipliers"),
            "timeperiods_filename": timeperiods_path.name if timeperiods_path else None,
            "root_age": float(root_age) if root_age is not None else None,
            "scale_tree_to_root_age": bool(scale_tree_to_root_age),
            "tree_scale_factor": float(tree_scale_factor) if tree_scale_factor is not None else None,
        }
        if period_matrix_path is not None:
            payload[self._matrix_filename_json_key(time_matrix_kind)] = period_matrix_path.name
        areas_json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _normalize_root_age(self, root_age) -> Optional[float]:
        try:
            value = float(str(root_age).strip())
        except Exception:
            return None
        if value <= 0:
            return None
        return value

    def _prepare_tree_for_bgb(self, tree, *, root_age, scale_tree_to_root_age):
        if not scale_tree_to_root_age or root_age is None:
            return tree, None

        tree_copy = self._copy_tree(tree)
        current_height = self._normalize_min_branch_lengths_and_get_height(tree_copy)
        if current_height <= 0:
            return tree_copy, None

        factor = float(root_age) / float(current_height)
        for node in self._iter_nodes(tree_copy):
            if self._is_root_node(node, tree_copy):
                continue
            node.dist = float(getattr(node, "dist", 0.0) or 0.0) * factor
        return tree_copy, factor

    def _copy_tree(self, tree):
        if hasattr(tree, "copy"):
            try:
                return tree.copy(method="deepcopy")
            except TypeError:
                try:
                    return tree.copy()
                except Exception:
                    pass
        return copy.deepcopy(tree)

    def _normalize_min_branch_lengths_and_get_height(self, tree) -> float:
        max_height = 0.0

        def visit(node, depth):
            nonlocal max_height
            if not self._is_root_node(node, tree):
                dist = float(getattr(node, "dist", 0.0) or 0.0)
                if dist < 0.0001:
                    dist = 0.0001
                    node.dist = dist
                depth += dist
            children = list(getattr(node, "children", []) or [])
            if not children:
                max_height = max(max_height, depth)
                return
            for child in children:
                visit(child, depth)

        visit(tree, 0.0)
        return max_height

    def _iter_nodes(self, tree):
        if hasattr(tree, "traverse"):
            return tree.traverse()

        def walk(node):
            yield node
            for child in list(getattr(node, "children", []) or []):
                yield from walk(child)

        return walk(tree)

    def _is_root_node(self, node, tree) -> bool:
        if node is tree:
            return True
        try:
            return bool(node.is_root())
        except Exception:
            return False

    def _normalize_ranges(self, ranges) -> List[str]:
        seen = set()
        out = []
        for value in list(ranges or []):
            text = str(value).strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out

    def _normalize_period_times(self, period_times) -> List[float]:
        values = []
        for value in list(period_times or []):
            try:
                values.append(float(value))
            except Exception:
                continue
        if not values:
            values = [0.0]
        values = sorted(set(values))
        if values[0] != 0.0:
            values.insert(0, 0.0)
        return values

    def _normalize_period_matrices(
        self,
        matrices,
        size: int,
        period_times: Sequence[float],
    ) -> List[List[List[float]]]:
        raw = list(matrices or [])
        period_count = max(1, len(period_times) - 1, len(raw))
        normalized = []
        for index in range(period_count):
            matrix = raw[index] if index < len(raw) else None
            normalized.append(self._normalize_one_matrix(matrix, size))
        return normalized

    def _normalize_one_matrix(self, matrix, size: int) -> List[List[float]]:
        normalized = [[1.0 for _ in range(size)] for _ in range(size)]
        for row in range(size):
            for col in range(size):
                if row < len(matrix or []) and col < len(matrix[row] or []):
                    try:
                        normalized[row][col] = float(matrix[row][col])
                    except Exception:
                        normalized[row][col] = 1.0
        return normalized

    def _normalize_time_matrix_kind(self, value) -> str:
        text = str(value or "dispersal_multipliers").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "dispersal": "dispersal_multipliers",
            "dispersal_multipliers": "dispersal_multipliers",
            "areas_allowed": "areas_allowed",
            "areas_adjacency": "areas_adjacency",
            "adjacency": "areas_adjacency",
            "distances": "distances",
            "distance": "distances",
        }
        return aliases.get(text, "dispersal_multipliers")

    def _write_time_stratified_files(
        self,
        *,
        workdir: Path,
        area_names: Sequence[str],
        period_times: Sequence[float],
        period_matrices: Sequence[Sequence[Sequence[float]]],
        time_matrix_kind: str,
    ):
        if not period_matrices:
            return None, None

        has_multiple_periods = len(period_matrices) > 1
        has_non_default = any(
            not self._is_default_matrix(matrix, len(area_names))
            for matrix in period_matrices
        )
        if not has_multiple_periods and not has_non_default:
            return None, None

        timeperiods_path = workdir / "timeperiods.txt"
        times_to_write = list(period_times[1:] if period_times and period_times[0] == 0.0 else period_times)
        timeperiods_path.write_text(
            "".join("%s\n" % self._format_float(value) for value in times_to_write),
            encoding="utf-8",
        )

        matrix_path = workdir / self._matrix_filename(time_matrix_kind)
        self._write_biogeobears_matrix_file(matrix_path, area_names, period_matrices)
        return timeperiods_path, matrix_path

    def _write_biogeobears_matrix_file(
        self,
        path: Path,
        area_names: Sequence[str],
        period_matrices: Sequence[Sequence[Sequence[float]]],
    ) -> None:
        lines = []
        for matrix in period_matrices:
            lines.append("\t".join(str(x) for x in area_names))
            n = len(area_names)
            for row in range(n):
                values = []
                for col in range(n):
                    value = 1.0
                    if row < len(matrix or []) and col < len(matrix[row] or []):
                        value = float(matrix[row][col])
                    values.append(self._format_float(value))
                lines.append("\t".join(values))
            lines.append("")
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _matrix_filename(self, time_matrix_kind: str) -> str:
        return {
            "dispersal_multipliers": "dispersal_multipliers.txt",
            "areas_allowed": "areas_allowed.txt",
            "areas_adjacency": "areas_adjacency.txt",
            "distances": "distances_matrix.txt",
        }.get(str(time_matrix_kind), "dispersal_multipliers.txt")

    def _matrix_filename_json_key(self, time_matrix_kind: str) -> str:
        return {
            "dispersal_multipliers": "dispersal_multipliers_filename",
            "areas_allowed": "areas_allowed_filename",
            "areas_adjacency": "areas_adjacency_filename",
            "distances": "distances_filename",
        }.get(str(time_matrix_kind), "dispersal_multipliers_filename")

    def _is_default_matrix(self, matrix, size: int) -> bool:
        for row in range(size):
            for col in range(size):
                value = 1.0
                if row < len(matrix or []) and col < len(matrix[row] or []):
                    value = float(matrix[row][col])
                if abs(value - 1.0) > 1e-12:
                    return False
        return True

    def _format_float(self, value) -> str:
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return "%g" % number

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple
import copy
import re


@dataclass
class DECRunFiles:
    workdir: Path
    tree_path: Path
    data_path: Path
    config_path: Path
    log_path: Path

    results_json_path: Path
    nodes_tree_path: Path
    states_tree_path: Path
    splits_tree_path: Path
    scaled_tree_path: Path
    clean_tree_path: Path

    area_names: List[str]
    max_areas: int
    taxon_count: int
    scale_tree_to_root_age: bool = False
    root_age: Optional[float] = None
    tree_scale_factor: Optional[float] = None


class DECDatasetBuilder:
    """
    负责把当前树 + 当前矩阵导出为 Lagrange-NG 的最小输入集：
    - input_tree.nwk
    - ranges.phy
    - run.conf

    支持两种矩阵输入：
    1. 多区域列的 0/1 presence/absence 矩阵
    2. 单状态编码矩阵，例如 A / B / AB / ABC
    """

    TRUE_SET = {"1", "true", "t", "yes", "y", "present"}
    FALSE_SET = {"0", "", "false", "f", "no", "n", "absent", "nan", "none", "-", "?"}

    def _remove_stale_outputs(self, paths: Sequence[Path]) -> None:
        for path in paths:
            try:
                if path.exists() and path.is_file():
                    path.unlink()
            except OSError:
                pass

    def build(
            self,
            *,
            tree,
            matrix,
            output_dir,
            run_name: str = "dec_run",
            max_areas: Optional[int] = None,
            workers: int = 1,
            threads_per_worker: int = 1,
            include_states: bool = True,
            include_splits: bool = False,
            output_type: str = "json",
            opt_method: str = "bobyqa",
            mode: str = "optimize",
            dispersion: Optional[float] = None,
            extinction: Optional[float] = None,
            expm_mode: Optional[str] = None,
            allow_ambiguous: Optional[bool] = True,
            lwr_threshold: Optional[float] = None,
            extra_control_lines: Optional[Sequence[str]] = None,
            period_times: Optional[Sequence[float]] = None,
            dispersal_matrices: Optional[Sequence[Sequence[Sequence[float]]]] = None,
            period_include_area_bits: Optional[object] = None,
            period_exclude_area_bits: Optional[object] = None,
            mrca_constraints: Optional[Sequence[object]] = None,
            root_age: Optional[float] = None,
            scale_tree_to_root_age: bool = False,
    ) -> DECRunFiles:
        workdir = Path(output_dir) / run_name
        workdir.mkdir(parents=True, exist_ok=True)

        tree_path = workdir / "input_tree.nwk"
        data_path = workdir / "ranges.phy"
        config_path = workdir / "run.conf"
        log_path = workdir / "lagrange.log"
        tree_base = tree_path.name
        self._remove_stale_outputs(
            [
                workdir / f"{tree_base}.results.json",
                workdir / f"{tree_base}.nodes.tre",
                workdir / f"{tree_base}.states.tre",
                workdir / f"{tree_base}.splits.tre",
                workdir / f"{tree_base}.scaled.tre",
                workdir / f"{tree_base}.clean.tre",
                log_path,
            ]
        )
        for old_period_matrix in workdir.glob("period_*_matrix.csv"):
            self._remove_stale_outputs([old_period_matrix])

        area_names, rows = self._collect_area_names_and_rows(matrix)
        self._validate_tree_and_matrix(tree, rows)

        chosen_max_areas = self._choose_max_areas(rows, max_areas)
        normalized_root_age = self._normalize_root_age(root_age)
        written_tree, tree_scale_factor = self._prepare_tree_for_dec(
            tree,
            root_age=normalized_root_age,
            scale_tree_to_root_age=scale_tree_to_root_age,
        )

        self._write_tree(written_tree, tree_path)
        self._write_phylip(rows, area_names, data_path)
        period_lines = self._write_period_matrix_files(
            workdir=workdir,
            area_names=area_names,
            period_times=period_times,
            dispersal_matrices=dispersal_matrices,
            period_include_area_bits=period_include_area_bits,
            period_exclude_area_bits=period_exclude_area_bits,
        )
        mrca_lines = self._build_mrca_constraint_lines(
            mrca_constraints=mrca_constraints,
            area_names=area_names,
        )
        self._write_config(
            config_path=config_path,
            tree_filename=tree_path.name,
            data_filename=data_path.name,
            log_filename=log_path.name,
            area_names=area_names,
            max_areas=chosen_max_areas,
            workers=workers,
            threads_per_worker=threads_per_worker,
            include_states=include_states,
            include_splits=include_splits,
            output_type=output_type,
            opt_method=opt_method,
            mode=mode,
            dispersion=dispersion,
            extinction=extinction,
            expm_mode=expm_mode,
            allow_ambiguous=allow_ambiguous,
            lwr_threshold=lwr_threshold,
            extra_control_lines=extra_control_lines,
            period_control_lines=period_lines,
            mrca_control_lines=mrca_lines,
        )

        return DECRunFiles(
            workdir=workdir,
            tree_path=tree_path,
            data_path=data_path,
            config_path=config_path,
            log_path=log_path,
            results_json_path=workdir / f"{tree_base}.results.json",
            nodes_tree_path=workdir / f"{tree_base}.nodes.tre",
            states_tree_path=workdir / f"{tree_base}.states.tre",
            splits_tree_path=workdir / f"{tree_base}.splits.tre",
            scaled_tree_path=workdir / f"{tree_base}.scaled.tre",
            clean_tree_path=workdir / f"{tree_base}.clean.tre",
            area_names=area_names,
            max_areas=chosen_max_areas,
            taxon_count=len(rows),
            scale_tree_to_root_age=bool(scale_tree_to_root_age and normalized_root_age),
            root_age=normalized_root_age,
            tree_scale_factor=tree_scale_factor,
        )

    def _collect_area_names_and_rows(self, matrix) -> Tuple[List[str], List[Tuple[str, str]]]:
        columns = list(getattr(matrix, "state_columns", []) or [])
        columns = [str(c).strip() for c in columns if str(c).strip() and c not in ("ID", "Name")]
        if not columns:
            raise ValueError("DEC 矩阵未找到可用状态列。要求至少包含 Name 列和 1 个状态列。")

        raw_rows = list(getattr(matrix, "rows", []) or [])
        if not raw_rows:
            raise ValueError("DEC 矩阵为空。")

        mode = self._detect_matrix_mode(raw_rows, columns)

        if mode == "binary":
            area_names = columns
            for name in area_names:
                if any(ch.isspace() for ch in name):
                    raise ValueError(f"区域名 '{name}' 含空格。第一版请先使用无空格区域名。")
            rows = self._collect_binary_rows(raw_rows, area_names)
            return area_names, rows

        rows, area_names = self._collect_encoded_rows(raw_rows, columns)
        return area_names, rows

    def _detect_matrix_mode(self, raw_rows, columns: Sequence[str]) -> str:
        """
        只要任意状态列出现非 0/1 风格值，就切到 encoded 模式。
        """
        saw_nonbinary = False

        for row in raw_rows:
            for col in columns:
                text = str(row.get(col, "")).strip()
                if self._is_binary_like(text):
                    continue
                saw_nonbinary = True
                break
            if saw_nonbinary:
                break

        return "encoded" if saw_nonbinary else "binary"

    def _is_binary_like(self, text: str) -> bool:
        value = str(text).strip().lower()
        if value in self.TRUE_SET or value in self.FALSE_SET:
            return True
        try:
            num = float(value)
            return num in (0.0, 1.0)
        except Exception:
            return False

    def _collect_binary_rows(
            self,
            raw_rows,
            area_names: Sequence[str],
    ) -> List[Tuple[str, str]]:
        rows = []
        seen = set()

        for row in raw_rows:
            taxon = str(row.get("Name", "")).strip()
            if not taxon:
                continue
            if taxon in seen:
                raise ValueError(f"DEC 矩阵中存在重复物种名：{taxon}")
            if any(ch.isspace() for ch in taxon):
                raise ValueError(f"物种名 '{taxon}' 含空格。第一版请先使用无空格 taxon 名。")

            bit_string = "".join(self._normalize_presence_value(row.get(col, "")) for col in area_names)

            if "1" not in bit_string:
                raise ValueError(
                    f"DEC 物种 '{taxon}' 的分布为空。"
                    f"当前导出行为：{bit_string}。"
                    "Lagrange-NG 不接受全 0 tip range。请检查该物种的区域编码。"
                )

            rows.append((taxon, bit_string))
            seen.add(taxon)

        if not rows:
            raise ValueError("DEC 矩阵没有可导出的有效行。")
        return rows

    def _collect_encoded_rows(
            self,
            raw_rows,
            columns: Sequence[str],
    ) -> Tuple[List[Tuple[str, str]], List[str]]:
        encoded_rows = []
        seen = set()

        for row in raw_rows:
            taxon = str(row.get("Name", "")).strip()
            if not taxon:
                continue
            if taxon in seen:
                raise ValueError(f"DEC 矩阵中存在重复物种名：{taxon}")
            if any(ch.isspace() for ch in taxon):
                raise ValueError(f"物种名 '{taxon}' 含空格。第一版请先使用无空格 taxon 名。")

            state_parts = []
            for col in columns:
                text = str(row.get(col, "")).strip()
                if text:
                    state_parts.append(text)

            state_text = "".join(state_parts).strip()
            tokens = self._parse_encoded_state_tokens(state_text)

            if not tokens:
                raise ValueError(
                    f"DEC 物种 '{taxon}' 的状态编码为空或无法形成有效区域集合：{state_text!r}。"
                    "Lagrange-NG 不接受空分布 tip range。"
                )

            encoded_rows.append((taxon, state_text, tokens))
            seen.add(taxon)

        if not encoded_rows:
            raise ValueError("DEC 矩阵没有可导出的有效行。")

        area_names = self._infer_area_names_from_encoded_rows(encoded_rows)
        rows = []

        for taxon, state_text, tokens in encoded_rows:
            token_set = set(tokens)
            bit_string = "".join("1" if area in token_set else "0" for area in area_names)

            if "1" not in bit_string:
                raise ValueError(
                    f"DEC 物种 '{taxon}' 的状态编码 {state_text!r} 导出后为空分布：{bit_string}。"
                )

            rows.append((taxon, bit_string))

        return rows, area_names

    def _parse_encoded_state_tokens(self, state_text: str) -> List[str]:
        text = str(state_text).strip()
        if text.lower() in self.FALSE_SET:
            return []

        text = text.strip()
        text = text.replace("{", "").replace("}", "")
        text = text.replace("[", "").replace("]", "")
        text = text.replace("(", "").replace(")", "")
        text = text.replace("'", "").replace('"', "")
        text = text.strip()

        if not text:
            return []

        # 如果存在明显分隔符，就按分隔符拆
        if re.search(r"[,;/|+\s]", text):
            tokens = [x.strip().upper() for x in re.split(r"[\s,;/|+]+", text) if x.strip()]
            return tokens

        # 没有分隔符时，第一版按单字符区域码处理：
        # A / B / AB / ABC
        if re.fullmatch(r"[A-Za-z0-9]+", text):
            return [ch.upper() for ch in text]

        raise ValueError(
            f"DEC 状态编码无法解析：{state_text!r}。"
            "第一版支持 A/B/AB/ABC 或 A,B / A+B / A|B 这类写法。"
        )

    def _infer_area_names_from_encoded_rows(
        self,
        encoded_rows: Sequence[Tuple[str, str, Sequence[str]]],
    ) -> List[str]:
        areas = []

        for _taxon, _state_text, tokens in encoded_rows:
            for token in tokens:
                if token not in areas:
                    areas.append(token)

        if not areas:
            raise ValueError("DEC 编码矩阵中未解析出任何区域。")

        areas.sort(key=lambda x: (len(x), x))
        return areas

    def _normalize_presence_value(self, value) -> str:
        text = str(value).strip().lower()

        if text in self.TRUE_SET:
            return "1"
        if text in self.FALSE_SET:
            return "0"

        try:
            num = float(text)
            return "1" if num > 0 else "0"
        except Exception:
            pass

        raise ValueError(f"DEC 矩阵包含非 0/1 值：{value!r}。第一版只接受 presence/absence 矩阵。")

    def _validate_tree_and_matrix(self, tree, rows: Sequence[Tuple[str, str]]) -> None:
        if tree is None:
            raise ValueError("DEC 缺少树对象。")

        if not hasattr(tree, "get_leaf_names"):
            raise ValueError("当前树对象不支持 get_leaf_names()，无法导出 DEC 输入。")

        tree_taxa = list(tree.get_leaf_names())
        matrix_taxa = [name for name, _ in rows]

        tree_set = set(tree_taxa)
        matrix_set = set(matrix_taxa)

        missing_in_matrix = sorted(tree_set - matrix_set)
        missing_in_tree = sorted(matrix_set - tree_set)

        if missing_in_matrix or missing_in_tree:
            parts = []
            if missing_in_matrix:
                preview = ", ".join(missing_in_matrix[:10])
                parts.append(f"树中有但矩阵中缺失：{preview}")
            if missing_in_tree:
                preview = ", ".join(missing_in_tree[:10])
                parts.append(f"矩阵中有但树中缺失：{preview}")
            raise ValueError("DEC 的树和矩阵 taxon 不一致。 " + "；".join(parts))

    def _choose_max_areas(
            self,
            rows: Sequence[Tuple[str, str]],
            user_value: Optional[int],
    ) -> int:
        if not rows:
            raise ValueError("DEC 矩阵为空，无法确定 max_areas。")

        area_count = len(rows[0][1])

        if user_value is None:
            # 第一版默认 4；如果实际区域数少于 4，则自动截断到区域数
            raise ValueError("DEC max_areas must come from the active config object.")

        value = int(user_value)
        if value <= 0:
            raise ValueError("DEC 的 max_areas 必须大于 0。")

        return max(1, min(value, area_count))

    def _write_tree(self, tree, tree_path: Path) -> None:
        tree_path.parent.mkdir(parents=True, exist_ok=True)

        if hasattr(tree, "write"):
            try:
                tree.write(outfile=str(tree_path), format=1)
                return
            except TypeError:
                newick = tree.write(format=1)
                tree_path.write_text(newick + ("\n" if not newick.endswith("\n") else ""), encoding="utf-8")
                return

        raise ValueError("当前树对象不支持 write()，无法导出 DEC treefile。")

    def _normalize_root_age(self, root_age) -> Optional[float]:
        try:
            value = float(str(root_age).strip())
        except Exception:
            return None
        if value <= 0:
            return None
        return value

    def _prepare_tree_for_dec(self, tree, *, root_age, scale_tree_to_root_age):
        if not scale_tree_to_root_age or root_age is None:
            return tree, None

        tree_copy = self._copy_tree(tree)
        current_height = self._get_root_height(tree_copy)
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

    def _get_root_height(self, tree) -> float:
        max_height = 0.0

        def visit(node, depth):
            nonlocal max_height
            if not self._is_root_node(node, tree):
                depth += float(getattr(node, "dist", 0.0) or 0.0)
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

    def _write_phylip(
        self,
        rows: Sequence[Tuple[str, str]],
        area_names: Sequence[str],
        data_path: Path,
    ) -> None:
        data_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [f"{len(rows)} {len(area_names)}"]
        for taxon, bits in rows:
            lines.append(f"{taxon} {bits}")
        data_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_period_matrix_files(
        self,
        *,
        workdir: Path,
        area_names: Sequence[str],
        period_times: Optional[Sequence[float]],
        dispersal_matrices: Optional[Sequence[Sequence[Sequence[float]]]],
        period_include_area_bits: Optional[object] = None,
        period_exclude_area_bits: Optional[object] = None,
    ) -> List[str]:
        n = len(area_names)
        if n <= 0:
            return []

        matrices = list(dispersal_matrices or [])
        times = [float(x) for x in list(period_times or [])]
        raw_rule_count = max(
            self._period_area_bits_count(period_include_area_bits),
            self._period_area_bits_count(period_exclude_area_bits),
        )
        period_count = max(len(matrices), len(times) - 1 if len(times) >= 2 else 0, raw_rule_count)
        if period_count <= 0:
            return []

        include_bits_by_period = self._normalize_period_area_bit_rows(
            period_include_area_bits,
            n,
            period_count,
            allow_multiple=False,
        )
        exclude_bits_by_period = self._normalize_period_area_bit_rows(
            period_exclude_area_bits,
            n,
            period_count,
            allow_multiple=True,
        )

        if not matrices:
            matrices = [self._default_dispersal_matrix(n) for _idx in range(period_count)]
        elif len(matrices) < period_count:
            matrices = list(matrices) + [
                self._default_dispersal_matrix(n)
                for _idx in range(period_count - len(matrices))
            ]

        has_active_period_content = any(
            not self._is_default_dispersal_matrix(matrix, n)
            for matrix in matrices
        ) or any(include_bits_by_period) or any(exclude_bits_by_period)
        if not has_active_period_content:
            return []

        lines = []
        for period_index, matrix in enumerate(matrices):
            include_bits = include_bits_by_period[period_index]
            exclude_bits = exclude_bits_by_period[period_index]
            if (
                self._is_default_dispersal_matrix(matrix, n)
                and len(times) < 2
                and not include_bits
                and not exclude_bits
            ):
                continue

            period_name = "period_%s" % period_index
            lines.append("period %s" % period_name)
            if include_bits:
                lines.append("period %s include = %s" % (period_name, include_bits))
            if exclude_bits:
                lines.append("period %s exclude = %s" % (period_name, exclude_bits))
            if period_index > 0 and period_index < len(times):
                lines.append("period %s start = %s" % (period_name, self._format_float(times[period_index])))
            if period_index < period_count - 1 and (period_index + 1) < len(times):
                lines.append("period %s end = %s" % (period_name, self._format_float(times[period_index + 1])))

            if not self._is_default_dispersal_matrix(matrix, n):
                matrix_filename = "period_%s_matrix.csv" % period_index
                self._write_adjustment_matrix_csv(workdir / matrix_filename, area_names, matrix)
                lines.append("period %s matrix = %s" % (period_name, self._quote_if_needed(matrix_filename)))

        return lines

    def _default_dispersal_matrix(self, size: int) -> List[List[float]]:
        return [[1.0 for _ in range(size)] for _ in range(size)]

    def _period_area_bits_count(self, value) -> int:
        if value is None:
            return 0
        if isinstance(value, str):
            return 1 if value.strip() else 0
        return len(list(value or []))

    def _normalize_period_area_bit_rows(
        self,
        value,
        size: int,
        count: int,
        *,
        allow_multiple: bool,
    ) -> List[str]:
        if isinstance(value, str):
            raw = [value for _idx in range(count)] if value.strip() else []
        else:
            raw = list(value or [])
        values = []
        for idx in range(count):
            text = str(raw[idx]).strip() if idx < len(raw) else ""
            if not text:
                values.append("")
                continue
            if len(text) != size or any(ch not in "01" for ch in text):
                raise ValueError(
                    "lagrange-ng period area mask must be a %s-bit 0/1 string: %r"
                    % (size, text)
                )
            if "1" not in text:
                values.append("")
                continue
            if not allow_multiple and text.count("1") > 1:
                raise ValueError("lagrange-ng period include supports only one area bit: %s" % text)
            values.append(text)
        return values

    def _write_adjustment_matrix_csv(
        self,
        path: Path,
        area_names: Sequence[str],
        matrix: Sequence[Sequence[float]],
    ) -> None:
        lines = ["from,to,dist"]
        n = len(area_names)
        for row in range(n):
            for col in range(n):
                if row == col:
                    continue
                value = 1.0
                if row < len(matrix or []) and col < len(matrix[row] or []):
                    value = float(matrix[row][col])
                lines.append(
                    "%s,%s,%s" % (
                        self._csv_cell(area_names[row]),
                        self._csv_cell(area_names[col]),
                        self._format_float(value),
                    )
                )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _build_mrca_constraint_lines(
        self,
        *,
        mrca_constraints: Optional[Sequence[object]],
        area_names: Sequence[str],
    ) -> List[str]:
        lines = []
        for idx, constraint in enumerate(list(mrca_constraints or [])):
            taxon1 = str(getattr(constraint, "taxon1", "")).strip()
            taxon2 = str(getattr(constraint, "taxon2", "")).strip()
            range_name = str(getattr(constraint, "range_name", "")).strip()
            if not taxon1 or not taxon2 or not range_name:
                continue
            label = "mrca_%s" % idx
            bits = self._range_name_to_bits(range_name, area_names)
            lines.append(
                "mrca %s = %s %s" % (
                    label,
                    self._quote_if_needed(taxon1),
                    self._quote_if_needed(taxon2),
                )
            )
            lines.append("fossil fixed %s = %s" % (label, bits))
        return lines

    def _range_name_to_bits(self, range_name: str, area_names: Sequence[str]) -> str:
        text = str(range_name or "").strip()
        present = set(text)
        return "".join("1" if str(area) in present else "0" for area in area_names)

    def _is_default_dispersal_matrix(self, matrix, size: int) -> bool:
        if not matrix:
            return True
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

    def _csv_cell(self, value) -> str:
        text = str(value)
        if any(ch in text for ch in [",", '"', "\n", "\r"]):
            return '"' + text.replace('"', '""') + '"'
        return text

    def _quote_if_needed(self, value: str) -> str:
        value = str(value)
        if any(ch.isspace() for ch in value):
            return f"'{value}'"
        return value

    def _write_config(
        self,
        *,
        config_path: Path,
        tree_filename: str,
        data_filename: str,
        log_filename: str,
        area_names: Sequence[str],
        max_areas: int,
        workers: int,
        threads_per_worker: int,
        include_states: bool,
        include_splits: bool,
        output_type: str,
        opt_method: str,
        mode: str,
        dispersion: Optional[float],
        extinction: Optional[float],
        expm_mode: Optional[str],
        allow_ambiguous: Optional[bool],
        lwr_threshold: Optional[float],
        extra_control_lines: Optional[Sequence[str]],
        period_control_lines: Optional[Sequence[str]],
        mrca_control_lines: Optional[Sequence[str]],
    ) -> None:
        lines = [
            f"treefile = {self._quote_if_needed(tree_filename)}",
            f"datafile = {self._quote_if_needed(data_filename)}",
            "areanames = " + " ".join(self._quote_if_needed(x) for x in area_names),
            f"workers = {max(1, int(workers))}",
            f"threads-per-worker = {max(1, int(threads_per_worker))}",
            f"maxareas = {int(max_areas)}",
            f"mode = {str(mode or 'optimize').strip()}",
            f"output-type = {output_type}",
            f"opt-method = {opt_method}",
            f"logfile = {self._quote_if_needed(log_filename)}",
        ]

        if allow_ambiguous is not None:
            lines.append("allow-ambiguous = %s" % ("true" if allow_ambiguous else "false"))
        if expm_mode:
            lines.append(f"expm-mode = {str(expm_mode).strip()}")
        if dispersion is not None:
            lines.append(f"dispersion = {float(dispersion)}")
        if extinction is not None:
            lines.append(f"extinction = {float(extinction)}")
        if include_states:
            lines.append("states")
        if include_splits:
            lines.append("splits")
        if lwr_threshold is not None:
            lines.append(f"lh-epsilon = {float(lwr_threshold)}")
        lines.extend(str(line).strip() for line in list(period_control_lines or []) if str(line).strip())
        lines.extend(str(line).strip() for line in list(mrca_control_lines or []) if str(line).strip())
        for line in list(extra_control_lines or []):
            text = str(line).strip()
            if text and not text.startswith("#"):
                lines.append(text)

        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

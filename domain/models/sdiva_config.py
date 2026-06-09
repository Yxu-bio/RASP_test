from dataclasses import dataclass, field
from itertools import combinations
import re
from typing import List


EMPTY_STATE_TOKENS = {"", "0", "-", "?", "NA", "N/A", "NONE", "NULL"}
TRUTHY_STATE_TOKENS = {"1", "TRUE", "T", "YES", "Y", "PRESENT", "+"}
FALSY_STATE_TOKENS = {"0", "FALSE", "F", "NO", "N", "ABSENT", "-", ""}


def infer_sdiva_area_names(matrix) -> List[str]:
    if matrix is None:
        return []

    state_columns = [
        str(col).strip()
        for col in list(getattr(matrix, "state_columns", []) or [])
        if str(col).strip() and str(col).strip() not in ("ID", "Name")
    ]
    rows = list(getattr(matrix, "rows", []) or [])

    if len(state_columns) > 1 and _looks_like_binary_area_matrix(rows, state_columns):
        areas = []
        for col in state_columns:
            if any(_is_truthy_area_marker(row.get(col, "")) for row in rows):
                areas.append(col)
        if areas:
            return areas[:15]

    areas = []
    seen = set()
    for row in rows:
        for col in state_columns:
            value = str(row.get(col, "")).strip()
            for area in _split_area_value(value):
                if area not in seen:
                    seen.add(area)
                    areas.append(area)

    if not areas:
        return state_columns[:15]

    if all(len(area) == 1 for area in areas):
        return sorted(areas)[:15]

    return areas[:15]


def _looks_like_binary_area_matrix(rows, state_columns) -> bool:
    saw_value = False
    for row in rows:
        for col in state_columns:
            value = str(row.get(col, "")).strip().upper()
            if value:
                saw_value = True
            if value not in TRUTHY_STATE_TOKENS and value not in FALSY_STATE_TOKENS:
                return False
    return saw_value


def _is_truthy_area_marker(value) -> bool:
    return str(value).strip().upper() in TRUTHY_STATE_TOKENS


def _split_area_value(value: str) -> List[str]:
    text = str(value or "").strip()
    if text.upper() in EMPTY_STATE_TOKENS:
        return []

    if re.search(r"[\s,;|/]+", text):
        return [
            token.strip()
            for token in re.split(r"[\s,;|/]+", text)
            if token.strip() and token.strip().upper() not in EMPTY_STATE_TOKENS
        ]

    if len(text) == 1:
        return [text]

    return [char for char in text if char.strip()]


@dataclass
class SDivaConfig:
    area_names: List[str]
    range_matrix: List[List[bool]]
    include_ranges: List[str] = field(default_factory=list)
    exclude_ranges: List[str] = field(default_factory=list)
    fossil_values: List[str] = field(default_factory=list)
    fossil_node_signature: List[str] = field(default_factory=list)
    use_final_tree: bool = False

    max_areas_enabled: bool = True
    max_areas: int = 4
    allow_extinction: bool = False
    allow_reconstruction: bool = False
    max_reconstructions: int = 100
    random_step_enabled: bool = False
    random_step: int = 2
    final_tree_max_enabled: bool = False
    max_reconstructions_for_final_tree: int = 1000
    keep_enabled: bool = True
    keep_value: int = 65536
    threads: int = 1

    @classmethod
    def default_for_areas(cls, area_names: List[str]):
        names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        n = len(names)
        matrix = [[False for _ in range(n)] for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                matrix[i][j] = True

        config = cls(
            area_names=names,
            range_matrix=matrix,
            max_areas=min(4, n) if n else 4,
        )
        config.refresh_range_lists()
        return config

    def refresh_range_lists(self) -> None:
        include_ranges, exclude_ranges = self.build_range_lists()
        self.include_ranges = include_ranges
        self.exclude_ranges = exclude_ranges

    def build_range_lists(self):
        max_size = min(max(1, int(self.max_areas or 1)), len(self.area_names))
        include_ranges = []
        exclude_ranges = []

        for size in range(2, max_size + 1):
            for combo in combinations(self.area_names, size):
                range_name = "".join(combo)
                if self._is_combo_allowed(combo):
                    include_ranges.append(range_name)
                else:
                    exclude_ranges.append(range_name)

        return include_ranges, exclude_ranges

    def optimize_values(self) -> List[int]:
        return [
            1 if self.max_areas_enabled else 0,
            int(self.max_areas),
            1 if self.allow_extinction else 0,
            1 if self.allow_reconstruction else 0,
            int(self.max_reconstructions),
            1 if self.random_step_enabled else 0,
            int(self.random_step),
            1 if self.final_tree_max_enabled else 0,
            int(self.max_reconstructions_for_final_tree),
        ]

    def to_diva_exclude_command(self) -> str:
        ranges = self.runtime_exclude_ranges()
        if not ranges:
            return ""
        return "exclude %s;" % " ".join(ranges)

    def runtime_exclude_ranges(self) -> List[str]:
        ranges = self._ordered_unique(
            str(x).strip().upper()
            for x in list(self.exclude_ranges or [])
            if str(x).strip()
        )
        if ranges:
            return ranges

        _include_ranges, excluded_ranges = self.build_range_lists()
        return self._ordered_unique(
            str(x).strip().upper()
            for x in excluded_ranges
            if str(x).strip()
        )

    def normalized_fossil_values(self, fossil_count: int = 0) -> List[str]:
        values = [str(x).strip().upper() for x in list(self.fossil_values or [])]
        if fossil_count > len(values):
            values.extend([""] * (fossil_count - len(values)))
        elif fossil_count > 0:
            values = values[:fossil_count]
        return values

    def has_fossils(self) -> bool:
        return any(str(x).strip() for x in list(self.fossil_values or []))

    def to_diva_fossil_command(self, fossil_count: int = 0) -> str:
        values = self.normalized_fossil_values(fossil_count=fossil_count)
        if not any(values):
            return ""
        normalized = [value if value else "0" for value in values]
        return "Fossil %s;" % " ".join(normalized)

    def to_diva_optimize_command(self, taxon_count: int = 0, final_tree: bool = False) -> str:
        parts = ["optimize"]
        if self.allow_extinction or self.has_fossils() or self.runtime_exclude_ranges():
            parts.append("enex")
        if self.allow_reconstruction:
            parts.append("Printrecs")
        if self.max_areas_enabled:
            parts.append("Maxareas=%s" % int(self.max_areas))

        if self.random_step_enabled:
            min_t = max(1, int(taxon_count or 1))
        else:
            min_t = 65536
        parts.append("min_t=%s" % min_t)
        parts.append("rand=%s" % int(self.random_step))
        if self.keep_enabled:
            parts.append("keep=%s" % int(self.keep_value))

        if self.allow_reconstruction:
            if final_tree and self.final_tree_max_enabled:
                max_reconstructions = self.max_reconstructions_for_final_tree
            else:
                max_reconstructions = self.max_reconstructions
            parts.append("max_a=%s" % int(max_reconstructions))

        return " ".join(parts) + ";"

    def to_legacy_config_text(self, fossil_count: int = 0) -> str:
        matrix_values = []
        n = len(self.area_names)
        for row in range(n):
            for col in range(n):
                enabled = False
                if row < len(self.range_matrix) and col < len(self.range_matrix[row]):
                    enabled = bool(self.range_matrix[row][col])
                matrix_values.append("1" if enabled else "0")

        fossil_values = [str(x).strip() for x in list(self.fossil_values or [])]
        if fossil_count > len(fossil_values):
            fossil_values.extend([""] * (fossil_count - len(fossil_values)))
        elif fossil_count > 0:
            fossil_values = fossil_values[:fossil_count]

        lines = [
            "[Range list]",
            self._comma_line(matrix_values),
            "[Optimize]",
            self._comma_line([str(x) for x in self.optimize_values()]),
            "[Fossils]",
            self._comma_line(fossil_values),
            "[Include]",
            self._comma_line(self.include_ranges),
            "[Exclude]",
            self._comma_line(self.exclude_ranges),
        ]
        return "\n".join(lines) + "\n"

    def _is_combo_allowed(self, combo) -> bool:
        indexes = [self.area_names.index(area) for area in combo]
        for left, right in combinations(indexes, 2):
            row = min(left, right)
            col = max(left, right)
            if row >= len(self.range_matrix) or col >= len(self.range_matrix[row]):
                return False
            if not bool(self.range_matrix[row][col]):
                return False
        return True

    @staticmethod
    def _comma_line(values) -> str:
        values = [str(value).strip() for value in list(values or [])]
        if not values:
            return ""
        return ",".join(values) + ","

    @staticmethod
    def _ordered_unique(values) -> List[str]:
        result = []
        seen = set()
        for value in values:
            item = str(value).strip()
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

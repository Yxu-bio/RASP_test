import json
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional


SBGB_MODEL_DISPLAY = {
    "DEC": "DEC",
    "DECJ": "DEC+J",
    "DIVALIKE": "DIVALIKE",
    "DIVALIKEJ": "DIVALIKE+J",
    "BAYAREALIKE": "BAYAREALIKE",
    "BAYAREALIKEJ": "BAYAREALIKE+J",
}

SBGB_MODEL_FROM_DISPLAY = {display: key for key, display in SBGB_MODEL_DISPLAY.items()}

SBGB_NULL_RANGE_MODE_DISPLAY = {
    "include": "Include",
    "exclude": "Exclude",
}

SBGB_NULL_RANGE_MODE_FROM_DISPLAY = {
    display: key for key, display in SBGB_NULL_RANGE_MODE_DISPLAY.items()
}


@dataclass
class SBGBConfig:
    area_names: List[str]
    range_matrix: List[List[bool]]
    include_ranges: List[str] = field(default_factory=list)
    exclude_ranges: List[str] = field(default_factory=list)
    taxon_ranges: List[str] = field(default_factory=list)

    max_areas: int = 2
    min_max_areas: int = 1
    cores: int = 1
    model_name: str = "DEC"
    test_j_models: bool = True
    include_null_range: bool = True
    null_range_mode: str = ""

    root_age: str = ""
    period_times: List[float] = field(default_factory=lambda: [0.0])
    time_matrix_kind: str = "dispersal_multipliers"
    period_matrices: List[List[List[float]]] = field(default_factory=list)

    @classmethod
    def default_for_areas(cls, area_names: List[str], taxon_ranges: Optional[List[str]] = None):
        names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        ranges = [str(x).strip() for x in list(taxon_ranges or []) if str(x).strip()]
        n = len(names)
        matrix = [[False for _ in range(n)] for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                matrix[i][j] = True

        min_areas = max([1] + [len(x) for x in ranges])
        max_areas = n if n else max(2, min_areas)
        config = cls(
            area_names=names,
            range_matrix=matrix,
            taxon_ranges=ranges,
            min_max_areas=min_areas,
            max_areas=max_areas,
            period_matrices=[cls._default_matrix(n)],
        )
        config.refresh_range_lists()
        return config

    @staticmethod
    def _default_matrix(size: int) -> List[List[float]]:
        return [[1.0 for _ in range(size)] for _ in range(size)]

    def validate(self) -> None:
        names = [str(x).strip() for x in list(self.area_names or []) if str(x).strip()]
        if not names:
            raise ValueError("No areas were detected from the matrix.")
        if len(set(names)) != len(names):
            raise ValueError("Area names must be unique.")

        self.area_names = names
        self.taxon_ranges = [str(x).strip() for x in list(self.taxon_ranges or []) if str(x).strip()]
        self.min_max_areas = max([1] + [len(x) for x in self.taxon_ranges] + [int(self.min_max_areas or 1)])
        self.max_areas = max(self.min_max_areas, min(int(self.max_areas or self.min_max_areas), len(names)))
        self.cores = max(1, int(self.cores or 1))
        self.model_name = normalize_sbgb_model_name(self.model_name)
        self.test_j_models = bool(self.test_j_models)
        self.null_range_mode = normalize_sbgb_null_range_mode(
            self.null_range_mode,
            self.include_null_range,
        )
        self.include_null_range = self.null_range_mode == "include"
        self.range_matrix = self._normalize_range_matrix(self.range_matrix, len(names))
        self.include_ranges = self._normalize_range_names(self.include_ranges)
        self.exclude_ranges = [
            value for value in self._normalize_range_names(self.exclude_ranges)
            if value not in set(self.taxon_ranges)
        ]
        self.period_times = self._normalize_period_times(self.period_times)
        self.period_matrices = self._normalize_period_matrices(self.period_matrices, len(names), self.period_count())
        if self.time_matrix_kind not in self.time_matrix_kinds():
            self.time_matrix_kind = "dispersal_multipliers"

    def refresh_range_lists(self) -> None:
        include_ranges, exclude_ranges = self.build_range_lists()
        self.include_ranges = include_ranges
        self.exclude_ranges = exclude_ranges

    def build_range_lists(self):
        max_size = min(max(1, int(self.max_areas or 1)), len(self.area_names))
        taxon_ranges = set(self.taxon_ranges)
        include_ranges = []
        exclude_ranges = []

        for size in range(2, max_size + 1):
            for combo in combinations(self.area_names, size):
                range_name = "".join(combo)
                if self._is_combo_allowed(combo) or range_name in taxon_ranges:
                    include_ranges.append(range_name)
                else:
                    exclude_ranges.append(range_name)

        return include_ranges, exclude_ranges

    def runtime_include_ranges(self) -> List[str]:
        values = ["_"] if self.include_null_range else []
        values.extend(self.area_names)
        values.extend(self.taxon_ranges)
        values.extend(self.include_ranges)
        return self._dedupe(values)

    def runtime_exclude_ranges(self) -> List[str]:
        taxon_ranges = set(self.taxon_ranges)
        return self._dedupe([x for x in self.exclude_ranges if x not in taxon_ranges])

    def period_count(self) -> int:
        if self.period_times and len(self.period_times) > 1:
            return max(1, len(self.period_times) - 1)
        return max(1, len(self.period_matrices or []))

    def has_time_stratified(self) -> bool:
        matrices = self._normalize_period_matrices(self.period_matrices, len(self.area_names), self.period_count())
        if len(matrices) > 1:
            return True
        return any(not self._is_default_matrix(matrix) for matrix in matrices)

    def engine_kwargs(self) -> Dict[str, object]:
        self.validate()
        return {
            "model_name": self.model_name,
            "max_range_size": self.max_areas,
            "include_null_range": bool(self.include_null_range),
            "null_range_mode": self.null_range_mode,
            "cores": self.cores,
            "threads": self.cores,
            "test_j_models": bool(self.test_j_models),
            "root_age": self.root_age,
            "include_ranges": self.runtime_include_ranges(),
            "exclude_ranges": self.runtime_exclude_ranges(),
            "period_times": list(self.period_times),
            "time_matrix_kind": self.time_matrix_kind,
            "period_matrices": list(self.period_matrices),
        }

    def to_preset_dict(self) -> Dict[str, object]:
        return {
            "area_names": list(self.area_names or []),
            "range_matrix": [list(row) for row in list(self.range_matrix or [])],
            "include_ranges": list(self.include_ranges or []),
            "exclude_ranges": list(self.exclude_ranges or []),
            "taxon_ranges": list(self.taxon_ranges or []),
            "max_areas": int(self.max_areas),
            "min_max_areas": int(self.min_max_areas),
            "cores": int(self.cores),
            "model_name": str(self.model_name or "DEC"),
            "test_j_models": bool(self.test_j_models),
            "include_null_range": bool(self.include_null_range),
            "null_range_mode": str(self.null_range_mode or ""),
            "root_age": str(self.root_age or ""),
            "period_times": [float(value) for value in list(self.period_times or [])],
            "time_matrix_kind": str(self.time_matrix_kind or "dispersal_multipliers"),
            "period_matrices": [
                [list(row) for row in list(matrix or [])]
                for matrix in list(self.period_matrices or [])
            ],
        }

    def to_preset_json_text(self) -> str:
        self.validate()
        payload = {
            "format": "RASP-Python BioGeoBEARS config",
            "version": 1,
            "config": self.to_preset_dict(),
            "runtime": self.engine_kwargs(),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_preset_json_text(cls, text: str, area_names: List[str], taxon_ranges=None, base_config=None):
        try:
            payload = json.loads(str(text or ""))
        except Exception as exc:
            raise ValueError("Not a JSON BioGeoBEARS setting file.") from exc

        if not isinstance(payload, dict):
            raise ValueError("Invalid BioGeoBEARS setting file: root must be an object.")

        data = payload.get("config", payload)
        if not isinstance(data, dict):
            raise ValueError("Invalid BioGeoBEARS setting file: missing config object.")

        names = [str(value).strip() for value in list(area_names or []) if str(value).strip()]
        saved_areas = [
            str(value).strip()
            for value in list(data.get("area_names", []) or [])
            if str(value).strip()
        ]
        if saved_areas and saved_areas != names:
            raise ValueError(
                "The setting file areas (%s) do not match the current data areas (%s)."
                % (", ".join(saved_areas), ", ".join(names))
            )

        current_taxon_ranges = [
            str(value).strip()
            for value in list(taxon_ranges or [])
            if str(value).strip()
        ]
        base = base_config if base_config is not None else cls.default_for_areas(names, current_taxon_ranges)

        def value(name, default):
            return data.get(name, getattr(base, name, default))

        saved_taxon_ranges = list(value("taxon_ranges", current_taxon_ranges) or [])
        if current_taxon_ranges:
            saved_taxon_ranges = current_taxon_ranges

        config = cls(
            area_names=names,
            range_matrix=value("range_matrix", getattr(base, "range_matrix", [])),
            include_ranges=list(value("include_ranges", []) or []),
            exclude_ranges=list(value("exclude_ranges", []) or []),
            taxon_ranges=saved_taxon_ranges,
            max_areas=int(value("max_areas", getattr(base, "max_areas", 2)) or 2),
            min_max_areas=int(value("min_max_areas", getattr(base, "min_max_areas", 1)) or 1),
            cores=int(value("cores", getattr(base, "cores", 1)) or 1),
            model_name=str(value("model_name", getattr(base, "model_name", "DEC")) or "DEC"),
            test_j_models=bool(value("test_j_models", getattr(base, "test_j_models", True))),
            include_null_range=bool(value("include_null_range", getattr(base, "include_null_range", True))),
            null_range_mode=str(value("null_range_mode", getattr(base, "null_range_mode", "")) or ""),
            root_age=str(value("root_age", getattr(base, "root_age", "")) or ""),
            period_times=list(value("period_times", getattr(base, "period_times", [0.0])) or [0.0]),
            time_matrix_kind=str(value("time_matrix_kind", getattr(base, "time_matrix_kind", "dispersal_multipliers")) or "dispersal_multipliers"),
            period_matrices=list(value("period_matrices", getattr(base, "period_matrices", [])) or []),
        )
        config.validate()
        return config

    @staticmethod
    def time_matrix_kinds() -> List[str]:
        return [
            "dispersal_multipliers",
            "areas_allowed",
            "areas_adjacency",
            "distances",
        ]

    def _is_combo_allowed(self, combo) -> bool:
        indexes = [self.area_names.index(area) for area in combo]
        for left, right in combinations(indexes, 2):
            row = min(left, right)
            col = max(left, right)
            if not self.range_matrix[row][col]:
                return False
        return True

    def _normalize_range_matrix(self, matrix, size: int) -> List[List[bool]]:
        normalized = [[False for _ in range(size)] for _ in range(size)]
        for row in range(size):
            for col in range(size):
                if row < col:
                    value = False
                    if row < len(matrix or []) and col < len(matrix[row] or []):
                        value = bool(matrix[row][col])
                    normalized[row][col] = value
        return normalized

    def _normalize_range_names(self, ranges) -> List[str]:
        allowed_chars = set(self.area_names)
        values = []
        for value in list(ranges or []):
            text = str(value).strip()
            if not text:
                continue
            if text == "_":
                values.append(text)
                continue
            parts = [char for char in text if char in allowed_chars]
            if parts:
                ordered = "".join([area for area in self.area_names if area in set(parts)])
                if ordered:
                    values.append(ordered)
        return self._dedupe(values)

    def _normalize_period_times(self, times) -> List[float]:
        values = []
        for value in list(times or []):
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

    def _normalize_period_matrices(self, matrices, size: int, period_count: int) -> List[List[List[float]]]:
        period_count = max(1, int(period_count or 1))
        values = []
        for index in range(period_count):
            matrix = matrices[index] if index < len(matrices or []) else None
            values.append(self._normalize_one_matrix(matrix, size))
        return values

    def _normalize_one_matrix(self, matrix, size: int) -> List[List[float]]:
        normalized = self._default_matrix(size)
        for row in range(size):
            for col in range(size):
                if row < len(matrix or []) and col < len(matrix[row] or []):
                    try:
                        normalized[row][col] = float(matrix[row][col])
                    except Exception:
                        normalized[row][col] = 1.0
        return normalized

    def _is_default_matrix(self, matrix) -> bool:
        normalized = self._normalize_one_matrix(matrix, len(self.area_names))
        for row in normalized:
            for value in row:
                if abs(float(value) - 1.0) > 1e-12:
                    return False
        return True

    def _dedupe(self, values) -> List[str]:
        seen = set()
        out = []
        for value in values:
            text = str(value).strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out


def normalize_sbgb_model_name(model_name: str) -> str:
    value = str(model_name or "DEC").strip().upper().replace("+", "")
    if value in SBGB_MODEL_DISPLAY:
        return value
    if value in SBGB_MODEL_FROM_DISPLAY:
        return SBGB_MODEL_FROM_DISPLAY[value]
    raise ValueError("Unsupported BioGeoBEARS model: %s" % model_name)


def normalize_sbgb_null_range_mode(mode: str, include_null_range=True) -> str:
    value = str(mode or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "include_null_range": "include",
        "include_null": "include",
        "official": "include",
        "dec": "include",
        "true": "include",
        "1": "include",
        "exclude_null_range": "exclude",
        "exclude_null": "exclude",
        "no_null": "exclude",
        "dec_star": "exclude",
        "dec*": "exclude",
        "false": "exclude",
        "0": "exclude",
    }
    if value in aliases:
        value = aliases[value]
    if value in SBGB_NULL_RANGE_MODE_DISPLAY:
        return value
    if value in SBGB_NULL_RANGE_MODE_FROM_DISPLAY:
        return SBGB_NULL_RANGE_MODE_FROM_DISPLAY[value]
    return "include" if bool(include_null_range) else "exclude"

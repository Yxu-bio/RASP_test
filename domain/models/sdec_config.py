from dataclasses import dataclass, field
from itertools import combinations
import json
from typing import Dict, List, Optional


OPT_METHODS = ("bobyqa", "nelder-mead", "cobyla", "bfgs", "stogo", "direct")
RUN_MODES = ("optimize", "evaluate")
EXPM_MODES = ("", "adaptive", "krylov", "pade")


@dataclass
class SDECMRCAConstraint:
    taxon1: str
    taxon2: str
    range_name: str


@dataclass
class SDECConfig:
    area_names: List[str]
    range_matrix: List[List[bool]]
    include_ranges: List[str] = field(default_factory=list)
    exclude_ranges: List[str] = field(default_factory=list)
    use_include_list: bool = False
    max_areas: int = 2
    threads: int = 1

    root_age: str = ""
    period_times: List[float] = field(default_factory=lambda: [0.0])
    dispersal_matrices: List[List[List[float]]] = field(default_factory=list)
    period_include_area_bits: List[str] = field(default_factory=list)
    period_exclude_area_bits: List[str] = field(default_factory=list)
    mrca_constraints: List[SDECMRCAConstraint] = field(default_factory=list)

    include_splits: bool = False
    allow_ambiguous: bool = True
    opt_method: str = "bobyqa"
    mode: str = "optimize"
    use_fixed_rates: bool = False
    dispersion: float = 0.1
    extinction: float = 0.1
    expm_mode: str = ""
    lwr_threshold_enabled: bool = False
    lwr_threshold: float = 0.0
    extra_control_lines: List[str] = field(default_factory=list)

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
            max_areas=min(2, n) if n else 2,
            dispersal_matrices=[cls._default_dispersal_matrix(n)],
        )
        config.refresh_range_lists()
        return config

    @staticmethod
    def _default_dispersal_matrix(size: int) -> List[List[float]]:
        return [[1.0 for _ in range(size)] for _ in range(size)]

    def validate(self) -> None:
        names = [str(x).strip() for x in list(self.area_names or []) if str(x).strip()]
        if not names:
            raise ValueError("S-DEC requires at least one area.")

        self.area_names = names
        self.max_areas = max(1, min(int(self.max_areas or 1), len(names)))
        self.threads = max(1, int(self.threads or 1))

        self.range_matrix = self._normalize_range_matrix(self.range_matrix, len(names))
        self.include_ranges = self._normalize_ranges(self.include_ranges)
        self.exclude_ranges = self._normalize_ranges(self.exclude_ranges)

        self.period_times = self._normalize_period_times(self.period_times)
        self._validate_root_age_periods()
        self.dispersal_matrices = self._normalize_dispersal_matrices(
            self.dispersal_matrices,
            self.period_matrix_count(),
            len(names),
        )
        period_count = self.period_matrix_count()
        self.period_include_area_bits = self._normalize_period_area_bits(
            self.period_include_area_bits,
            period_count,
            len(names),
            allow_multiple=False,
        )
        self.period_exclude_area_bits = self._normalize_period_area_bits(
            self.period_exclude_area_bits,
            period_count,
            len(names),
            allow_multiple=True,
        )
        self._validate_area_rule_conflicts()

        self.mrca_constraints = [
            constraint
            for constraint in list(self.mrca_constraints or [])
            if str(constraint.taxon1).strip()
            and str(constraint.taxon2).strip()
            and str(constraint.range_name).strip()
        ]
        for constraint in self.mrca_constraints:
            range_size = self.range_to_bits(constraint.range_name).count("1")
            if range_size > self.max_areas:
                raise ValueError(
                    "MRCA/Fossil range %s uses %s areas, but Maximum areas is %s."
                    % (constraint.range_name, range_size, self.max_areas)
                )

        self.opt_method = str(self.opt_method or "bobyqa").strip().lower()
        if self.opt_method not in OPT_METHODS:
            raise ValueError("Unsupported lagrange-ng opt-method: %s" % self.opt_method)

        self.mode = str(self.mode or "optimize").strip().lower()
        if self.mode not in RUN_MODES:
            raise ValueError("Unsupported lagrange-ng mode: %s" % self.mode)

        self.expm_mode = str(self.expm_mode or "").strip().lower()
        if self.expm_mode not in EXPM_MODES:
            raise ValueError("Unsupported lagrange-ng expm-mode: %s" % self.expm_mode)

        self.dispersion = float(self.dispersion)
        self.extinction = float(self.extinction)
        if self.dispersion < 0 or self.extinction < 0:
            raise ValueError("Dispersion and extinction must be non-negative.")

        self.lwr_threshold = float(self.lwr_threshold)
        if self.lwr_threshold_enabled and not (0.0 <= self.lwr_threshold <= 1.0):
            raise ValueError("LWR threshold must be between 0 and 1.")

        self.extra_control_lines = [
            str(line).strip()
            for line in list(self.extra_control_lines or [])
            if str(line).strip() and not str(line).strip().startswith("#")
        ]

    def _validate_root_age_periods(self) -> None:
        try:
            root_age = float(str(self.root_age or "").strip())
        except Exception:
            return
        if root_age <= 0:
            return
        count = sum(1 for value in list(self.period_times or [])[1:] if float(value) >= root_age)
        if count > 1:
            raise ValueError(
                "The timeperiods has to have just only one oldest time that is older than the root age of the tree."
            )

    def refresh_range_lists(self) -> None:
        include_ranges, exclude_ranges = self.build_range_lists()
        self.include_ranges = include_ranges
        self.exclude_ranges = exclude_ranges

    def to_legacy_config_text(self) -> str:
        matrix_values = []
        n = len(self.area_names)
        for row in range(n):
            for col in range(n):
                enabled = False
                if row < len(self.range_matrix or []) and col < len(self.range_matrix[row] or []):
                    enabled = bool(self.range_matrix[row][col])
                matrix_values.append("1" if enabled else "0")

        lines = [
            "[Range list]",
            self._comma_line(matrix_values),
            "[Optimize]",
            self._comma_line([int(self.max_areas), 1 if self.use_include_list else 0]),
            "[Fossils]",
            "",
            "[Include]",
            self._comma_line(self.include_ranges),
            "[Exclude]",
            self._comma_line(self.exclude_ranges),
            "[Period include]",
            self._comma_line(self.period_include_area_bits),
            "[Period exclude]",
            self._comma_line(self.period_exclude_area_bits),
        ]
        return "\n".join(lines) + "\n"

    def to_preset_dict(self) -> Dict[str, object]:
        return {
            "area_names": list(self.area_names or []),
            "range_matrix": [list(row) for row in list(self.range_matrix or [])],
            "include_ranges": list(self.include_ranges or []),
            "exclude_ranges": list(self.exclude_ranges or []),
            "use_include_list": bool(self.use_include_list),
            "max_areas": int(self.max_areas),
            "threads": int(self.threads),
            "root_age": str(self.root_age or ""),
            "period_times": [float(value) for value in list(self.period_times or [])],
            "dispersal_matrices": [
                [list(row) for row in list(matrix or [])]
                for matrix in list(self.dispersal_matrices or [])
            ],
            "period_include_area_bits": list(self.period_include_area_bits or []),
            "period_exclude_area_bits": list(self.period_exclude_area_bits or []),
            "mrca_constraints": [
                {
                    "taxon1": str(constraint.taxon1),
                    "taxon2": str(constraint.taxon2),
                    "range_name": str(constraint.range_name),
                }
                for constraint in list(self.mrca_constraints or [])
            ],
            "include_splits": bool(self.include_splits),
            "allow_ambiguous": bool(self.allow_ambiguous),
            "opt_method": str(self.opt_method or "bobyqa"),
            "mode": str(self.mode or "optimize"),
            "use_fixed_rates": bool(self.use_fixed_rates),
            "dispersion": float(self.dispersion),
            "extinction": float(self.extinction),
            "expm_mode": str(self.expm_mode or ""),
            "lwr_threshold_enabled": bool(self.lwr_threshold_enabled),
            "lwr_threshold": float(self.lwr_threshold),
            "extra_control_lines": list(self.extra_control_lines or []),
        }

    def to_preset_json_text(self) -> str:
        payload = {
            "format": "RASP-Python DEC/S-DEC config",
            "version": 1,
            "config": self.to_preset_dict(),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_preset_json_text(cls, text: str, area_names: List[str], base_config=None):
        try:
            payload = json.loads(str(text or ""))
        except Exception as exc:
            raise ValueError("Not a JSON DEC/S-DEC setting file.") from exc

        if not isinstance(payload, dict):
            raise ValueError("Invalid DEC/S-DEC setting file: root must be an object.")

        data = payload.get("config", payload)
        if not isinstance(data, dict):
            raise ValueError("Invalid DEC/S-DEC setting file: missing config object.")

        saved_areas = [
            str(value).strip()
            for value in list(data.get("area_names", []) or [])
            if str(value).strip()
        ]
        names = [str(value).strip() for value in list(area_names or []) if str(value).strip()]
        if saved_areas and saved_areas != names:
            raise ValueError(
                "The setting file areas (%s) do not match the current data areas (%s)."
                % (", ".join(saved_areas), ", ".join(names))
            )

        base = base_config if base_config is not None else cls.default_for_areas(names)

        def value(name, default):
            return data.get(name, getattr(base, name, default))

        mrca_constraints = []
        for item in list(value("mrca_constraints", []) or []):
            if not isinstance(item, dict):
                continue
            mrca_constraints.append(
                SDECMRCAConstraint(
                    taxon1=str(item.get("taxon1", "") or ""),
                    taxon2=str(item.get("taxon2", "") or ""),
                    range_name=str(item.get("range_name", "") or ""),
                )
            )

        config = cls(
            area_names=names,
            range_matrix=value("range_matrix", getattr(base, "range_matrix", [])),
            include_ranges=list(value("include_ranges", []) or []),
            exclude_ranges=list(value("exclude_ranges", []) or []),
            use_include_list=bool(value("use_include_list", False)),
            max_areas=int(value("max_areas", 2) or 2),
            threads=int(value("threads", 1) or 1),
            root_age=str(value("root_age", "") or ""),
            period_times=list(value("period_times", [0.0]) or [0.0]),
            dispersal_matrices=list(value("dispersal_matrices", []) or []),
            period_include_area_bits=list(value("period_include_area_bits", []) or []),
            period_exclude_area_bits=list(value("period_exclude_area_bits", []) or []),
            mrca_constraints=mrca_constraints,
            include_splits=bool(value("include_splits", False)),
            allow_ambiguous=bool(value("allow_ambiguous", True)),
            opt_method=str(value("opt_method", "bobyqa") or "bobyqa"),
            mode=str(value("mode", "optimize") or "optimize"),
            use_fixed_rates=bool(value("use_fixed_rates", False)),
            dispersion=float(value("dispersion", 0.1) or 0.1),
            extinction=float(value("extinction", 0.1) or 0.1),
            expm_mode=str(value("expm_mode", "") or ""),
            lwr_threshold_enabled=bool(value("lwr_threshold_enabled", False)),
            lwr_threshold=float(value("lwr_threshold", 0.0) or 0.0),
            extra_control_lines=list(value("extra_control_lines", []) or []),
        )
        config.validate()
        return config

    @classmethod
    def from_legacy_config_text(cls, text: str, area_names: List[str], base_config=None):
        names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        base = base_config if base_config is not None else cls.default_for_areas(names)
        sections = cls._parse_legacy_sections(text)
        n = len(names)

        matrix = [list(row) for row in list(getattr(base, "range_matrix", []) or [])]
        matrix_values = cls._split_legacy_values(sections.get("Range list", ""))
        if len(matrix_values) >= n * n:
            matrix = [[False for _col in range(n)] for _row in range(n)]
            for row in range(n):
                for col in range(n):
                    matrix[row][col] = str(matrix_values[row * n + col]).strip() == "1"

        max_areas = int(getattr(base, "max_areas", 2) or 2)
        use_include_list = bool(getattr(base, "use_include_list", False))
        optimize_values = cls._split_legacy_values(sections.get("Optimize", ""))
        if optimize_values:
            # Old Config_Lagrange saves "Max areas,Use list".
            max_areas = cls._safe_int(optimize_values[0], max_areas)
        if len(optimize_values) >= 2:
            use_include_list = cls._safe_int(optimize_values[1], 1 if use_include_list else 0) == 1

        config = cls(
            area_names=names,
            range_matrix=matrix,
            include_ranges=cls._split_legacy_values(sections.get("Include", "")),
            exclude_ranges=cls._split_legacy_values(sections.get("Exclude", "")),
            use_include_list=use_include_list,
            max_areas=max_areas,
            threads=int(getattr(base, "threads", 1) or 1),
            root_age=str(getattr(base, "root_age", "") or ""),
            period_times=list(getattr(base, "period_times", []) or [0.0]),
            dispersal_matrices=list(getattr(base, "dispersal_matrices", []) or []),
            period_include_area_bits=(
                cls._split_legacy_period_values(sections.get("Period include", ""))
                or list(getattr(base, "period_include_area_bits", []) or [])
            ),
            period_exclude_area_bits=(
                cls._split_legacy_period_values(sections.get("Period exclude", ""))
                or list(getattr(base, "period_exclude_area_bits", []) or [])
            ),
            mrca_constraints=list(getattr(base, "mrca_constraints", []) or []),
            include_splits=bool(getattr(base, "include_splits", False)),
            allow_ambiguous=bool(getattr(base, "allow_ambiguous", True)),
            opt_method=str(getattr(base, "opt_method", "bobyqa") or "bobyqa"),
            mode=str(getattr(base, "mode", "optimize") or "optimize"),
            use_fixed_rates=bool(getattr(base, "use_fixed_rates", False)),
            dispersion=float(getattr(base, "dispersion", 0.1) or 0.1),
            extinction=float(getattr(base, "extinction", 0.1) or 0.1),
            expm_mode=str(getattr(base, "expm_mode", "") or ""),
            lwr_threshold_enabled=bool(getattr(base, "lwr_threshold_enabled", False)),
            lwr_threshold=float(getattr(base, "lwr_threshold", 0.0) or 0.0),
            extra_control_lines=list(getattr(base, "extra_control_lines", []) or []),
        )
        if not config.include_ranges and not config.exclude_ranges:
            config.refresh_range_lists()
        return config

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

    def runtime_include_ranges(self) -> List[str]:
        mrca_ranges = [
            str(constraint.range_name).strip()
            for constraint in list(self.mrca_constraints or [])
            if str(getattr(constraint, "range_name", "")).strip()
        ]
        if self.use_include_list:
            return self._normalize_ranges(list(self.include_ranges or []) + mrca_ranges)
        include_ranges, _exclude_ranges = self.build_range_lists()
        return self._normalize_ranges(include_ranges + mrca_ranges)

    def runtime_exclude_ranges(self) -> List[str]:
        if self.use_include_list:
            return self._normalize_ranges(self.exclude_ranges)
        _include_ranges, exclude_ranges = self.build_range_lists()
        return exclude_ranges

    def range_to_bits(self, range_name: str) -> str:
        text = str(range_name or "").strip()
        present = set(text)
        return "".join("1" if area in present else "0" for area in self.area_names)

    def period_matrix_count(self) -> int:
        if len(self.period_times or []) >= 2:
            return max(1, len(self.period_times) - 1)
        return max(1, len(self.dispersal_matrices or []))

    def has_period_configuration(self) -> bool:
        if len(self.period_times or []) >= 2:
            return True
        return any(not self._is_default_matrix(m) for m in list(self.dispersal_matrices or []))

    def builder_kwargs(self) -> Dict[str, Optional[object]]:
        self.validate()
        rate_values_enabled = bool(self.use_fixed_rates or self.mode == "evaluate")
        return {
            "max_areas": self.max_areas,
            "workers": self.threads,
            "threads_per_worker": 1,
            "include_splits": bool(self.include_splits),
            "opt_method": self.opt_method,
            "mode": self.mode,
            "dispersion": self.dispersion if rate_values_enabled else None,
            "extinction": self.extinction if rate_values_enabled else None,
            "expm_mode": self.expm_mode or None,
            "allow_ambiguous": bool(self.allow_ambiguous),
            "lwr_threshold": self.lwr_threshold if self.lwr_threshold_enabled else None,
            "extra_control_lines": list(self.extra_control_lines),
            "period_times": list(self.period_times),
            "dispersal_matrices": list(self.dispersal_matrices),
            "period_include_area_bits": list(self.period_include_area_bits),
            "period_exclude_area_bits": list(self.period_exclude_area_bits),
            "mrca_constraints": list(self.mrca_constraints),
            "root_age": self.root_age,
        }

    def _validate_area_rule_conflicts(self) -> None:
        for idx, (include_bits, exclude_bits) in enumerate(
            zip(list(self.period_include_area_bits or []), list(self.period_exclude_area_bits or []))
        ):
            if include_bits and exclude_bits and self._area_bits_overlap(include_bits, exclude_bits):
                raise ValueError(
                    "Period area rules conflict in period %s: required area is also excluded." % idx
                )

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

    def _is_default_matrix(self, matrix) -> bool:
        n = len(self.area_names)
        normalized = self._normalize_one_matrix(matrix, n)
        for row in normalized:
            for value in row:
                if abs(float(value) - 1.0) > 1e-12:
                    return False
        return True

    def _normalize_range_matrix(self, matrix, size: int) -> List[List[bool]]:
        normalized = [[False for _ in range(size)] for _ in range(size)]
        for row in range(size):
            for col in range(size):
                if row >= col:
                    normalized[row][col] = False
                    continue
                if row < len(matrix or []) and col < len(matrix[row] or []):
                    normalized[row][col] = bool(matrix[row][col])
                else:
                    normalized[row][col] = True
        return normalized

    @staticmethod
    def _comma_line(values) -> str:
        values = [str(value).strip() for value in list(values or [])]
        if not values:
            return ""
        return ",".join(values) + ","

    @staticmethod
    def _parse_legacy_sections(text: str) -> Dict[str, str]:
        sections = {}
        current = None
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1].strip()
                sections[current] = []
                continue
            if current is not None:
                sections[current].append(line)
        return {key: ",".join(value) for key, value in sections.items()}

    @staticmethod
    def _split_legacy_values(text: str) -> List[str]:
        values = [value.strip() for value in str(text or "").split(",")]
        if values and values[-1] == "":
            values = values[:-1]
        return [value for value in values if value]

    @staticmethod
    def _split_legacy_period_values(text: str) -> List[str]:
        values = [value.strip() for value in str(text or "").split(",")]
        while values and values[-1] == "":
            values = values[:-1]
        if not any(values):
            return []
        return values

    @staticmethod
    def _safe_int(value, default) -> int:
        try:
            return int(float(str(value).strip()))
        except Exception:
            return int(default)

    def _normalize_ranges(self, ranges) -> List[str]:
        values = []
        for value in list(ranges or []):
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
        return sorted(values, key=lambda x: (len(x), x))

    def _normalize_period_times(self, values) -> List[float]:
        times = []
        for value in list(values or []):
            text = str(value).strip()
            if not text:
                continue
            times.append(float(text))
        if not times:
            times = [0.0]
        times = sorted(set(times))
        if times[0] != 0.0:
            times.insert(0, 0.0)
        return times

    def _normalize_dispersal_matrices(self, matrices, count: int, size: int) -> List[List[List[float]]]:
        values = []
        raw = list(matrices or [])
        for idx in range(max(1, count)):
            if idx < len(raw):
                values.append(self._normalize_one_matrix(raw[idx], size))
            else:
                values.append(self._default_dispersal_matrix(size))
        return values

    def _normalize_one_matrix(self, matrix, size: int) -> List[List[float]]:
        normalized = self._default_dispersal_matrix(size)
        for row in range(size):
            for col in range(size):
                if row < len(matrix or []) and col < len(matrix[row] or []):
                    try:
                        normalized[row][col] = float(matrix[row][col])
                    except Exception:
                        normalized[row][col] = 1.0
        return normalized

    def _normalize_period_area_bits(
        self,
        values,
        count: int,
        size: int,
        *,
        allow_multiple: bool,
    ) -> List[str]:
        if isinstance(values, str):
            raw = [values]
        else:
            raw = list(values or [])

        normalized = []
        for idx in range(max(1, count)):
            text = str(raw[idx]).strip() if idx < len(raw) else ""
            if not text:
                normalized.append("")
                continue
            if len(text) != size or any(ch not in "01" for ch in text):
                raise ValueError("Period area rule must be a %s-bit 0/1 string: %s" % (size, text))
            if not allow_multiple and text.count("1") > 1:
                raise ValueError("Require area supports only one area per period: %s" % text)
            normalized.append(text if "1" in text else "")
        return normalized

    def _area_bits_overlap(self, left: str, right: str) -> bool:
        left = str(left or "").strip()
        right = str(right or "").strip()
        return any(
            left[idx] == "1" and right[idx] == "1"
            for idx in range(min(len(left), len(right)))
        )

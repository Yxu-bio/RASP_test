from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PreflightIssue:
    severity: str
    code: str
    message: str


@dataclass
class PreflightReport:
    method_name: str
    issues: List[PreflightIssue] = field(default_factory=list)

    @property
    def blockers(self) -> List[PreflightIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> List[PreflightIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.blockers


class PreflightValidationService:
    VALID_BGB_MODELS = {
        "DEC",
        "DECJ",
        "DIVALIKE",
        "DIVALIKEJ",
        "BAYAREALIKE",
        "BAYAREALIKEJ",
    }

    def validate_range_analysis(self, *, method_name, tree, matrix, config=None, tree_entries=None) -> PreflightReport:
        report = PreflightReport(method_name=str(method_name or "Analysis"))
        tree_taxa = self._tree_taxa(tree)
        matrix_taxa = self._matrix_taxa(matrix)

        if tree is None:
            self._error(report, "tree.missing", "No reference/consensus tree is loaded.")
        elif not tree_taxa:
            self._error(report, "tree.no_taxa", "The reference/consensus tree has no readable tip names.")
        else:
            self._check_duplicates(report, "tree", tree_taxa)

        if matrix is None:
            self._error(report, "matrix.missing", "No range matrix is available.")
        elif not matrix_taxa:
            self._error(report, "matrix.no_taxa", "The range matrix has no readable taxon names.")
        else:
            self._check_duplicates(report, "matrix", matrix_taxa)

        if tree_taxa and matrix_taxa:
            only_tree = sorted(set(tree_taxa) - set(matrix_taxa))
            only_matrix = sorted(set(matrix_taxa) - set(tree_taxa))
            if only_tree or only_matrix:
                message = [
                    "Tree and matrix taxa do not match.",
                    "Only in tree: %s" % (", ".join(only_tree[:20]) if only_tree else "none"),
                    "Only in matrix: %s" % (", ".join(only_matrix[:20]) if only_matrix else "none"),
                ]
                if len(only_tree) > 20 or len(only_matrix) > 20:
                    message.append("Only the first 20 names are shown.")
                self._error(report, "taxa.mismatch", "\n".join(message))

        area_names, max_observed_range = self._validate_range_rows(report, matrix)
        self._validate_config(report, config, area_names, max_observed_range, tree)

        entries = list(tree_entries or [])
        if entries:
            missing_tree_count = sum(1 for entry in entries if getattr(entry, "parsed_tree", entry) is None)
            if missing_tree_count:
                self._warning(
                    report,
                    "treeset.unparsed",
                    "%d tree-set entries have no parsed tree object and may be skipped." % missing_tree_count,
                )
        return report

    def _validate_range_rows(self, report, matrix):
        area_names = [
            str(col).strip()
            for col in list(getattr(matrix, "state_columns", []) or [])
            if str(col).strip()
        ]
        rows = list(getattr(matrix, "rows", []) or [])
        if not area_names:
            self._error(report, "range.no_area_columns", "The active range matrix has no area columns.")
            return [], 0
        if not rows:
            self._error(report, "range.no_rows", "The active range matrix has no rows.")
            return area_names, 0

        max_observed = 0
        for row in rows:
            taxon = str(row.get("Name", "") or "").strip()
            if not taxon:
                self._error(report, "range.empty_taxon", "A range matrix row has an empty taxon name.")
                continue
            bits = []
            for area in area_names:
                value = str(row.get(area, "") or "").strip()
                if value not in ("0", "1"):
                    self._error(
                        report,
                        "range.invalid_bit",
                        "Taxon '%s' has invalid value %r in area column '%s'; expected 0 or 1."
                        % (taxon, value, area),
                    )
                bits.append(value)
            observed = bits.count("1")
            max_observed = max(max_observed, observed)
            if observed <= 0:
                self._error(report, "range.empty_range", "Taxon '%s' has an empty range." % taxon)
        return area_names, max_observed

    def _validate_config(self, report, config, area_names, max_observed_range, tree):
        if config is None:
            return

        max_areas = self._first_int_attr(config, ["max_areas", "max_range_size"])
        if max_areas is not None:
            if max_areas <= 0:
                self._error(report, "config.max_areas_nonpositive", "Maximum areas must be greater than 0.")
            if max_observed_range and max_areas < max_observed_range:
                self._error(
                    report,
                    "config.max_areas_too_small",
                    "Maximum areas (%d) is smaller than the largest observed tip range (%d)."
                    % (max_areas, max_observed_range),
                )
            if area_names and max_areas > len(area_names):
                self._warning(
                    report,
                    "config.max_areas_gt_area_count",
                    "Maximum areas (%d) is larger than the number of detected areas (%d)."
                    % (max_areas, len(area_names)),
                )

        for attr in ("threads", "cores", "workers", "threads_per_worker"):
            if hasattr(config, attr):
                value = self._safe_int(getattr(config, attr, None))
                if value is not None and value <= 0:
                    self._error(report, "config.%s_nonpositive" % attr, "%s must be greater than 0." % attr)

        model_name = str(getattr(config, "model_name", "") or "").strip()
        if model_name and model_name.upper() in {name.upper() for name in self.VALID_BGB_MODELS}:
            pass
        elif model_name and "BGB" in str(type(config).__name__).upper():
            self._error(report, "config.unknown_bgb_model", "Unknown BioGeoBEARS model: %s" % model_name)

        root_age = self._safe_float(getattr(config, "root_age", ""))
        if root_age is not None:
            if root_age <= 0.0:
                self._error(report, "config.root_age_nonpositive", "Root age must be greater than 0.")
            tree_height = self._tree_height(tree)
            if tree_height and root_age > 0.0:
                ratio = abs(root_age - tree_height) / max(root_age, tree_height)
                if ratio > 0.25:
                    self._warning(
                        report,
                        "config.root_age_tree_height_gap",
                        "Root age (%g) differs from current tree height (%g). The runner may rescale the tree."
                        % (root_age, tree_height),
                    )

        period_times = [self._safe_float(value) for value in list(getattr(config, "period_times", []) or [])]
        period_times = [value for value in period_times if value is not None]
        if period_times:
            if any(value < 0.0 for value in period_times):
                self._error(report, "config.negative_period", "Time-period values must not be negative.")
            if period_times != sorted(period_times):
                self._error(report, "config.unsorted_periods", "Time periods must be sorted from young to old.")
            if root_age is not None and root_age > 0.0:
                oldest_count = sum(1 for value in period_times[1:] if value >= root_age)
                if oldest_count != 1:
                    self._warning(
                        report,
                        "config.root_age_period_count",
                        "Expected exactly one oldest time period >= root age; found %d." % oldest_count,
                    )

    def _tree_taxa(self, tree) -> List[str]:
        if tree is None:
            return []
        try:
            return [str(name).strip() for name in tree.get_leaf_names() if str(name).strip()]
        except Exception:
            return []

    def _matrix_taxa(self, matrix) -> List[str]:
        return [
            str(name).strip()
            for name in list(getattr(matrix, "taxa_names", []) or [])
            if str(name).strip()
        ]

    def _check_duplicates(self, report, label, values):
        seen = set()
        duplicates = []
        for value in values:
            if value in seen and value not in duplicates:
                duplicates.append(value)
            seen.add(value)
        if duplicates:
            self._error(
                report,
                "%s.duplicates" % label,
                "%s contains duplicated taxon names: %s" % (label, ", ".join(duplicates[:20])),
            )

    def _tree_height(self, tree) -> Optional[float]:
        if tree is None:
            return None
        try:
            leaves = list(tree.iter_leaves())
            if not leaves:
                return None
            return max(float(tree.get_distance(leaf)) for leaf in leaves)
        except Exception:
            return None

    def _first_int_attr(self, config, names):
        for name in names:
            if hasattr(config, name):
                value = self._safe_int(getattr(config, name, None))
                if value is not None:
                    return value
        return None

    def _safe_int(self, value):
        try:
            text = str(value).strip()
            if not text:
                return None
            return int(float(text))
        except Exception:
            return None

    def _safe_float(self, value):
        try:
            text = str(value).strip()
            if not text:
                return None
            return float(text)
        except Exception:
            return None

    def _error(self, report, code, message):
        report.issues.append(PreflightIssue("error", code, message))

    def _warning(self, report, code, message):
        report.issues.append(PreflightIssue("warning", code, message))

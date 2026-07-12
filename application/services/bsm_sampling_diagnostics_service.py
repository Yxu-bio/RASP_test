import math
from collections import Counter
from statistics import median


class BSMSamplingDiagnosticsService:
    """Describe BSM Monte Carlo sampling without judging model adequacy."""

    def describe_count(self, map_count):
        count = max(0, self._int(map_count, 0))
        if count < 10:
            tier = "debug_only"
            label = "Debug only"
        elif count < 50:
            tier = "preview"
            label = "Preview"
        elif count < 100:
            tier = "exploratory"
            label = "Exploratory"
        elif count < 500:
            tier = "standard"
            label = "Standard"
        else:
            tier = "high"
            label = "High sampling"

        half_width = None
        if count > 0:
            # Conservative binomial Monte Carlo interval at p=0.5.
            half_width = 1.96 * math.sqrt(0.25 / float(count))
        return {
            "map_count": count,
            "sampling_tier": tier,
            "sampling_label": label,
            "worst_case_mc95_half_width": half_width,
        }

    def evaluate_timeline(self, timeline, max_branches=200):
        diagnostics = self.describe_count(len(getattr(timeline, "history_sample_ids", []) or []))
        diagnostics.update({
            "stability_status": "not_evaluated",
            "stability_label": "Not evaluated",
            "split_half_query_count": 0,
            "split_half_median_total_variation": None,
            "split_half_p95_total_variation": None,
            "split_half_max_state_difference": None,
        })

        sample_ids = list(getattr(timeline, "history_sample_ids", []) or [])
        segment_index = dict(getattr(timeline, "metadata", {}) or {}).get("history_segment_index", {}) or {}
        if len(sample_ids) < 20 or not segment_index:
            return diagnostics
        if len(getattr(timeline, "history_segments", []) or []) > 500000:
            diagnostics["stability_label"] = "Skipped for large history table"
            return diagnostics

        split_at = len(sample_ids) // 2
        first_ids = sample_ids[:split_at]
        second_ids = sample_ids[split_at:]
        if not first_ids or not second_ids:
            return diagnostics

        branches = list(getattr(timeline, "branches", []) or [])
        branches = self._evenly_spaced(branches, max(1, int(max_branches or 1)))
        total_variations = []
        max_state_differences = []
        for branch in branches:
            span = float(branch.older_time) - float(branch.younger_time)
            if span <= 0.0:
                continue
            samples_for_branch = dict(segment_index.get(branch.branch_id, {}) or {})
            for fraction in (0.25, 0.5, 0.75):
                time_value = float(branch.older_time) - span * fraction
                first = self._probabilities(samples_for_branch, first_ids, time_value)
                second = self._probabilities(samples_for_branch, second_ids, time_value)
                if not first and not second:
                    continue
                total_variation, max_difference = self._distance(first, second)
                total_variations.append(total_variation)
                max_state_differences.append(max_difference)

        if not total_variations:
            return diagnostics

        p95 = self._percentile(total_variations, 0.95)
        if p95 <= 0.10:
            stability_status = "low_variation"
            stability_label = "Low split-half variation"
        elif p95 <= 0.25:
            stability_status = "moderate"
            stability_label = "Moderate split-half variation"
        else:
            stability_status = "high_variation"
            stability_label = "High split-half variation"
        diagnostics.update({
            "stability_status": stability_status,
            "stability_label": stability_label,
            "split_half_query_count": len(total_variations),
            "split_half_median_total_variation": median(total_variations),
            "split_half_p95_total_variation": p95,
            "split_half_max_state_difference": max(max_state_differences or [0.0]),
        })
        return diagnostics

    def _probabilities(self, samples_for_branch, sample_ids, time_value):
        counts = Counter()
        for sample_id in sample_ids:
            state = self._state_at(samples_for_branch.get(sample_id, []), time_value)
            if state:
                counts[state] += 1
        total = float(sum(counts.values()) or 0.0)
        if total <= 0.0:
            return {}
        return dict((state, count / total) for state, count in counts.items())

    def _state_at(self, segments, time_value):
        for segment in reversed(list(segments or [])):
            epsilon = max(1e-9, abs(float(segment.older_time)) * 1e-12)
            if float(segment.younger_time) - epsilon <= float(time_value) <= float(segment.older_time) + epsilon:
                return str(segment.state or "")
        return ""

    def _distance(self, first, second):
        states = set(first) | set(second)
        differences = [abs(float(first.get(state, 0.0)) - float(second.get(state, 0.0))) for state in states]
        return 0.5 * sum(differences), max(differences or [0.0])

    def _percentile(self, values, fraction):
        ordered = sorted(float(value) for value in values)
        if not ordered:
            return 0.0
        rank = max(0, min(len(ordered) - 1, int(math.ceil(float(fraction) * len(ordered))) - 1))
        return ordered[rank]

    def _evenly_spaced(self, values, limit):
        values = list(values or [])
        if len(values) <= limit:
            return values
        if limit <= 1:
            return values[:1]
        indices = []
        for index in range(limit):
            position = int(round(index * (len(values) - 1) / float(limit - 1)))
            if position not in indices:
                indices.append(position)
        return [values[index] for index in indices]

    def _int(self, value, fallback):
        try:
            return int(float(value))
        except Exception:
            return fallback

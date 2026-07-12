import math
import re
from collections import OrderedDict

from domain.models.temporal_range_result import (
    TemporalRangeBranch,
    TemporalRangeFrame,
    TemporalRangeResult,
)


class TemporalRangePlaybackService:
    """Build and sample a visualization-only range timeline.

    Generic reconstructions interpolate node probabilities. BioGeoBEARS can
    additionally use its branch-bottom and branch-top endpoint probabilities.
    Neither mode invents stochastic events inside a branch.
    """

    NULL_STATES = set(["", "/", "_", "null", "none", "empty", "na", "nan"])

    def build(
        self,
        *,
        result,
        method_name="",
        leaf_state_map=None,
        area_records=None,
        range_matrix=None,
        reference_tree=None,
    ):
        if result is None:
            raise ValueError("A reconstruction result is required.")
        tree = reference_tree or getattr(result, "reference_tree", None)
        if tree is None or not hasattr(tree, "traverse"):
            raise ValueError("The reconstruction result does not contain a usable reference tree.")

        source_name = str(method_name or getattr(result, "model_name", "") or type(result).__name__)
        if type(result).__name__ == "ContinuousTraitResult":
            raise ValueError("Spatiotemporal Range Playback requires discrete range probabilities.")

        leaf_state_map = dict(leaf_state_map or {})
        area_records = list(area_records or [])
        node_by_key, key_by_node = self._tree_node_maps(tree)
        node_ages, root_age, age_warnings, age_mode = self._node_ages(tree, key_by_node)
        node_probabilities = self._node_probabilities(result, node_by_key, leaf_state_map)
        node_ids = self._node_ids(result, node_by_key, tree)

        branches = []
        states = []
        endpoint_branch_count = 0
        warnings = list(age_warnings)
        for index, child in enumerate(self._non_root_nodes(tree), 1):
            parent = getattr(child, "up", None)
            if parent is None:
                continue
            parent_key = key_by_node[parent]
            child_key = key_by_node[child]
            parent_probs = dict(node_probabilities.get(parent_key, {}) or {})
            child_probs = dict(node_probabilities.get(child_key, {}) or {})
            child_result = dict(getattr(result, "node_results", {}) or {}).get(child_key)
            raw_child_payload = dict(getattr(child_result, "raw_method_payload", {}) or {}) if child_result is not None else {}
            engine_child_node_id = str(raw_child_payload.get("bgb_node_id", "") or "").strip()
            if not engine_child_node_id and getattr(child, "is_leaf", lambda: False)():
                engine_child_node_id = node_ids.get(child_key, "")

            bottom_probs = self.normalize_probabilities(
                getattr(child_result, "branch_bottom_supports", {}) if child_result is not None else {}
            )
            top_probs = self.normalize_probabilities(
                getattr(child_result, "branch_top_supports", {}) if child_result is not None else {}
            )
            if bottom_probs and top_probs:
                older_probs = bottom_probs
                younger_probs = top_probs
                interpolation_mode = "bgb_branch_endpoints"
                endpoint_branch_count += 1
            else:
                older_probs = parent_probs
                younger_probs = child_probs
                interpolation_mode = "visual_linear_interpolation"

            if not older_probs and younger_probs:
                older_probs = dict(younger_probs)
                warnings.append("Branch %s lacks an older endpoint; the younger endpoint is held constant." % index)
            if not younger_probs and older_probs:
                younger_probs = dict(older_probs)
                warnings.append("Branch %s lacks a younger endpoint; the older endpoint is held constant." % index)
            if not older_probs and not younger_probs:
                continue

            for label in list(older_probs.keys()) + list(younger_probs.keys()):
                if label not in states:
                    states.append(label)

            older_time = float(node_ages.get(parent_key, 0.0))
            younger_time = float(node_ages.get(child_key, 0.0))
            if younger_time > older_time:
                older_time, younger_time = younger_time, older_time
            branches.append(TemporalRangeBranch(
                branch_id="branch_%05d" % index,
                parent_clade_key=parent_key,
                child_clade_key=child_key,
                parent_node_id=node_ids.get(parent_key, ""),
                child_node_id=node_ids.get(child_key, ""),
                older_time=older_time,
                younger_time=younger_time,
                older_probabilities=older_probs,
                younger_probabilities=younger_probs,
                parent_node_probabilities=parent_probs,
                interpolation_mode=interpolation_mode,
                metadata={
                    "child_is_tip": bool(getattr(child, "is_leaf", lambda: False)()),
                    "branch_length": self._safe_float(getattr(child, "dist", 0.0), 0.0),
                    "engine_child_node_id": engine_child_node_id,
                },
            ))

        if not branches:
            raise ValueError("No branches with usable range probabilities were found.")

        source_kind = "bgb_endpoints" if endpoint_branch_count else "node_interpolation"
        if endpoint_branch_count:
            semantics = (
                "BioGeoBEARS branch-bottom and branch-top probabilities are model outputs. "
                "The smooth change drawn between them is a visual interpolation, not an inferred event history."
            )
            if endpoint_branch_count < len(branches):
                warnings.append(
                    "%d of %d branches lack complete BioGeoBEARS endpoints and use node interpolation."
                    % (len(branches) - endpoint_branch_count, len(branches))
                )
        else:
            semantics = (
                "Branch interiors are linearly interpolated between reconstructed node distributions. "
                "This is a visual approximation and must not be interpreted as inferred dispersal history."
            )

        state_colors = dict(getattr(result, "state_colors", {}) or {})
        state_order = list(getattr(result, "state_order", []) or [])
        for state in states:
            if state not in state_order:
                state_order.append(state)

        state_area_members, area_metadata = self._state_area_members(
            state_order,
            range_matrix=range_matrix,
            area_records=area_records,
        )
        return TemporalRangeResult(
            reference_tree=tree,
            source_model_name=source_name,
            source_kind=source_kind,
            branches=branches,
            state_order=state_order,
            state_colors=state_colors,
            state_area_members=state_area_members,
            node_ages=node_ages,
            root_age=float(root_age),
            present_time=0.0,
            semantics_note=semantics,
            warnings=self._unique(warnings),
            metadata={
                "age_mode": age_mode,
                "bgb_endpoint_branch_count": endpoint_branch_count,
                "branch_count": len(branches),
                "area_metadata": area_metadata,
                "full_state_order": list(
                    dict(getattr(result, "model_statistics", {}) or {}).get("full_state_order", []) or state_order
                ),
            },
        )

    def frame(
        self,
        timeline,
        time_value,
        selected_branch_id="",
        display_scope="all_active_lineages",
        history_mode="",
        sample_id="",
        node_boundary_mode="after_split",
    ):
        time_value = max(float(timeline.present_time), min(float(timeline.root_age), float(time_value)))
        if history_mode in ("bsm_summary", "bsm_sample") and timeline.history_segments:
            active = self._history_probabilities_at(
                timeline,
                time_value,
                sample_id=str(sample_id or "") if history_mode == "bsm_sample" else "",
                node_boundary_mode=node_boundary_mode,
            )
        else:
            active = OrderedDict()
            for branch in timeline.branches:
                if self._branch_contains_time(
                    branch,
                    time_value,
                    node_boundary_mode=node_boundary_mode,
                    root_age=timeline.root_age,
                    present_time=timeline.present_time,
                ):
                    active[branch.branch_id] = self.branch_probabilities_at(branch, time_value)

        selected_id = str(selected_branch_id or "")
        selected_probs = dict(active.get(selected_id, {}) or {})
        scope = str(display_scope or "all_active_lineages")
        if scope == "selected_lineage" and selected_id:
            area_probabilities = self.area_marginals(selected_probs, timeline.state_area_members)
        else:
            area_rows = [
                self.area_marginals(probabilities, timeline.state_area_members)
                for probabilities in active.values()
            ]
            area_probabilities = self._mean_area_probabilities(area_rows)

        return TemporalRangeFrame(
            time=time_value,
            active_branch_probabilities=dict(active),
            selected_branch_id=selected_id,
            selected_range_probabilities=selected_probs,
            area_probabilities=area_probabilities,
            active_branch_count=len(active),
            display_scope=scope,
            history_mode=str(history_mode or "endpoints"),
            node_boundary_mode=str(node_boundary_mode or "after_split"),
        )

    def _history_probabilities_at(self, timeline, time_value, sample_id="", node_boundary_mode="after_split"):
        index = timeline.metadata.get("history_segment_index", {}) or {}
        active = OrderedDict()
        for branch in timeline.branches:
            if not self._branch_contains_time(
                branch,
                time_value,
                node_boundary_mode=node_boundary_mode,
                root_age=timeline.root_age,
                present_time=timeline.present_time,
            ):
                continue
            sample_segments = dict(index.get(branch.branch_id, {}) or {})
            if sample_id:
                state = self._state_from_segments(sample_segments.get(sample_id, []), time_value)
                if state:
                    active[branch.branch_id] = {state: 1.0}
                continue
            counts = {}
            total = 0
            for current_sample_id in timeline.history_sample_ids:
                state = self._state_from_segments(sample_segments.get(current_sample_id, []), time_value)
                if not state:
                    continue
                counts[state] = counts.get(state, 0.0) + 1.0
                total += 1
            if total:
                active[branch.branch_id] = dict((state, count / float(total)) for state, count in counts.items())
        return active

    def _state_from_segments(self, segments, time_value):
        # At an event boundary, prefer the younger (post-event) segment.
        for segment in reversed(list(segments or [])):
            epsilon = max(1e-9, abs(float(segment.older_time)) * 1e-12)
            if float(segment.younger_time) - epsilon <= float(time_value) <= float(segment.older_time) + epsilon:
                return str(segment.state or "")
        return ""

    def branch_probabilities_at(self, branch, time_value, clamp=False):
        older = float(branch.older_time)
        younger = float(branch.younger_time)
        time_value = float(time_value)
        if clamp:
            time_value = max(younger, min(older, time_value))
        elif not self._branch_contains_time(branch, time_value):
            return {}
        span = older - younger
        fraction = 0.0 if span <= 0.0 else (older - time_value) / span
        fraction = max(0.0, min(1.0, fraction))
        labels = set(branch.older_probabilities) | set(branch.younger_probabilities)
        interpolated = {}
        for label in labels:
            start = float(branch.older_probabilities.get(label, 0.0) or 0.0)
            end = float(branch.younger_probabilities.get(label, 0.0) or 0.0)
            value = start + ((end - start) * fraction)
            if value > 0.0:
                interpolated[label] = value
        return self.normalize_probabilities(interpolated)

    def area_marginals(self, range_probabilities, state_area_members):
        marginals = {}
        for state, probability in dict(range_probabilities or {}).items():
            for area_code in list(state_area_members.get(state, []) or []):
                marginals[area_code] = marginals.get(area_code, 0.0) + float(probability)
        return dict((key, max(0.0, min(1.0, value))) for key, value in marginals.items())

    def normalize_probabilities(self, supports):
        values = {}
        for label, value in dict(supports or {}).items():
            text = str(label or "").strip()
            if not text:
                continue
            try:
                number = max(0.0, float(value or 0.0))
            except Exception:
                continue
            if number > 0.0:
                values[text] = number
        if not values:
            return {}
        if max(values.values()) > 1.0000001:
            values = dict((key, value / 100.0) for key, value in values.items())
        total = sum(values.values())
        if total <= 0.0:
            return {}
        return dict((key, value / total) for key, value in values.items())

    def _node_probabilities(self, result, node_by_key, leaf_state_map):
        probabilities = {}
        result_nodes = dict(getattr(result, "node_results", {}) or {})
        for clade_key, node in node_by_key.items():
            if getattr(node, "is_leaf", lambda: False)():
                state = str(leaf_state_map.get(str(getattr(node, "name", "") or ""), "") or "").strip()
                if state:
                    probabilities[clade_key] = {state: 1.0}
                continue
            node_result = result_nodes.get(clade_key)
            if node_result is None:
                continue
            supports = getattr(node_result, "branch_top_supports", {}) or getattr(node_result, "state_supports", {})
            probabilities[clade_key] = self.normalize_probabilities(supports)
        return probabilities

    def _node_ids(self, result, node_by_key, tree=None):
        ids = dict(getattr(result, "reference_node_ids", {}) or {})
        result_nodes = dict(getattr(result, "node_results", {}) or {})
        tree = tree or getattr(result, "reference_tree", None)
        if tree is not None and hasattr(tree, "get_leaf_names"):
            for index, leaf_name in enumerate(list(tree.get_leaf_names()), 1):
                ids.setdefault(str(leaf_name), str(index))
        for key, node in node_by_key.items():
            if key in ids:
                continue
            node_result = result_nodes.get(key)
            display = ""
            if node_result is not None:
                display = str(
                    getattr(node_result, "display_node_id", "")
                    or getattr(node_result, "diva_node_id", "")
                    or ""
                )
            ids[key] = display or str(getattr(node, "name", "") or "")
        return ids

    def _tree_node_maps(self, tree):
        node_by_key = {}
        key_by_node = {}
        for node in tree.traverse("preorder"):
            key = self._clade_key(node)
            node_by_key[key] = node
            key_by_node[node] = key
        return node_by_key, key_by_node

    def _clade_key(self, node):
        if getattr(node, "is_leaf", lambda: False)():
            return str(getattr(node, "name", "") or "")
        try:
            return "|".join(sorted(str(name) for name in node.get_leaf_names()))
        except Exception:
            return str(getattr(node, "name", "") or "")

    def _non_root_nodes(self, tree):
        return [node for node in tree.traverse("preorder") if getattr(node, "up", None) is not None]

    def _node_ages(self, tree, key_by_node):
        warnings = []
        root = tree.get_tree_root() if hasattr(tree, "get_tree_root") else tree
        distances = {}
        max_distance = 0.0
        for node in tree.traverse("preorder"):
            try:
                distance = float(node.get_distance(root))
            except Exception:
                distance = 0.0
                cursor = node
                while getattr(cursor, "up", None) is not None:
                    distance += self._safe_float(getattr(cursor, "dist", 0.0), 0.0)
                    cursor = cursor.up
            distances[node] = distance
            max_distance = max(max_distance, distance)

        age_mode = "branch_lengths"
        if max_distance <= 0.0:
            age_mode = "topological_pseudotime"
            depths = {root: 0.0}
            max_depth = 0.0
            for node in tree.traverse("preorder"):
                if node is root:
                    continue
                depths[node] = depths.get(getattr(node, "up", None), 0.0) + 1.0
                max_depth = max(max_depth, depths[node])
            distances = depths
            max_distance = max_depth
            warnings.append("Tree branch lengths are zero; playback uses topological pseudo-time.")

        node_ages = dict((key_by_node[node], max_distance - distance) for node, distance in distances.items())
        tip_ages = [node_ages[key_by_node[node]] for node in tree.iter_leaves()]
        tip_spread = max(tip_ages) - min(tip_ages) if tip_ages else 0.0
        ultrametric_tolerance = max(1e-8, max_distance * 1e-3)
        if tip_ages and tip_spread <= ultrametric_tolerance:
            for leaf in tree.iter_leaves():
                node_ages[key_by_node[leaf]] = 0.0
        elif tip_ages:
            warnings.append("The tree is not ultrametric; some tips do not end at time 0.")
        return node_ages, max_distance, warnings, age_mode

    def _state_area_members(self, states, range_matrix=None, area_records=None):
        matrix_codes = [str(value) for value in list(getattr(range_matrix, "state_columns", []) or []) if str(value)]
        code_to_label = dict(getattr(range_matrix, "area_code_to_label", {}) or {})
        area_rows = list(area_records or [])
        spatial_by_normalized = {}
        area_metadata = {}
        for area in area_rows:
            code = str(getattr(area, "area_code", "") or "").strip()
            name = str(getattr(area, "display_name", "") or code).strip()
            if not code:
                continue
            area_metadata[code] = name
            spatial_by_normalized[self._normalize_token(code)] = code
            spatial_by_normalized[self._normalize_token(name)] = code

        model_to_spatial = {}
        for code in matrix_codes:
            label = str(code_to_label.get(code, code) or code)
            target = spatial_by_normalized.get(self._normalize_token(label))
            if target is None:
                target = spatial_by_normalized.get(self._normalize_token(code), label)
            model_to_spatial[code] = target
            area_metadata.setdefault(target, label)

        if not matrix_codes:
            matrix_codes = list(model_to_spatial.keys())
        if not matrix_codes and area_rows:
            matrix_codes = [str(getattr(area, "area_code", "") or "") for area in area_rows]
            model_to_spatial = dict((code, code) for code in matrix_codes if code)

        members = {}
        for state in states:
            members[state] = self._resolve_state_areas(state, matrix_codes, model_to_spatial, spatial_by_normalized)
        return members, area_metadata

    def _resolve_state_areas(self, state, model_codes, model_to_spatial, spatial_by_normalized):
        text = str(state or "").strip()
        if text.lower() in self.NULL_STATES or text == "*":
            return []
        if text in model_to_spatial:
            return [model_to_spatial[text]]
        exact = spatial_by_normalized.get(self._normalize_token(text))
        if exact:
            return [exact]

        if model_codes and all(len(code) == 1 for code in model_codes):
            clean = re.sub(r"[^A-Za-z0-9]", "", text)
            if clean and all(char in model_to_spatial for char in clean):
                return self._unique([model_to_spatial[char] for char in clean])

        parts = [part.strip() for part in re.split(r"[+,;|]", text) if part.strip()]
        resolved = []
        for part in parts:
            if part in model_to_spatial:
                resolved.append(model_to_spatial[part])
                continue
            target = spatial_by_normalized.get(self._normalize_token(part))
            if target:
                resolved.append(target)
        return self._unique(resolved)

    def _mean_area_probabilities(self, rows):
        rows = [dict(row or {}) for row in rows if row]
        if not rows:
            return {}
        keys = set()
        for row in rows:
            keys.update(row.keys())
        return dict((key, sum(float(row.get(key, 0.0)) for row in rows) / float(len(rows))) for key in keys)

    def _branch_contains_time(
        self,
        branch,
        time_value,
        node_boundary_mode="closed",
        root_age=None,
        present_time=0.0,
    ):
        epsilon = max(1e-9, abs(float(branch.older_time)) * 1e-12)
        younger = float(branch.younger_time)
        older = float(branch.older_time)
        value = float(time_value)
        mode = str(node_boundary_mode or "closed")
        if mode == "after_split":
            if abs(value - float(present_time)) <= epsilon and abs(younger - float(present_time)) <= epsilon:
                return True
            return younger + epsilon < value <= older + epsilon
        if mode == "before_split":
            if root_age is not None and abs(value - float(root_age)) <= epsilon and abs(older - float(root_age)) <= epsilon:
                return True
            return younger - epsilon <= value < older - epsilon
        return younger - epsilon <= value <= older + epsilon

    def _normalize_token(self, value):
        return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())

    def _safe_float(self, value, fallback=0.0):
        try:
            number = float(value)
            return number if math.isfinite(number) else float(fallback)
        except Exception:
            return float(fallback)

    def _unique(self, values):
        output = []
        for value in values:
            if value not in output:
                output.append(value)
        return output

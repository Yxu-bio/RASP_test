from collections import defaultdict

from domain.models.temporal_range_result import TemporalRangeHistorySegment


class BSMBranchHistoryService:
    """Convert BioGeoBEARS BSM event tables into branch state segments."""

    def attach(self, timeline, bsm_result):
        if timeline is None or bsm_result is None:
            return timeline
        raw_tables = dict(getattr(bsm_result, "raw_tables", {}) or {})
        clado_rows = list(raw_tables.get("cladogenetic", []) or [])
        ana_rows = list(raw_tables.get("anagenetic", []) or [])
        if not clado_rows and not ana_rows:
            timeline.warnings.append("The loaded BSM result has no raw branch event rows for playback.")
            return timeline

        source_clades = set(
            str(value) for value in list(
                getattr(bsm_result, "source_clade_keys", [])
                or dict(getattr(bsm_result, "summary", {}) or {}).get("source_clade_keys", [])
                or []
            )
            if str(value)
        )
        timeline_clades = set(
            branch.child_clade_key for branch in timeline.branches
            if "|" in str(branch.child_clade_key or "")
        )
        if source_clades and timeline_clades:
            overlap = len(source_clades & timeline_clades)
            required = max(1, int(round(0.9 * min(len(source_clades), len(timeline_clades)))))
            if overlap < required:
                timeline.warnings.append(
                    "The loaded BSM clades do not match the current result tree; BSM history playback was disabled."
                )
                return timeline

        branch_by_engine_child_node = {}
        branch_by_display_child_node = {}
        for branch in timeline.branches:
            engine_id = str(dict(branch.metadata or {}).get("engine_child_node_id", "") or "").strip()
            display_id = str(branch.child_node_id or "").strip()
            if engine_id:
                branch_by_engine_child_node[engine_id] = branch
            if display_id:
                branch_by_display_child_node[display_id] = branch

        clado_by_sample_branch = defaultdict(list)
        ana_by_sample_branch = defaultdict(list)
        sample_ids = []
        warnings = []
        full_state_order = list(timeline.metadata.get("full_state_order", []) or timeline.state_order)
        for row in clado_rows:
            sample_id = self._sample_id(row)
            branch = self._resolve_branch(row, branch_by_engine_child_node, branch_by_display_child_node)
            if not sample_id or branch is None:
                continue
            clado_by_sample_branch[(sample_id, branch.branch_id)].append(row)
            if sample_id not in sample_ids:
                sample_ids.append(sample_id)
        for row in ana_rows:
            sample_id = self._sample_id(row)
            branch = self._resolve_branch(row, branch_by_engine_child_node, branch_by_display_child_node)
            if not sample_id or branch is None:
                continue
            ana_by_sample_branch[(sample_id, branch.branch_id)].append(row)
            if sample_id not in sample_ids:
                sample_ids.append(sample_id)

        branch_coverage = defaultdict(set)
        for sample_branch in clado_by_sample_branch.keys():
            branch_coverage[sample_branch[0]].add(sample_branch[1])
        max_coverage = max([0] + [len(values) for values in branch_coverage.values()])
        complete_sample_ids = [
            sample_id for sample_id in sample_ids
            if len(branch_coverage.get(sample_id, set())) == max_coverage and max_coverage > 0
        ]
        expected_maps = self._int(dict(getattr(bsm_result, "summary", {}) or {}).get("nummaps"), len(sample_ids))
        all_maps_loaded = bool(
            expected_maps > 0
            and len(complete_sample_ids) >= expected_maps
            and max_coverage >= len(timeline.branches)
        )
        if len(complete_sample_ids) < len(sample_ids):
            warnings.append(
                "Only %d of %d loaded BSM maps contain the maximum branch coverage; partial maps were ignored."
                % (len(complete_sample_ids), len(sample_ids))
            )
        if not all_maps_loaded:
            warnings.append(
                "The loaded BSM rows are incomplete for all-map probability summaries "
                "(expected %d maps; %d complete maps loaded). Single-map playback remains available."
                % (expected_maps, len(complete_sample_ids))
            )
        sample_ids = complete_sample_ids

        segments = []
        segment_index = defaultdict(lambda: defaultdict(list))
        for sample_id in sample_ids:
            for branch in timeline.branches:
                clado = clado_by_sample_branch.get((sample_id, branch.branch_id), [])
                events = ana_by_sample_branch.get((sample_id, branch.branch_id), [])
                branch_segments = self._segments_for_branch(
                    timeline,
                    branch,
                    sample_id,
                    clado,
                    events,
                    full_state_order,
                    warnings,
                )
                for segment in branch_segments:
                    segments.append(segment)
                    segment_index[branch.branch_id][sample_id].append(segment)

        if not segments:
            timeline.warnings.append(
                "BSM rows could not be mapped to tree branches; endpoint playback remains available."
            )
            return timeline

        timeline.history_segments = segments
        timeline.history_sample_ids = self._sorted_sample_ids(sample_ids)
        timeline.metadata["history_segment_index"] = dict(
            (branch_id, dict(samples)) for branch_id, samples in segment_index.items()
        )
        timeline.metadata["bsm_history_sample_count"] = len(timeline.history_sample_ids)
        timeline.metadata["bsm_history_segment_count"] = len(segments)
        timeline.metadata["bsm_expected_sample_count"] = expected_maps
        timeline.metadata["bsm_history_complete"] = all_maps_loaded
        timeline.metadata["bsm_summary_interactive_available"] = bool(
            all_maps_loaded and len(segments) <= 500000
        )
        if all_maps_loaded and len(segments) > 500000:
            timeline.warnings.append(
                "Full BSM histories are loaded, but interactive all-map summaries are disabled above "
                "500,000 state segments. Use a single BSM map or endpoint playback."
            )
        timeline.warnings.extend(self._unique(warnings))
        return timeline

    def _segments_for_branch(
        self,
        timeline,
        branch,
        sample_id,
        clado_rows,
        event_rows,
        full_state_order,
        warnings,
    ):
        event_rows = sorted(event_rows, key=lambda row: self._event_age(branch, row), reverse=True)
        start_state = ""
        if event_rows:
            start_state = self._clean(event_rows[0].get("current_rangetxt"))
        if not start_state:
            start_state = self._state_from_clado(clado_rows, "bottom", full_state_order)
        end_state = self._state_from_clado(clado_rows, "top", full_state_order)
        if not start_state and end_state:
            start_state = end_state
        if not start_state:
            return []

        segments = []
        cursor_age = float(branch.older_time)
        current_state = start_state
        for row in event_rows:
            event_age = max(float(branch.younger_time), min(float(branch.older_time), self._event_age(branch, row)))
            source_state = self._clean(row.get("current_rangetxt"))
            target_state = self._clean(row.get("new_rangetxt"))
            if source_state and current_state and source_state != current_state:
                warnings.append(
                    "BSM state continuity mismatch on %s sample %s: %s versus %s."
                    % (branch.branch_id, sample_id, current_state, source_state)
                )
                current_state = source_state
            if cursor_age > event_age:
                segments.append(self._segment(sample_id, branch.branch_id, cursor_age, event_age, current_state, row))
            cursor_age = event_age
            if target_state:
                current_state = target_state
        if cursor_age >= float(branch.younger_time):
            segments.append(
                self._segment(
                    sample_id,
                    branch.branch_id,
                    cursor_age,
                    float(branch.younger_time),
                    current_state or end_state,
                    {},
                )
            )
        return [segment for segment in segments if segment.state]

    def _segment(self, sample_id, branch_id, older_time, younger_time, state, raw):
        return TemporalRangeHistorySegment(
            sample_id=str(sample_id),
            branch_id=str(branch_id),
            older_time=float(older_time),
            younger_time=float(younger_time),
            state=str(state or ""),
            metadata={"event_row": dict(raw or {})},
        )

    def _event_age(self, branch, row):
        relative = self._float(row.get("event_time"), None)
        edge_length = self._float(row.get("edge.length"), None)
        if not edge_length:
            edge_length = self._float(row.get("SUBedge.length"), None)
        span = max(0.0, float(branch.older_time) - float(branch.younger_time))
        if edge_length and relative is not None:
            fraction = max(0.0, min(1.0, relative / edge_length))
            return float(branch.older_time) - (span * fraction)
        absolute = self._float(row.get("abs_event_time"), None)
        if absolute is not None:
            return absolute
        return float(branch.older_time)

    def _state_from_clado(self, rows, endpoint, state_order):
        rows = list(rows or [])
        if not rows:
            return ""
        text_fields = (
            ["sampled_states_AT_brbots_txt", "branch_bottom_state_txt"]
            if endpoint == "bottom"
            else ["sampled_states_AT_nodes_txt", "branch_top_state_txt"]
        )
        numeric_field = "sampled_states_AT_brbots" if endpoint == "bottom" else "sampled_states_AT_nodes"
        for row in rows:
            for field in text_fields:
                text = self._clean(row.get(field))
                if text:
                    return text
            index = self._int(row.get(numeric_field), None)
            if index is not None and 1 <= index <= len(state_order):
                return str(state_order[index - 1])
        return ""

    def _resolve_branch(self, row, branch_by_engine_child_node, branch_by_display_child_node):
        for field in ["nodenum_at_top_of_branch", "node", "SUBnode"]:
            value = self._clean(row.get(field))
            if value in branch_by_engine_child_node:
                return branch_by_engine_child_node[value]
        for field in ["nodenum_at_top_of_branch", "node", "SUBnode"]:
            value = self._clean(row.get(field))
            if value in branch_by_display_child_node:
                return branch_by_display_child_node[value]
        return None

    def _sample_id(self, row):
        return self._clean(row.get("sample_id") or row.get("trynum"))

    def _clean(self, value):
        text = str(value or "").strip()
        return "" if text.lower() in ("", "na", "nan", "none", "null", "<na>") else text

    def _float(self, value, fallback):
        try:
            return float(value)
        except Exception:
            return fallback

    def _int(self, value, fallback):
        try:
            return int(float(value))
        except Exception:
            return fallback

    def _sorted_sample_ids(self, values):
        def key(value):
            try:
                return 0, int(float(value))
            except Exception:
                return 1, str(value)

        return sorted(self._unique(values), key=key)

    def _unique(self, values):
        output = []
        for value in values:
            if value not in output:
                output.append(value)
        return output

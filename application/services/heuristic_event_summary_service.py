import math
from collections import defaultdict


class HeuristicEventSummaryService:
    """
    Build old-RASP-style heuristic event summaries from reconstructed node ranges.

    This is not BioGeoBEARS BSM. It uses the top ancestral range at each internal
    node and the two child start ranges to infer simple Dispersal / Vicariance /
    Extinction counts, mirroring the legacy result-view Information/Time layer.
    """

    NULL_STATES = {"", "/", "*", "NULL", "NONE", "NA", "N/A"}

    def attach(self, *, result, tree, range_matrix, method_name=""):
        if result is None or tree is None or range_matrix is None:
            return result

        area_names, tip_ranges, legacy_area_order = self._range_matrix_context(range_matrix)
        if not area_names or not tip_ranges:
            self._append_warning(result, "Heuristic event summary skipped: no usable tip ranges.")
            return result

        node_results = dict(getattr(result, "node_results", {}) or {})
        if not node_results:
            self._append_warning(result, "Heuristic event summary skipped: result has no node results.")
            return result

        clade_to_node = self._reference_nodes_by_clade(tree)
        if not clade_to_node:
            self._append_warning(result, "Heuristic event summary skipped: no internal nodes in reference tree.")
            return result

        use_legacy_diva_tie_order = str(method_name or "").strip().upper() == "DIVA"
        display_ids_by_clade = {
            clade_key: str(fallback_display_id)
            for clade_key, _node, fallback_display_id in self._iter_internal_nodes_in_display_order(tree)
        }
        node_states = {}
        for clade_key, node_result in node_results.items():
            state = self._top_state(
                node_result,
                area_names,
                legacy_area_order=legacy_area_order,
                use_legacy_diva_tie_order=use_legacy_diva_tie_order,
            )
            if state is not None:
                node_states[str(clade_key)] = state

        events = []
        skipped = 0
        for clade_key, node, fallback_display_id in self._iter_internal_nodes_in_display_order(tree):
            node_result = node_results.get(clade_key)
            if node_result is None:
                continue
            parent_state = node_states.get(clade_key)
            if parent_state is None:
                skipped += 1
                continue

            child_states = self._legacy_child_states_for_node(
                node,
                area_names=area_names,
                tip_ranges=tip_ranges,
                node_states=node_states,
                display_ids_by_clade=display_ids_by_clade,
            )

            if len(child_states) < 2:
                skipped += 1
                continue

            event = self._infer_event(
                parent_state=parent_state,
                child_states=child_states,
                node_result=node_result,
                clade_key=clade_key,
                area_names=area_names,
                display_node_id=(
                    self._display_node_id(node_result)
                    or self._result_display_node_id(result, clade_key)
                    or fallback_display_id
                ),
            )
            events.append(event)
            try:
                node_result.event_summary = (
                    "Dispersal:%s Vicariance:%s Extinction:%s"
                    % (event["dispersal"], event["vicariance"], event["extinction"])
                )
                node_result.time_summary = "node_age=%s" % self._format_number(event.get("node_age", 0.0))
            except Exception:
                pass

        if not events:
            self._append_warning(result, "Heuristic event summary skipped: no node had enough range information.")
            return result

        ages = self._node_ages(tree)
        for event in events:
            event["node_age"] = ages.get(event["clade_key"], 0.0)
            node_result = node_results.get(event["clade_key"])
            if node_result is not None:
                try:
                    node_result.time_summary = "node_age=%s" % self._format_number(event.get("node_age", 0.0))
                except Exception:
                    pass

        info_text, totals = self._build_information_text(
            events=events,
            area_names=area_names,
            method_name=str(method_name or getattr(result, "model_name", "") or type(result).__name__),
            skipped=skipped,
        )
        time_text = self._build_time_text(events, area_names=area_names)

        result.information_text = info_text
        result.time_summary_text = time_text
        result.heuristic_events = events
        result.heuristic_event_totals = totals
        result.heuristic_time_data = self._build_time_data(events, area_names)
        return result

    def _range_matrix_context(self, matrix):
        area_names = [str(x).strip() for x in list(getattr(matrix, "state_columns", []) or []) if str(x).strip()]
        rows = list(getattr(matrix, "rows", []) or [])
        tip_ranges = {}
        for row in rows:
            taxon = str(row.get("Name", "") or "").strip()
            if not taxon:
                continue
            tokens = []
            for area in area_names:
                value = str(row.get(area, "") or "").strip().lower()
                present = False
                if value in {"1", "true", "t", "yes", "y", "present"}:
                    present = True
                else:
                    try:
                        present = float(value) == 1.0
                    except Exception:
                        present = bool(value) and value not in {"0", "false", "f", "no", "n", "absent"}
                if present:
                    tokens.append(area)
            if tokens:
                tip_ranges[taxon] = {
                    "tokens": tuple(tokens),
                    "label": self._join_tokens(tokens),
                    "support": 100.0,
                }
        legacy_area_order = []
        for row in rows:
            for area in area_names:
                value = str(row.get(area, "") or "").strip().lower()
                present = False
                if value in {"1", "true", "t", "yes", "y", "present"}:
                    present = True
                else:
                    try:
                        present = float(value) == 1.0
                    except Exception:
                        present = bool(value) and value not in {"0", "false", "f", "no", "n", "absent"}
                if present and area not in legacy_area_order:
                    legacy_area_order.append(area)
        for area in area_names:
            if area not in legacy_area_order:
                legacy_area_order.append(area)
        return area_names, tip_ranges, legacy_area_order

    def _reference_nodes_by_clade(self, tree):
        out = {}
        if tree is None or not hasattr(tree, "traverse"):
            return out
        for node in tree.traverse("postorder"):
            if node.is_leaf():
                continue
            clade_key = self._clade_key(node)
            if clade_key:
                out[clade_key] = node
        return out

    def _iter_internal_nodes_in_display_order(self, tree):
        if tree is None or not hasattr(tree, "traverse"):
            return []
        out = []
        try:
            taxon_count = len(tree.get_leaf_names())
        except Exception:
            taxon_count = 0
        counter = 0
        for node in tree.traverse("postorder"):
            if node.is_leaf():
                continue
            counter += 1
            clade_key = self._clade_key(node)
            out.append((clade_key, node, str(taxon_count + counter)))
        return out

    def _clade_key(self, node):
        try:
            return "|".join(sorted(node.get_leaf_names()))
        except Exception:
            return ""

    def _state_for_tree_node(self, node, *, area_names, tip_ranges, node_states):
        if node.is_leaf():
            return tip_ranges.get(str(getattr(node, "name", "") or "").strip())
        return node_states.get(self._clade_key(node))

    def _legacy_child_states_for_node(self, node, *, area_names, tip_ranges, node_states, display_ids_by_clade=None):
        entries = []
        for child_index, child in enumerate(list(getattr(node, "children", []) or [])):
            child_state = self._state_for_tree_node(
                child,
                area_names=area_names,
                tip_ranges=tip_ranges,
                node_states=node_states,
            )
            if child_state is not None:
                if child.is_leaf():
                    sort_key = (0, child_index)
                else:
                    child_clade = self._clade_key(child)
                    try:
                        child_display_id = int(str(dict(display_ids_by_clade or {}).get(child_clade, "0") or "0"))
                    except Exception:
                        child_display_id = 0
                    sort_key = (1, -child_display_id, child_index)
                entries.append((sort_key, child_state))
            elif not child.is_leaf():
                entries.extend(
                    self._legacy_child_state_entries_for_node(
                        child,
                        area_names=area_names,
                        tip_ranges=tip_ranges,
                        node_states=node_states,
                        display_ids_by_clade=display_ids_by_clade,
                        base_sort_key=(2, child_index),
                    )
                )
        entries.sort(key=lambda item: item[0])
        return [state for _sort_key, state in entries]

    def _legacy_child_state_entries_for_node(
        self,
        node,
        *,
        area_names,
        tip_ranges,
        node_states,
        display_ids_by_clade=None,
        base_sort_key=(),
    ):
        entries = []
        for child_index, child in enumerate(list(getattr(node, "children", []) or [])):
            child_state = self._state_for_tree_node(
                child,
                area_names=area_names,
                tip_ranges=tip_ranges,
                node_states=node_states,
            )
            sort_key = tuple(base_sort_key or ()) + (child_index,)
            if child_state is not None:
                entries.append((sort_key, child_state))
            elif not child.is_leaf():
                entries.extend(
                    self._legacy_child_state_entries_for_node(
                        child,
                        area_names=area_names,
                        tip_ranges=tip_ranges,
                        node_states=node_states,
                        display_ids_by_clade=display_ids_by_clade,
                        base_sort_key=sort_key,
                    )
                )
        return entries

    def _top_state(self, node_result, area_names, legacy_area_order=None, use_legacy_diva_tie_order=False):
        states = [str(x).strip() for x in list(getattr(node_result, "states", []) or []) if str(x).strip()]
        supports = {
            str(k).strip(): float(v)
            for k, v in dict(getattr(node_result, "state_supports", {}) or {}).items()
            if str(k).strip()
        }
        if not states and supports:
            states = [k for k, _v in sorted(supports.items(), key=lambda item: (-float(item[1]), item[0]))]

        pie_labels = [str(x).strip() for x in list(getattr(node_result, "pie_labels", []) or []) if str(x).strip()]
        pie_percents = list(getattr(node_result, "pie_percents", []) or [])
        if not states and pie_labels:
            states = list(pie_labels)
            for label, percent in zip(pie_labels, pie_percents):
                try:
                    supports.setdefault(label, float(percent))
                except Exception:
                    pass

        if use_legacy_diva_tie_order and states:
            states = self._legacy_diva_states_order(states, supports, legacy_area_order or area_names, area_names)

        for index, label in enumerate(states):
            if self._is_null_state(label):
                if index == 0:
                    return None
                continue
            tokens = self._split_range_label(label, area_names)
            if tokens:
                return {
                    "tokens": tuple(tokens),
                    "label": self._join_tokens(tokens),
                    "support": float(supports.get(label, supports.get(self._join_tokens(tokens), 100.0))),
                }
        return None

    def _legacy_diva_states_order(self, states, supports, legacy_area_order, area_names):
        clean_states = [str(state).strip() for state in list(states or []) if str(state).strip()]
        if len(clean_states) <= 1:
            return clean_states
        support_values = {}
        if supports:
            support_values = {state: float(supports.get(state, 0.0)) for state in clean_states}
        else:
            equal = 100.0 / float(len(clean_states))
            support_values = {state: equal for state in clean_states}

        ordered = []
        remaining = list(clean_states)
        while remaining:
            best = max(float(support_values.get(state, 0.0)) for state in remaining)
            group = [
                state for state in remaining
                if abs(float(support_values.get(state, 0.0)) - best) < 1e-7
            ]
            ordered.extend(self._legacy_diva_tie_group_order(group, legacy_area_order, area_names))
            remaining = [state for state in remaining if state not in group]
        return ordered

    def _legacy_diva_tie_group_order(self, group, legacy_area_order, area_names):
        group = [str(state).strip() for state in list(group or []) if str(state).strip()]
        if len(group) <= 1:
            return group

        token_map = {state: self._split_range_label(state, area_names) for state in group}
        union_tokens = []
        intersection = None
        for tokens in token_map.values():
            if intersection is None:
                intersection = list(tokens)
            else:
                intersection = [token for token in intersection if token in tokens]
            for token in tokens:
                if token not in union_tokens:
                    union_tokens.append(token)
        union_state = self._join_tokens(self._canonical_tokens(union_tokens, area_names))
        order = {area: index for index, area in enumerate(list(legacy_area_order or area_names or []))}

        if len(group) >= 4 and union_state in group:
            rest = [state for state in group if state != union_state]
            return [union_state] + self._fallback_legacy_state_order(rest, token_map, order)

        if len(group) == 3 and union_state in group:
            common = list(intersection or [])
            common_rank = min([order.get(token, 10**6) for token in common] or [10**6])
            if common_rank == 0:
                rest = [state for state in group if state != union_state]
                return [union_state] + self._fallback_legacy_state_order(rest, token_map, order)
            non_union = [state for state in group if state != union_state]
            non_union = sorted(non_union, key=lambda state: self._join_tokens(token_map.get(state, [])), reverse=True)
            return non_union + [union_state]

        if len(group) == 2:
            first, second = group[0], group[1]
            first_tokens = token_map.get(first, [])
            second_tokens = token_map.get(second, [])
            if set(first_tokens).issubset(set(second_tokens)) or set(second_tokens).issubset(set(first_tokens)):
                small = first if len(first_tokens) <= len(second_tokens) else second
                large = second if small == first else first
                small_tokens = token_map.get(small, [])
                rank = min([order.get(token, 10**6) for token in small_tokens] or [10**6])
                if rank == 0:
                    return [small, large]
                return [large, small]

        return self._fallback_legacy_state_order(group, token_map, order)

    def _fallback_legacy_state_order(self, states, token_map, order):
        return sorted(
            list(states or []),
            key=lambda state: (
                -len(token_map.get(state, [])),
                [order.get(token, 10**6) for token in token_map.get(state, [])],
                str(state),
            ),
        )

    def _is_null_state(self, label):
        return str(label or "").strip().upper() in self.NULL_STATES

    def _split_range_label(self, label, area_names):
        text = str(label or "").strip()
        if self._is_null_state(text):
            return []
        text = text.replace("{", "").replace("}", "")
        text = text.replace("[", "").replace("]", "")
        text = text.replace("(", "").replace(")", "")
        text = text.replace("'", "").replace('"', "")
        for sep in [",", ";", "/", "|", "+", " "]:
            text = text.replace(sep, " ")
        parts = [x.strip() for x in text.split() if x.strip()]
        if len(parts) > 1:
            return self._canonical_tokens(parts, area_names)

        clean = parts[0] if parts else text.strip()
        if not clean:
            return []

        names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        if names and all(len(x) == 1 for x in names):
            return self._canonical_tokens(list(clean), names)

        tokens = []
        remaining = clean
        for name in sorted(names, key=lambda value: (-len(value), value)):
            while remaining.startswith(name):
                tokens.append(name)
                remaining = remaining[len(name):]
        if tokens and not remaining:
            return self._canonical_tokens(tokens, names)

        return self._canonical_tokens(list(clean), names)

    def _canonical_tokens(self, tokens, area_names):
        clean = []
        for token in tokens:
            text = str(token or "").strip()
            if text and text not in clean:
                clean.append(text)
        order = {area: idx for idx, area in enumerate(list(area_names or []))}
        clean.sort(key=lambda value: (order.get(value, 10**6), value))
        return clean

    def _join_tokens(self, tokens):
        return "".join([str(x) for x in list(tokens or [])])

    def _infer_event(self, *, parent_state, child_states, node_result, clade_key, area_names, display_node_id=""):
        parent_tokens = list(parent_state["tokens"])
        child_token_lists = [list(child["tokens"]) for child in child_states]
        child_labels = [self._join_tokens(tokens) for tokens in child_token_lists]

        child_union_unsorted = []
        for tokens in child_token_lists:
            for token in tokens:
                if token not in child_union_unsorted:
                    child_union_unsorted.append(token)
        child_union = self._canonical_tokens(child_union_unsorted, area_names)

        child_intersection = list(child_token_lists[0]) if child_token_lists else []
        for tokens in child_token_lists[1:]:
            child_intersection = [token for token in child_intersection if token in tokens]
        child_intersection = self._canonical_tokens(child_intersection, area_names)

        repeated = []
        for i, tokens in enumerate(child_token_lists):
            for token in tokens:
                for later in child_token_lists[i + 1:]:
                    if token in later:
                        repeated.append(token)

        lost_tokens = [token for token in parent_tokens if token not in child_union]
        union_with_parent = list(child_union_unsorted)
        for token in lost_tokens:
            if token not in union_with_parent:
                union_with_parent.append(token)

        child_union_in_parent = [token for token in child_union if token in parent_tokens]
        shared_parent = [token for token in child_intersection if token in parent_tokens]

        dreg_duplication = len(child_union) - len(child_union_in_parent)
        dreg_reproductive_isolation = len(repeated)
        dreg_extinction = len(lost_tokens)
        dreg_geographical_isolation = (len(child_token_lists) - 1) if not shared_parent else 0

        use_single_area_model = True
        if len(parent_tokens) > 1 or not use_single_area_model:
            dispersal = dreg_duplication
        else:
            local_extinction = 0
            parent_token = parent_tokens[0] if parent_tokens else ""
            for tokens in child_token_lists:
                if parent_token not in tokens:
                    local_extinction += 1
            dispersal = len(union_with_parent) - len(child_token_lists) * len(shared_parent) - local_extinction

        dispersal += dreg_reproductive_isolation
        vicariance = dreg_geographical_isolation
        extinction = dreg_extinction

        probability = float(parent_state.get("support", 100.0) or 0.0) / 100.0
        for child in child_states:
            probability *= float(child.get("support", 100.0) or 0.0) / 100.0

        route = self._event_route(
            parent_tokens=parent_tokens,
            child_union=child_union,
            child_labels=child_labels,
            lost_tokens=lost_tokens,
            repeated=repeated,
            dreg_duplication=dreg_duplication,
            dreg_reproductive_isolation=dreg_reproductive_isolation,
            dreg_extinction=dreg_extinction,
        )

        dispersal_routes = self._dispersal_routes(parent_tokens, child_token_lists)
        within_routes = self._within_area_speciation(child_token_lists)

        return {
            "clade_key": clade_key,
            "display_node_id": str(display_node_id or ""),
            "parent_range": self._join_tokens(parent_tokens),
            "child_ranges": child_labels,
            "dispersal": int(dispersal),
            "vicariance": int(vicariance),
            "extinction": int(extinction),
            "standard": int(dispersal + vicariance + extinction),
            "probability": probability,
            "route": route,
            "dreg_duplication": int(dreg_duplication),
            "dreg_reproductive_isolation": int(dreg_reproductive_isolation),
            "dreg_extinction": int(dreg_extinction),
            "dreg_geographical_isolation": int(dreg_geographical_isolation),
            "dispersal_routes": dispersal_routes,
            "within_routes": within_routes,
            "area_probabilities": self._area_probabilities(node_result, area_names),
            "node_age": 0.0,
        }

    def _event_route(
        self,
        *,
        parent_tokens,
        child_union,
        child_labels,
        lost_tokens,
        repeated,
        dreg_duplication,
        dreg_reproductive_isolation,
        dreg_extinction,
    ):
        parts = [self._join_tokens(parent_tokens)]
        current = [token for token in parent_tokens if token not in lost_tokens]
        if dreg_extinction > 0:
            parts.append(self._join_tokens(current))
        repeated_suffix = "".join("^" + token for token in repeated)
        if dreg_reproductive_isolation > 0:
            parts.append(self._join_tokens(current) + "".join("^" + token for token in repeated))
        if dreg_duplication > 0:
            parts.append(self._join_tokens(child_union) + repeated_suffix)
        parts.append("|".join(child_labels))
        return "->".join([part for part in parts if part != ""])

    def _dispersal_routes(self, parent_tokens, child_token_lists):
        routes = defaultdict(float)
        denominator = max(1, len(parent_tokens))
        for child_tokens in child_token_lists:
            if set(parent_tokens) == set(child_tokens):
                continue
            novel = [token for token in child_tokens if token not in parent_tokens]
            for source in parent_tokens:
                for target in novel:
                    routes["%s->%s" % (source, target)] += 1.0 / float(denominator)
        return dict(routes)

    def _within_area_speciation(self, child_token_lists):
        routes = defaultdict(float)
        for i, tokens in enumerate(child_token_lists):
            for token in tokens:
                for later in child_token_lists[i + 1:]:
                    if token in later:
                        routes[token] += 1.0
        return dict(routes)

    def _area_probabilities(self, node_result, area_names):
        area_names = [str(area).strip() for area in list(area_names or []) if str(area).strip()]
        probabilities = {area: 0.0 for area in area_names}
        states = [str(x).strip() for x in list(getattr(node_result, "states", []) or []) if str(x).strip()]
        supports = {
            str(k).strip(): float(v)
            for k, v in dict(getattr(node_result, "state_supports", {}) or {}).items()
            if str(k).strip()
        }
        if not supports:
            pie_labels = [str(x).strip() for x in list(getattr(node_result, "pie_labels", []) or []) if str(x).strip()]
            pie_percents = list(getattr(node_result, "pie_percents", []) or [])
            for label, percent in zip(pie_labels, pie_percents):
                try:
                    supports[label] = float(percent)
                except Exception:
                    pass
            if pie_labels:
                states = pie_labels
        if not supports and states:
            equal = 100.0 / float(len(states))
            supports = {state: equal for state in states}

        for state, support in supports.items():
            tokens = self._split_range_label(state, area_names)
            for token in tokens:
                if token in probabilities:
                    probabilities[token] += float(support) / 100.0
        return probabilities

    def _display_node_id(self, node_result):
        for attr in ("display_node_id", "diva_node_id"):
            value = str(getattr(node_result, attr, "") or "").strip()
            if value:
                return value
        return ""

    def _result_display_node_id(self, result, clade_key):
        key = str(clade_key or "")
        for attr in ("reference_diva_node_ids", "reference_node_ids"):
            mapping = getattr(result, attr, None)
            if not mapping:
                continue
            value = str(dict(mapping).get(key, "") or "").strip()
            if value:
                return value
        return ""

    def _node_ages(self, tree):
        if tree is None or not hasattr(tree, "traverse"):
            return {}

        distances = {}
        max_leaf_distance = 0.0

        def walk(node, distance):
            nonlocal max_leaf_distance
            distances[node] = float(distance)
            if node.is_leaf():
                max_leaf_distance = max(max_leaf_distance, float(distance))
            for child in list(getattr(node, "children", []) or []):
                walk(child, float(distance) + float(getattr(child, "dist", 0.0) or 0.0))

        walk(tree, 0.0)

        if max_leaf_distance <= 0.0:
            depths = {}
            max_leaf_depth = 0

            def walk_depth(node, depth):
                nonlocal max_leaf_depth
                depths[node] = int(depth)
                if node.is_leaf():
                    max_leaf_depth = max(max_leaf_depth, int(depth))
                for child in list(getattr(node, "children", []) or []):
                    walk_depth(child, int(depth) + 1)

            walk_depth(tree, 0)
            return {
                self._clade_key(node): float(max_leaf_depth - depths.get(node, 0))
                for node in tree.traverse("postorder")
                if not node.is_leaf()
            }

        return {
            self._clade_key(node): max(0.0, max_leaf_distance - distances.get(node, 0.0))
            for node in tree.traverse("postorder")
            if not node.is_leaf()
        }

    def _build_information_text(self, *, events, area_names, method_name, skipped):
        totals = {
            "dispersal": sum(int(event["dispersal"]) for event in events),
            "vicariance": sum(int(event["vicariance"]) for event in events),
            "extinction": sum(int(event["extinction"]) for event in events),
        }
        dispersal_routes = defaultdict(float)
        within_routes = defaultdict(float)
        for event in events:
            for key, value in dict(event.get("dispersal_routes", {}) or {}).items():
                dispersal_routes[key] += float(value)
            for key, value in dict(event.get("within_routes", {}) or {}).items():
                within_routes[key] += float(value)

        lines = [
            "%s heuristic event summary" % method_name,
            "",
            "This Information page follows the old RASP-style heuristic event layer.",
            "It uses the top reconstructed range at each node and child start ranges.",
            "It is not BioGeoBEARS BSM / stochastic mapping.",
            "",
            "Internal nodes summarized: %d" % len(events),
        ]
        if skipped:
            lines.append("Skipped nodes without enough range information: %d" % int(skipped))
        lines.append("")

        for event in sorted(events, key=lambda item: self._node_sort_key(item.get("display_node_id", ""))):
            node_id = str(event.get("display_node_id", "") or "?")
            lines.append("NODE%s:" % node_id)
            lines.append("TOP-RANGE COMPARISON:")
            lines.append(" Parent: %s" % str(event.get("parent_range", "") or "none"))
            lines.append(
                " Children: %s"
                % (" | ".join(str(value) for value in list(event.get("child_ranges", []) or [])) or "none")
            )
            lines.append("HEURISTIC EVENT COUNTS:")
            lines.append(" Dispersal:%s" % int(event["dispersal"]))
            lines.append(" Vicariance:%s" % int(event["vicariance"]))
            lines.append(" Extinction:%s" % int(event["extinction"]))
            lines.append("PRODUCT OF SELECTED-STATE SUPPORTS:")
            lines.append(" %.2f%%" % (100.0 * float(event.get("probability", 0.0))))
            lines.append("")

        lines.append("===================")
        lines.append("Heuristic area transitions (source->destination):")
        for key, value in sorted(dispersal_routes.items(), key=lambda item: (-float(item[1]), item[0])):
            lines.append("%s:%s" % (key, self._format_number(value)))

        lines.append("Within-area child overlap:")
        for key, value in sorted(within_routes.items(), key=lambda item: (-float(item[1]), item[0])):
            lines.append("%s:%s" % (key, self._format_number(value)))

        lines.append("Heuristic area summary:")
        lines.append("\tfrom\tto\twithin")
        for area in area_names:
            from_value = sum(value for key, value in dispersal_routes.items() if key.startswith(str(area) + "->"))
            to_value = sum(value for key, value in dispersal_routes.items() if key.endswith("->" + str(area)))
            within_value = within_routes.get(area, 0.0)
            lines.append(
                "%s\t%s\t%s\t%s"
                % (
                    area,
                    self._format_number(from_value),
                    self._format_number(to_value),
                    self._format_number(within_value),
                )
            )

        lines.append("===================")
        lines.append("Heuristic totals:")
        lines.append(" Dispersal: %s" % totals["dispersal"])
        lines.append(" Vicariance: %s" % totals["vicariance"])
        lines.append(" Extinction: %s" % totals["extinction"])
        return "\n".join(lines), totals

    def _build_time_text(self, events, area_names=None):
        events = list(events or [])
        root_age = max([0.0] + [float(event.get("node_age", 0.0) or 0.0) for event in events])
        lines = [
            "Old RASP-style heuristic Time summary",
            "EventLine: smoothed Dispersal / Vicariance / Extinction / Total events through time.",
            "Node density baseline is the old RASP Standard curve: one Gaussian-weighted contribution per internal node.",
            "AreaLine: smoothed per-area node probabilities through time.",
            "This is not BioGeoBEARS BSM / stochastic mapping.",
            "Dis. = Dispersal; Vic. = Vicariance; Ext. = Extinction",
            "",
            "Node event table",
            "Node\tAge\tDis.\tVic.\tExt.\tTotal\tNodeDensity",
        ]
        for event in sorted(events, key=lambda item: (-float(item.get("node_age", 0.0) or 0.0), self._node_sort_key(item.get("display_node_id", "")))):
            dispersal = int(event.get("dispersal", 0) or 0)
            vicariance = int(event.get("vicariance", 0) or 0)
            extinction = int(event.get("extinction", 0) or 0)
            lines.append(
                "%s\t%s\t%s\t%s\t%s\t%s\t%s"
                % (
                    event.get("display_node_id", "") or "?",
                    self._format_number(event.get("node_age", 0.0)),
                    dispersal,
                    vicariance,
                    extinction,
                    dispersal + vicariance + extinction,
                    int(event.get("standard", 0) or 0),
                )
            )

        if root_age <= 0.0:
            return "\n".join(lines)

        bins = 50
        unit_time = root_age / max(1.0, float(len(events)))
        if unit_time <= 0.0:
            unit_time = root_age / float(bins)
        lines.append("")
        lines.append("Smoothed EventLine table")
        lines.append("TIME\tDis.\tVic.\tExt.\tTotal\tNodeDensity")
        smoothed_rows = []
        for idx in range(bins + 1):
            time_value = root_age * float(idx) / float(bins)
            dis = vic = ext = standard = 0.0
            for event in events:
                age = float(event.get("node_age", 0.0) or 0.0)
                weight = math.exp(-((time_value - age) / unit_time) ** 2 / 2.0)
                dis += int(event.get("dispersal", 0) or 0) * weight
                vic += int(event.get("vicariance", 0) or 0) * weight
                ext += int(event.get("extinction", 0) or 0) * weight
                standard += weight
            smoothed_rows.append((time_value, dis, vic, ext, standard))
            lines.append(
                "%s\t%s\t%s\t%s\t%s\t%s"
                % (
                    self._format_number(time_value),
                    self._format_number(dis),
                    self._format_number(vic),
                    self._format_number(ext),
                    self._format_number(dis + vic + ext),
                    self._format_number(standard),
                )
            )

        area_names = [str(area).strip() for area in list(area_names or []) if str(area).strip()]
        if area_names:
            lines.append("")
            lines.append("Smoothed AreaLine table")
            lines.append("TIME\t" + "\t".join(area_names))
            for time_value, _dis, _vic, _ext, _standard in smoothed_rows:
                values = []
                for area in area_names:
                    total = 0.0
                    for event in events:
                        age = float(event.get("node_age", 0.0) or 0.0)
                        weight = math.exp(-((time_value - age) / unit_time) ** 2 / 2.0)
                        total += float(dict(event.get("area_probabilities", {}) or {}).get(area, 0.0)) * weight
                    values.append(self._format_number(total))
                lines.append("%s\t%s" % (self._format_number(time_value), "\t".join(values)))
        return "\n".join(lines)

    def _build_time_data(self, events, area_names):
        clean_events = []
        for event in list(events or []):
            clean_events.append({
                "clade_key": str(event.get("clade_key", "") or ""),
                "display_node_id": str(event.get("display_node_id", "") or ""),
                "node_age": float(event.get("node_age", 0.0) or 0.0),
                "dispersal": int(event.get("dispersal", 0) or 0),
                "vicariance": int(event.get("vicariance", 0) or 0),
                "extinction": int(event.get("extinction", 0) or 0),
                "standard": int(event.get("standard", 0) or 0),
                "area_probabilities": dict(event.get("area_probabilities", {}) or {}),
            })
        root_age = max([0.0] + [float(event.get("node_age", 0.0) or 0.0) for event in clean_events])
        return {
            "events": clean_events,
            "area_names": [str(area).strip() for area in list(area_names or []) if str(area).strip()],
            "root_age": root_age,
            "event_series": ["Dispersal", "Vicariance", "Extinction", "Total events", "Node density baseline"],
        }

    def _node_sort_key(self, value):
        text = str(value or "").strip()
        try:
            return (0, int(text))
        except Exception:
            return (1, text)

    def _format_number(self, value):
        try:
            number = float(value)
        except Exception:
            return str(value)
        if abs(number - round(number)) < 1e-9:
            return str(int(round(number)))
        return ("%.4f" % number).rstrip("0").rstrip(".")

    def _append_warning(self, result, message):
        try:
            warnings = list(getattr(result, "parse_warnings", []) or [])
            warnings.append(str(message))
            result.parse_warnings = warnings
        except Exception:
            pass

import json, re
from pathlib import Path
from typing import Dict, List, Optional

from ete3 import Tree

from domain.models.dec_result import DECResult, DECNodeResult


class DECOutputParser:
    PALETTE = [
        "#e41a1c",
        "#377eb8",
        "#4daf4a",
        "#984ea3",
        "#ff7f00",
        "#ffff33",
        "#a65628",
        "#f781bf",
        "#999999",
        "#66c2a5",
        "#fc8d62",
        "#8da0cb",
        "#e78ac3",
        "#a6d854",
        "#ffd92f",
        "#1b9e77",
        "#d95f02",
        "#7570b3",
        "#e7298a",
        "#66a61e",
    ]

    def parse(
            self,
            *,
            reference_tree,
            area_names,
            results_json_path,
            nodes_tree_path,
    ):
        payload = json.loads(Path(results_json_path).read_text(encoding="utf-8"))

        result = DECResult(reference_tree=reference_tree)
        result.model_name = "DEC"
        result.result_note = "Parsed from Lagrange-NG results.json."

        attributes = payload.get("attributes", {})
        if not isinstance(attributes, dict):
            attributes = {}

        params = payload.get("params", None)

        embedded_nodes_tree = str(attributes.get("nodes-tree", "") or "").strip()
        if embedded_nodes_tree:
            node_map = self._build_node_id_to_clade_key_from_text(embedded_nodes_tree)
        else:
            node_map = self._build_node_id_to_clade_key_from_file(nodes_tree_path)
            result.parse_warnings.append("results.json 未提供 attributes.nodes-tree，已回退到 nodes.tre 文件解析。")

        all_state_labels = []

        for entry in list(payload.get("node-results", []) or []):
            if not isinstance(entry, dict):
                continue

            node_id = str(entry.get("number", "")).strip()
            if not node_id:
                continue

            clade_key = node_map.get(node_id)
            if not clade_key:
                result.parse_warnings.append(f"DEC 节点结果 {node_id} 无法映射到内部节点。")
                continue

            state_items = self._parse_state_items(entry.get("states", []) or [], area_names)
            state_labels = [x["label"] for x in state_items]

            for label in state_labels:
                if label not in all_state_labels:
                    all_state_labels.append(label)

            pie_labels = list(state_labels)
            pie_percents = self._normalize_ratios_to_percent([x["ratio"] for x in state_items])

            splits_raw = entry.get("splits", []) or []
            event_summary, event_supports = self._parse_split_summary(
                splits_raw,
                area_names,
            )

            node_result = DECNodeResult(
                node_key=clade_key,
                display_node_id=node_id,
                states=state_labels,
                event_counts={},
                event_supports=event_supports,
                event_summary=event_summary,
                pie_labels=pie_labels,
                pie_percents=pie_percents,
                pie_colors=[],
                raw_line=json.dumps(entry, ensure_ascii=False),
            )

            result.node_results[clade_key] = node_result
            result.reference_node_ids[clade_key] = node_id

        result.state_order = list(all_state_labels)
        result.state_colors = {
            state: self.PALETTE[i % len(self.PALETTE)]
            for i, state in enumerate(result.state_order)
        }

        for node_result in result.node_results.values():
            node_result.pie_colors = [
                result.state_colors.get(label, "#808080")
                for label in node_result.pie_labels
            ]

        desc = self._format_params_summary(params)
        if desc:
            result.result_note += " params: " + desc

        return result

    def _build_node_id_to_clade_key_from_file(self, nodes_tree_path) -> Dict[str, str]:
        raw_text = Path(nodes_tree_path).read_text(encoding="utf-8").strip()
        return self._build_node_id_to_clade_key_from_text(raw_text)

    def _build_node_id_to_clade_key_from_text(self, newick_text: str) -> Dict[str, str]:
        clean_text = self._strip_nhx_annotations(newick_text)
        tree = Tree(clean_text, format=1)

        mapping = {}
        for node in tree.traverse():
            if node.is_leaf():
                continue

            node_id = str(getattr(node, "name", "") or "").strip()
            if not node_id:
                continue

            leaf_names = sorted(node.get_leaf_names())
            clade_key = "|".join(leaf_names)
            mapping[node_id] = clade_key

        return mapping

    def _parse_state_items(self, raw_states, area_names) -> List[Dict]:
        items = []

        for item in list(raw_states or []):
            label = self._state_label_from_item(item, area_names)
            ratio = self._safe_float(item.get("ratio", 0.0))
            llh = self._safe_float(item.get("llh", 0.0))

            items.append({
                "label": label,
                "ratio": ratio,
                "llh": llh,
            })

        items.sort(key=lambda x: (-x["ratio"], -x["llh"], x["label"]))
        return items

    def _state_label_from_item(self, item, area_names) -> str:
        distribution = item.get("distribution")
        if distribution is not None:
            label = self._label_from_distribution_int(distribution, area_names)
            if label:
                return label

        regions = list(item.get("regions", []) or [])
        if regions:
            return self._canonical_regions_label(regions, area_names)

        dist_str = str(item.get("distribution-string", "") or "").strip()
        if dist_str:
            return self._canonical_distribution_string(dist_str, area_names)

        return "EMPTY"

    def _parse_split_summary(self, raw_splits, area_names):
        items = []

        for split in list(raw_splits or []):
            ratio = self._safe_float(split.get("ratio", 0.0))

            anc = self._distribution_label(split.get("anc-dist"), area_names)
            left = self._distribution_label(split.get("left-dist"), area_names)
            right = self._distribution_label(split.get("right-dist"), area_names)

            label = f"{anc}: {left} | {right}"
            items.append((label, ratio))

        if not items:
            return "当前节点无 split 摘要。", {}

        items.sort(key=lambda x: -x[1])

        if max(x[1] for x in items) <= 1.000001:
            supports = {label: ratio * 100.0 for label, ratio in items}
        else:
            supports = {label: ratio for label, ratio in items}

        top_label, top_ratio = max(supports.items(), key=lambda x: x[1])
        summary = f"{top_label} ({top_ratio:.1f}%)"
        return summary, supports

    def _distribution_label(self, value, area_names) -> str:
        if not isinstance(value, dict):
            return "EMPTY"

        distribution = value.get("distribution")
        if distribution is not None:
            label = self._label_from_distribution_int(distribution, area_names)
            if label:
                return label

        dist_str = str(value.get("distribution-string", "") or "").strip()
        if dist_str:
            return self._canonical_distribution_string(dist_str, area_names)

        regions = list(value.get("regions", []) or [])
        if regions:
            return self._canonical_regions_label(regions, area_names)

        return "EMPTY"

    def _label_from_distribution_int(self, value, area_names) -> str:
        try:
            n = len(area_names)
            bits = format(int(value), "b").zfill(n)
            labels = [area_names[i] for i, ch in enumerate(bits[-n:]) if ch == "1"]
            return "".join(labels) if labels else "EMPTY"
        except Exception:
            return ""

    def _canonical_regions_label(self, regions, area_names) -> str:
        raw = [str(x).strip() for x in list(regions or []) if str(x).strip()]
        if not raw:
            return "EMPTY"

        raw_upper = {x.upper(): x for x in raw}
        ordered = []
        used = set()
        for area in list(area_names or []):
            area_text = str(area).strip()
            key = area_text.upper()
            if key in raw_upper:
                ordered.append(area_text)
                used.add(key)

        extras = sorted(x for x in raw if x.upper() not in used)
        ordered.extend(extras)
        return "".join(ordered) if ordered else "EMPTY"

    def _canonical_distribution_string(self, text, area_names) -> str:
        value = str(text or "").strip()
        if not value:
            return "EMPTY"

        tokens = [x.strip() for x in re.split(r"[\s_,;/|+]+", value) if x.strip()]
        if len(tokens) > 1:
            return self._canonical_regions_label(tokens, area_names)

        compact = value.replace("_", "").strip()
        area_names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        if not compact or not area_names:
            return compact or "EMPTY"

        if all(len(area) == 1 for area in area_names):
            return self._canonical_regions_label(list(compact), area_names)

        remaining = compact
        parsed = []
        for area in sorted(area_names, key=len, reverse=True):
            if area and area in remaining:
                parsed.append(area)
                remaining = remaining.replace(area, "", 1)
        if parsed and not remaining:
            return self._canonical_regions_label(parsed, area_names)

        return value

    def _normalize_ratios_to_percent(self, values: List[float]) -> List[float]:
        if not values:
            return []

        if max(values) <= 1.000001:
            percents = [float(v) * 100.0 for v in values]
        else:
            percents = [float(v) for v in values]

        total = sum(percents)
        if total <= 0:
            n = len(percents)
            return [100.0 / n] * n

        norm = [x * 100.0 / total for x in percents]
        norm[-1] += 100.0 - sum(norm)
        return norm

    def _safe_float(self, value, default=0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    def _strip_nhx_annotations(self, newick_text: str) -> str:
        """
        把 Lagrange-NG nodes.tre 里形如 [&&NHX:...] 的注释去掉，只保留内部节点编号和树结构。
        """
        return re.sub(r"\[&&NHX:[^\]]*\]", "", newick_text)

    def _format_params_summary(self, params) -> str:
        if not params:
            return ""

        desc = []

        if isinstance(params, dict):
            for k, v in params.items():
                desc.append(f"{k}={v}")

        elif isinstance(params, list):
            for item in params:
                if isinstance(item, dict):
                    for k, v in item.items():
                        desc.append(f"{k}={v}")
                else:
                    desc.append(str(item))

        else:
            desc.append(str(params))

        return ", ".join(desc)

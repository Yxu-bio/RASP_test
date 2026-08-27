from collections import Counter


class CladeNodeIdentityService:
    """Build and audit the clade identities shared by analysis and display code."""

    SEPARATOR = "|"

    @classmethod
    def normalize_taxon_name(cls, value):
        return str(value or "").strip()

    @classmethod
    def canonical_clade_key(cls, taxon_names):
        names = [
            cls.normalize_taxon_name(name)
            for name in list(taxon_names or [])
            if cls.normalize_taxon_name(name)
        ]
        return cls.SEPARATOR.join(sorted(names))

    @classmethod
    def node_clade_key(cls, node):
        if node is None:
            return ""
        if hasattr(node, "get_leaf_names"):
            return cls.canonical_clade_key(node.get_leaf_names())
        if hasattr(node, "iter_leaves"):
            return cls.canonical_clade_key(
                getattr(leaf, "name", "") for leaf in node.iter_leaves()
            )
        return ""

    @classmethod
    def build_reference_node_records(cls, tree):
        if tree is None or not hasattr(tree, "traverse"):
            return []

        taxon_count = len(list(tree.get_leaf_names()))
        records = []
        counter = 0
        for node in tree.traverse("postorder"):
            if node.is_leaf():
                continue
            counter += 1
            tip_names = sorted(
                cls.normalize_taxon_name(name)
                for name in node.get_leaf_names()
            )
            records.append(
                {
                    "clade_key": cls.canonical_clade_key(tip_names),
                    "display_node_id": str(taxon_count + counter),
                    "tip_names": tip_names,
                    "tip_count": len(tip_names),
                }
            )
        return records

    @classmethod
    def build_reference_node_id_map(cls, tree):
        return {
            record["clade_key"]: record["display_node_id"]
            for record in cls.build_reference_node_records(tree)
        }

    @classmethod
    def audit_tree(cls, reference_tree, candidate_tree, tree_index=None):
        reference_profile = cls._tree_profile(reference_tree)
        candidate_profile = cls._tree_profile(candidate_tree)
        reference_clades = Counter(reference_profile["internal_clade_keys"])
        candidate_clades = Counter(candidate_profile["internal_clade_keys"])

        missing_taxa = sorted(
            set(reference_profile["taxa"]) - set(candidate_profile["taxa"])
        )
        extra_taxa = sorted(
            set(candidate_profile["taxa"]) - set(reference_profile["taxa"])
        )
        matched_clades = sorted((reference_clades & candidate_clades).elements())
        missing_reference_clades = sorted(
            (reference_clades - candidate_clades).elements()
        )
        extra_candidate_clades = sorted(
            (candidate_clades - reference_clades).elements()
        )

        taxon_identity_is_valid = (
            not missing_taxa
            and not extra_taxa
            and not candidate_profile["duplicate_taxa"]
            and not candidate_profile["empty_taxon_count"]
            and not candidate_profile["separator_taxa"]
            and not candidate_profile["duplicate_clade_keys"]
        )
        return {
            "tree_index": tree_index,
            "taxon_set_matches": not missing_taxa and not extra_taxa,
            "missing_taxa": missing_taxa,
            "extra_taxa": extra_taxa,
            "duplicate_taxa": list(candidate_profile["duplicate_taxa"]),
            "empty_taxon_count": int(candidate_profile["empty_taxon_count"]),
            "separator_taxa": list(candidate_profile["separator_taxa"]),
            "reference_duplicate_clade_keys": list(
                reference_profile["duplicate_clade_keys"]
            ),
            "internal_node_count": int(candidate_profile["internal_node_count"]),
            "matched_reference_clade_count": len(matched_clades),
            "missing_reference_clade_count": len(missing_reference_clades),
            "extra_candidate_clade_count": len(extra_candidate_clades),
            "matched_reference_clades": matched_clades,
            "missing_reference_clades": missing_reference_clades,
            "extra_candidate_clades": extra_candidate_clades,
            "duplicate_clade_keys": list(candidate_profile["duplicate_clade_keys"]),
            "taxon_identity_is_valid": taxon_identity_is_valid,
            "topology_matches_reference": (
                taxon_identity_is_valid
                and not missing_reference_clades
                and not extra_candidate_clades
                and not reference_profile["duplicate_clade_keys"]
            ),
        }

    @classmethod
    def audit_tree_collection(cls, reference_tree, candidate_trees):
        reference_records = cls.build_reference_node_records(reference_tree)
        reference_profile = cls._tree_profile(reference_tree)
        reference_keys = [record["clade_key"] for record in reference_records]
        support_by_clade = dict((key, 0) for key in reference_keys)
        tree_reports = []

        for tree_index, tree in enumerate(list(candidate_trees or []), 1):
            report = cls.audit_tree(reference_tree, tree, tree_index=tree_index)
            report["included_in_effective_count"] = bool(
                report["taxon_identity_is_valid"]
            )
            tree_reports.append(report)
            if not report["included_in_effective_count"]:
                continue
            for clade_key in report["matched_reference_clades"]:
                support_by_clade[clade_key] += 1

        input_tree_count = len(tree_reports)
        effective_tree_count = sum(
            1 for report in tree_reports if report["included_in_effective_count"]
        )
        node_support = []
        for record in reference_records:
            clade_key = record["clade_key"]
            supporting = int(support_by_clade.get(clade_key, 0))
            node_support.append(
                {
                    "clade_key": clade_key,
                    "display_node_id": record["display_node_id"],
                    "tip_count": record["tip_count"],
                    "supporting_tree_count": supporting,
                    "unmatched_tree_count": effective_tree_count - supporting,
                }
            )

        return {
            "tree_count": input_tree_count,
            "input_tree_count": input_tree_count,
            "effective_tree_count": effective_tree_count,
            "failed_tree_count": input_tree_count - effective_tree_count,
            "reference_leaf_count": len(list(reference_tree.get_leaf_names())),
            "reference_internal_node_count": len(reference_records),
            "reference_duplicate_taxa": list(reference_profile["duplicate_taxa"]),
            "reference_empty_taxon_count": int(reference_profile["empty_taxon_count"]),
            "reference_separator_taxa": list(reference_profile["separator_taxa"]),
            "reference_duplicate_clade_keys": list(
                reference_profile["duplicate_clade_keys"]
            ),
            "valid_taxon_identity_tree_count": effective_tree_count,
            "topology_match_tree_count": sum(
                1
                for report in tree_reports
                if report["topology_matches_reference"]
            ),
            "taxon_mismatch_tree_count": sum(
                1 for report in tree_reports if not report["taxon_set_matches"]
            ),
            "unmatched_clade_observation_count": sum(
                report["missing_reference_clade_count"]
                for report in tree_reports
                if report["included_in_effective_count"]
            ),
            "extra_clade_observation_count": sum(
                report["extra_candidate_clade_count"]
                for report in tree_reports
                if report["included_in_effective_count"]
            ),
            "node_support": node_support,
            "trees": tree_reports,
        }

    @classmethod
    def audit_result_nodes(cls, reference_tree, nodes, method_name=""):
        reference_records = cls.build_reference_node_records(reference_tree)
        reference_key_counts = Counter(
            row["clade_key"] for row in reference_records if row["clade_key"]
        )
        duplicate_reference_keys = sorted(
            key for key, count in reference_key_counts.items() if count > 1
        )
        reference_map = dict(
            (row["clade_key"], row["display_node_id"])
            for row in reference_records
        )
        normalized_nodes = cls._normalize_result_nodes(nodes)
        empty_clade_count = sum(1 for node in normalized_nodes if not node["clade_key"])
        actual_keys = [node["clade_key"] for node in normalized_nodes if node["clade_key"]]
        actual_key_counts = Counter(actual_keys)
        actual_key_set = set(actual_keys)
        reference_key_set = set(reference_map.keys())

        display_mismatches = []
        for node in normalized_nodes:
            clade_key = node["clade_key"]
            if clade_key not in reference_map:
                continue
            expected = str(reference_map[clade_key])
            actual = str(node["display_node_id"] or "")
            if actual != expected:
                display_mismatches.append(
                    {
                        "clade_key": clade_key,
                        "expected_display_node_id": expected,
                        "actual_display_node_id": actual,
                    }
                )

        display_ids = [
            str(node["display_node_id"])
            for node in normalized_nodes
            if str(node["display_node_id"] or "")
        ]
        display_counts = Counter(display_ids)
        duplicate_keys = sorted(
            key for key, count in actual_key_counts.items() if count > 1
        )
        duplicate_display_ids = sorted(
            key for key, count in display_counts.items() if count > 1
        )
        missing_keys = sorted(reference_key_set - actual_key_set)
        unexpected_keys = sorted(actual_key_set - reference_key_set)

        return {
            "method_name": str(method_name or ""),
            "reference_node_count": len(reference_records),
            "result_node_count": len(normalized_nodes),
            "empty_result_clade_count": empty_clade_count,
            "duplicate_reference_clade_keys": duplicate_reference_keys,
            "missing_reference_clades": missing_keys,
            "unexpected_result_clades": unexpected_keys,
            "duplicate_result_clade_keys": duplicate_keys,
            "duplicate_display_node_ids": duplicate_display_ids,
            "display_node_id_mismatches": display_mismatches,
            "identity_matches_reference": not (
                missing_keys
                or unexpected_keys
                or duplicate_keys
                or duplicate_display_ids
                or display_mismatches
                or empty_clade_count
                or duplicate_reference_keys
                or len(normalized_nodes) != len(reference_records)
            ),
        }

    @classmethod
    def audit_supporting_tree_counts(cls, collection_report, nodes, method_name=""):
        expected = {
            row["clade_key"]: int(row["supporting_tree_count"])
            for row in list(collection_report.get("node_support", []) or [])
        }
        normalized_nodes = cls._normalize_result_nodes(nodes)
        nodes_by_clade = dict(
            (node["clade_key"], node)
            for node in normalized_nodes
            if node["clade_key"]
        )
        missing_counts = []
        mismatches = []
        exceeds_topology = []
        for clade_key in sorted(expected):
            node = nodes_by_clade.get(clade_key)
            if node is None or node.get("supporting_tree_count", None) is None:
                missing_counts.append(clade_key)
                continue
            actual = int(node["supporting_tree_count"])
            if actual > expected[clade_key]:
                exceeds_topology.append(
                    {
                        "clade_key": clade_key,
                        "display_node_id": node["display_node_id"],
                        "topology_presence_count": expected[clade_key],
                        "actual_supporting_tree_count": actual,
                    }
                )
            if actual != expected[clade_key]:
                mismatches.append(
                    {
                        "clade_key": clade_key,
                        "display_node_id": node["display_node_id"],
                        "expected_supporting_tree_count": expected[clade_key],
                        "actual_supporting_tree_count": actual,
                    }
                )
        return {
            "method_name": str(method_name or ""),
            "checked_node_count": len(expected) - len(missing_counts),
            "expected_node_count": len(expected),
            "missing_supporting_tree_count_clades": missing_counts,
            "exceeds_topology_presence": exceeds_topology,
            "mismatches": mismatches,
            "supporting_tree_counts_are_complete": not missing_counts,
            "topology_presence_is_upper_bound": (
                not missing_counts and not exceeds_topology
            ),
            "supporting_tree_counts_match_topology": (
                not missing_counts and not mismatches
            ),
        }

    @classmethod
    def _tree_profile(cls, tree):
        if tree is None or not hasattr(tree, "traverse"):
            return {
                "taxa": [],
                "duplicate_taxa": [],
                "empty_taxon_count": 0,
                "separator_taxa": [],
                "internal_node_count": 0,
                "internal_clade_keys": [],
                "duplicate_clade_keys": [],
            }

        raw_taxa = [getattr(leaf, "name", "") for leaf in tree.iter_leaves()]
        taxa = [cls.normalize_taxon_name(name) for name in raw_taxa]
        taxon_counts = Counter(name for name in taxa if name)
        clade_keys = [
            cls.node_clade_key(node)
            for node in tree.traverse("postorder")
            if not node.is_leaf()
        ]
        clade_counts = Counter(key for key in clade_keys if key)
        return {
            "taxa": sorted(name for name in taxa if name),
            "duplicate_taxa": sorted(
                name for name, count in taxon_counts.items() if count > 1
            ),
            "empty_taxon_count": sum(1 for name in taxa if not name),
            "separator_taxa": sorted(
                name for name in taxa if cls.SEPARATOR in name
            ),
            "internal_node_count": len(clade_keys),
            "internal_clade_keys": clade_keys,
            "duplicate_clade_keys": sorted(
                key for key, count in clade_counts.items() if count > 1
            ),
        }

    @classmethod
    def _normalize_result_nodes(cls, nodes):
        normalized = []
        if isinstance(nodes, dict):
            iterable = list(nodes.items())
        else:
            iterable = [(None, node) for node in list(nodes or [])]

        for fallback_key, node in iterable:
            if isinstance(node, dict):
                clade_key = str(
                    node.get("clade_key", "")
                    or node.get("node_key", "")
                    or fallback_key
                    or ""
                ).strip()
                display_node_id = str(
                    node.get("display_node_id", "")
                    or node.get("diva_node_id", "")
                    or ""
                ).strip()
                supporting = node.get("supporting_tree_count", None)
            else:
                clade_key = str(
                    getattr(node, "node_key", "")
                    or getattr(node, "clade_key", "")
                    or fallback_key
                    or ""
                ).strip()
                display_node_id = str(
                    getattr(node, "display_node_id", "")
                    or getattr(node, "diva_node_id", "")
                    or ""
                ).strip()
                supporting = getattr(node, "supporting_tree_count", None)
            normalized.append(
                {
                    "clade_key": clade_key,
                    "display_node_id": display_node_id,
                    "supporting_tree_count": supporting,
                }
            )
        return normalized

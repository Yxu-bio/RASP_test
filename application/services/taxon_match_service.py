import re


class TaxonMatchService:
    MATCH_EXACT = "exact"
    MATCH_NORMALIZED_PREFIX = "normalized_prefix"
    MATCHED_STATUSES = ("exact", "normalized", "prefix")

    def match(self, tree_taxa, matrix_taxa, mode=MATCH_NORMALIZED_PREFIX):
        tree_names = self.unique_names(tree_taxa)
        matrix_names = self.unique_names(matrix_taxa)
        rows = self.build_mapping_rows(
            source_taxa=tree_names,
            target_taxa=matrix_names,
            source_type="tree",
            target_type="matrix",
            mode=mode,
        )
        matched_rows = [row for row in rows if row["match_status"] in self.MATCHED_STATUSES]
        ambiguous_rows = [row for row in rows if row["match_status"] == "ambiguous"]
        unmatched_rows = [row for row in rows if row["match_status"] == "unmatched"]
        matched_targets = set(row["matched_taxon"] for row in matched_rows if row["matched_taxon"])
        only_in_matrix = [name for name in matrix_names if name not in matched_targets]
        status_counts = self.count_statuses(rows)

        return {
            "mode": mode,
            "matched": [row["source_taxon"] for row in matched_rows],
            "only_in_tree": [row["source_taxon"] for row in unmatched_rows + ambiguous_rows],
            "only_in_matrix": only_in_matrix,
            "ambiguous": ambiguous_rows,
            "unmatched": unmatched_rows,
            "mapping_rows": rows,
            "matched_count": len(matched_rows),
            "only_in_tree_count": len(unmatched_rows) + len(ambiguous_rows),
            "only_in_matrix_count": len(only_in_matrix),
            "exact_count": status_counts.get("exact", 0),
            "normalized_count": status_counts.get("normalized", 0),
            "prefix_count": status_counts.get("prefix", 0),
            "ambiguous_count": status_counts.get("ambiguous", 0),
            "unmatched_count": status_counts.get("unmatched", 0),
        }

    def build_mapping_rows(self, source_taxa, target_taxa, source_type="source", target_type="target", mode=MATCH_NORMALIZED_PREFIX):
        targets = self.unique_names(target_taxa)
        rows = []
        for source_name in self.unique_names(source_taxa):
            match = self.match_name_to_candidates(source_name, targets, mode=mode)
            rows.append({
                "source_type": source_type,
                "source_taxon": source_name,
                "target_type": target_type,
                "matched_taxon": match["matched_name"],
                "match_status": match["status"],
                "match_rule": match["rule"],
                "candidates": ";".join(match["candidates"]),
            })
        return rows

    def match_name_to_candidates(self, source_name, candidate_names, mode=MATCH_NORMALIZED_PREFIX):
        source = str(source_name or "").strip()
        candidates = self.unique_names(candidate_names)
        if not source:
            return self._match_result("", "unmatched", "empty source name", [])
        if not candidates:
            return self._match_result("", "no_target", "no target taxa", [])

        exact = [name for name in candidates if name == source]
        if len(exact) == 1:
            return self._match_result(exact[0], "exact", "exact string match", exact)
        if len(exact) > 1:
            return self._match_result("", "ambiguous", "multiple exact target names", exact)
        if mode == self.MATCH_EXACT:
            return self._match_result("", "unmatched", "no exact string match", [])

        source_key = self.normalize_taxon_key(source)
        if not source_key:
            return self._match_result("", "unmatched", "empty normalized source name", [])

        keyed = []
        for name in candidates:
            key = self.normalize_taxon_key(name)
            if key:
                keyed.append((name, key))

        normalized = [name for name, key in keyed if key == source_key]
        if len(normalized) == 1:
            return self._match_result(normalized[0], "normalized", "normalized string match", normalized)
        if len(normalized) > 1:
            return self._match_result("", "ambiguous", "multiple normalized target names", normalized)

        prefix_matches = []
        for name, key in keyed:
            if source_key.startswith(key + "_") or key.startswith(source_key + "_"):
                prefix_matches.append((name, key))
        if prefix_matches:
            max_len = max(len(key) for _name, key in prefix_matches)
            longest = sorted(set(name for name, key in prefix_matches if len(key) == max_len))
            if len(longest) == 1:
                return self._match_result(longest[0], "prefix", "unique longest normalized prefix", longest)
            return self._match_result("", "ambiguous", "multiple longest normalized prefixes", longest)

        return self._match_result("", "unmatched", "no normalized or unique-prefix match", [])

    def count_statuses(self, rows):
        counts = {}
        for row in list(rows or []):
            status = str(row.get("match_status", "") or "")
            counts[status] = counts.get(status, 0) + 1
        return counts

    def unique_names(self, values):
        names = []
        seen = set()
        for value in list(values or []):
            name = str(value or "").strip()
            if not name or name in seen:
                continue
            names.append(name)
            seen.add(name)
        return names

    def normalize_taxon_key(self, value):
        text = str(value or "").strip().lower()
        text = re.sub(r"[^0-9a-z]+", "_", text)
        text = re.sub(r"_+", "_", text)
        return text.strip("_")

    def _match_result(self, matched_name, status, rule, candidates):
        return {
            "matched_name": str(matched_name or ""),
            "status": str(status or ""),
            "rule": str(rule or ""),
            "candidates": self.unique_names(candidates),
        }

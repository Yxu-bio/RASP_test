class TaxonMatchService:
    def match(self, tree_taxa, matrix_taxa):
        tree_set = set(tree_taxa)
        matrix_set = set(matrix_taxa)

        matched = sorted(tree_set & matrix_set)
        only_in_tree = sorted(tree_set - matrix_set)
        only_in_matrix = sorted(matrix_set - tree_set)

        return {
            "matched": matched,
            "only_in_tree": only_in_tree,
            "only_in_matrix": only_in_matrix,
            "matched_count": len(matched),
            "only_in_tree_count": len(only_in_tree),
            "only_in_matrix_count": len(only_in_matrix),
        }

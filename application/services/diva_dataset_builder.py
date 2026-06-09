from domain.models.diva_dataset import DivaDataset

class DivaDatasetBuilder:
    MAX_AREAS = 15

    def build(self, tree, matrix, tree_name="t1", distribution_name="d1") -> DivaDataset:
        if tree is None:
            raise ValueError("DIVA 构建失败：tree 为空")
        if matrix is None:
            raise ValueError("DIVA 构建失败：matrix 为空")

        # 校验树是否为 fully bifurcate
        self._validate_binary_tree(tree)

        # 自动识别状态列，除 ID/Name 外的所有列
        area_columns = [c for c in matrix.state_columns if c not in ("ID", "Name")]
        if not area_columns:
            raise ValueError("DIVA 构建失败：矩阵中没有状态列")
        if len(area_columns) > self.MAX_AREAS:
            raise ValueError(
                f"DIVA 最多支持 {self.MAX_AREAS} 个 area，但当前矩阵有 {len(area_columns)} 列状态列"
            )

        # 构建矩阵查找表
        matrix_by_name = self._build_matrix_lookup(matrix)

        # 获取树叶顺序
        taxa_order = self._extract_leaf_order(tree)

        # 校验树叶和矩阵 Name 一致
        self._validate_taxon_consistency(taxa_order, matrix_by_name)

        # 生成 taxon 编号映射
        name_to_index = {taxon_name: i for i, taxon_name in enumerate(taxa_order, start=1)}
        index_to_name = {v: k for k, v in name_to_index.items()}

        # 生成数字化 Newick
        numeric_newick = self._build_numeric_newick(tree, name_to_index) + ";"

        # 构建 distribution 列表
        distributions = []
        for taxon_name in taxa_order:
            row = matrix_by_name[taxon_name]
            dist = self._row_to_distribution(row, area_columns)
            distributions.append(dist)

        return DivaDataset(
            tree_name=self._sanitize_label(tree_name, "t1"),
            distribution_name=self._sanitize_label(distribution_name, "d1"),
            taxa_order=taxa_order,
            name_to_index=name_to_index,
            index_to_name=index_to_name,
            numeric_newick=numeric_newick,
            distributions=distributions,
            area_column_to_letter=None,
            source_matrix_path=getattr(matrix, "source_path", "") or "",
        )

    # ---------------- 内部方法 ----------------
    def _sanitize_label(self, value: str, fallback: str) -> str:
        value = (value or fallback).strip()
        if not value:
            value = fallback
        return value[:16]

    def _validate_binary_tree(self, tree) -> None:
        for node in tree.traverse():
            if node.is_leaf():
                continue
            child_count = len(node.children)
            if child_count != 2:
                raise ValueError(
                    f"DIVA 要求 fully bifurcate tree，但节点 {getattr(node, 'name', '<内部节点>')} "
                    f"有 {child_count} 个子节点"
                )

    def _build_matrix_lookup(self, matrix) -> dict:
        lookup = {}
        for row in matrix.rows:
            name = str(row["Name"]).strip()
            if not name:
                raise ValueError("矩阵中存在空的 Name")
            if name in lookup:
                raise ValueError(f"矩阵中存在重复 taxon 名称: {name}")
            lookup[name] = row
        return lookup

    def _extract_leaf_order(self, tree) -> list:
        return [leaf.name for leaf in tree.iter_leaves()]

    def _validate_taxon_consistency(self, taxa_order: list, matrix_by_name: dict) -> None:
        tree_set = set(taxa_order)
        matrix_set = set(matrix_by_name.keys())

        only_in_tree = sorted(tree_set - matrix_set)
        only_in_matrix = sorted(matrix_set - tree_set)

        if only_in_tree or only_in_matrix:
            lines = ["树与矩阵 taxon 不一致，无法生成 DIVA 输入文件。"]
            if only_in_tree:
                lines.append(f"只在树中: {only_in_tree}")
            if only_in_matrix:
                lines.append(f"只在矩阵中: {only_in_matrix}")
            raise ValueError("\n".join(lines))

    def _row_to_distribution(self, row, area_columns) -> str:
        """
        将矩阵行压成 DIVA area-set 字符串
        支持 CSV 已经用字符表示区域（例如 A / BD / C）
        """
        dist_list = []
        for col in area_columns:
            val = str(row[col]).strip()
            if val:  # 非空直接加入
                dist_list.append(val)
        return "".join(dist_list)

    def _build_numeric_newick(self, tree, name_to_index):
        """
        将 ete3 树对象转换成数字化 Newick 字符串，
        所有叶子用 1..n 编号，内部节点保持括号结构
        """
        def recurse(node):
            if node.is_leaf():
                return str(name_to_index[node.name])
            else:
                return "(" + ",".join([recurse(c) for c in node.children]) + ")"
        return recurse(tree)
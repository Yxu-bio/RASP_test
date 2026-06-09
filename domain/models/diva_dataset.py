from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class DivaDataset:
    tree_name: str
    distribution_name: str

    taxa_order: List[str]                 # 数字树中的叶子顺序，对应 1..n
    name_to_index: Dict[str, int]        # 真实 taxon 名 -> 1-based index
    index_to_name: Dict[int, str]        # 1-based index -> 真实 taxon 名

    numeric_newick: str                  # 例如 ((1,2),(3,4));
    distributions: List[str]             # 例如 ["A", "AB", "C", "D"]

    area_column_to_letter: Dict[str, str] = field(default_factory=dict)
    source_matrix_path: str = ""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SDivaNodeResult:
    node_key: str
    supporting_tree_count: int
    total_tree_count: int

    states: List[str] = field(default_factory=list)
    state_counts: Dict[str, float] = field(default_factory=dict)
    state_supports: Dict[str, float] = field(default_factory=dict)

    pie_labels: List[str] = field(default_factory=list)
    pie_percents: List[float] = field(default_factory=list)
    pie_colors: List[str] = field(default_factory=list)

    @property
    def display_text(self) -> str:
        if not self.states:
            return "无"
        parts = []
        for state in self.states:
            percent = self.state_supports.get(state, 0.0)
            parts.append(f"{state}({percent:.1f}%)")
        return " ".join(parts)

    @property
    def ambiguity_count(self) -> int:
        return len(self.states)


@dataclass
class SDivaResult:
    reference_tree: object
    tree_count_total: int

    node_results: Dict[str, SDivaNodeResult] = field(default_factory=dict)
    parse_warnings: List[str] = field(default_factory=list)
    config: Optional[object] = None
    config_text: str = ""
    config_path: str = ""

    state_order: List[str] = field(default_factory=list)
    state_colors: Dict[str, str] = field(default_factory=dict)

    # clade_key -> 参考树单独跑 DIVA 后得到的原生 diva_node_id
    reference_diva_node_ids: Dict[str, int] = field(default_factory=dict)

    def get_node_result(self, node_key: str) -> Optional[SDivaNodeResult]:
        if not node_key:
            return None
        return self.node_results.get(node_key)

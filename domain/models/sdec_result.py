from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SDECNodeResult:
    node_key: str
    display_node_id: str = ""

    states: List[str] = field(default_factory=list)

    supporting_tree_count: int = 0
    total_tree_count: int = 0

    # 累加后的原始权重（按每棵树内部归一化后的 state 权重求和）
    state_weights: Dict[str, float] = field(default_factory=dict)

    # 对 supporting_tree_count 归一化后的百分比
    state_supports: Dict[str, float] = field(default_factory=dict)

    pie_labels: List[str] = field(default_factory=list)
    pie_percents: List[float] = field(default_factory=list)
    pie_colors: List[str] = field(default_factory=list)

    event_summary: str = ""
    raw_method_payload: Dict = field(default_factory=dict)

    @property
    def display_text(self) -> str:
        if self.states:
            return " ".join(self.states)
        return "无"

    @property
    def ambiguity_count(self) -> int:
        return len(self.states)


@dataclass
class SDECResult:
    reference_tree: object

    node_results: Dict[str, SDECNodeResult] = field(default_factory=dict)
    parse_warnings: List[str] = field(default_factory=list)

    state_order: List[str] = field(default_factory=list)
    state_colors: Dict[str, str] = field(default_factory=dict)

    reference_node_ids: Dict[str, str] = field(default_factory=dict)

    model_name: str = "S-DEC"
    result_note: str = ""

    input_tree_count: int = 0
    effective_tree_count: int = 0

    def get_node_result(self, node_key: str) -> Optional[SDECNodeResult]:
        if not node_key:
            return None
        return self.node_results.get(node_key)
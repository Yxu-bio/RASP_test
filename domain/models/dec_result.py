from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DECNodeResult:
    node_key: str
    display_node_id: str = ""
    states: List[str] = field(default_factory=list)

    # 事件相关：窄版 DEC 先只保留文本和简单统计
    event_counts: Dict[str, float] = field(default_factory=dict)
    event_supports: Dict[str, float] = field(default_factory=dict)
    event_summary: str = ""

    # 可选饼图数据，便于沿用当前 renderer / legend 机制
    pie_labels: List[str] = field(default_factory=list)
    pie_percents: List[float] = field(default_factory=list)
    pie_colors: List[str] = field(default_factory=list)

    raw_line: str = ""

    @property
    def display_text(self) -> str:
        if self.states:
            return " ".join(self.states)
        return "无"

    @property
    def ambiguity_count(self) -> int:
        return len(self.states)


@dataclass
class DECResult:
    reference_tree: object

    node_results: Dict[str, DECNodeResult] = field(default_factory=dict)
    parse_warnings: List[str] = field(default_factory=list)

    state_order: List[str] = field(default_factory=list)
    state_colors: Dict[str, str] = field(default_factory=dict)

    # 节点显示号，仍然保持 clade_key -> display_node_id 的映射思路
    reference_node_ids: Dict[str, str] = field(default_factory=dict)

    # 方法级说明，窄版先保留
    model_name: str = "DEC"
    result_note: str = ""

    def get_node_result(self, node_key: str) -> Optional[DECNodeResult]:
        if not node_key:
            return None
        return self.node_results.get(node_key)

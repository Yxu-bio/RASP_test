from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BioGeoBEARSNodeResult:
    node_key: str
    display_node_id: str = ""

    states: List[str] = field(default_factory=list)
    state_supports: Dict[str, float] = field(default_factory=dict)

    pie_labels: List[str] = field(default_factory=list)
    pie_percents: List[float] = field(default_factory=list)
    pie_colors: List[str] = field(default_factory=list)

    supporting_tree_count: int = 1
    total_tree_count: int = 1

    event_summary: str = ""
    raw_method_payload: Dict = field(default_factory=dict)


@dataclass
class BioGeoBEARSResult:
    reference_tree: object

    node_results: Dict[str, BioGeoBEARSNodeResult] = field(default_factory=dict)
    parse_warnings: List[str] = field(default_factory=list)

    state_order: List[str] = field(default_factory=list)
    state_colors: Dict[str, str] = field(default_factory=dict)

    reference_node_ids: Dict[str, str] = field(default_factory=dict)

    model_name: str = "BioGeoBEARS"
    result_note: str = ""
    input_tree_count: int = 1
    effective_tree_count: int = 1

    model_statistics: Dict = field(default_factory=dict)



    def get_node_result(self, node_key: str) -> Optional[BioGeoBEARSNodeResult]:
        if not node_key:
            return None
        return self.node_results.get(node_key)
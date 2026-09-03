from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BioGeoBEARSNodeResult:
    node_key: str
    display_node_id: str = ""

    states: List[str] = field(default_factory=list)
    state_supports: Dict[str, float] = field(default_factory=dict)
    # Optional BioGeoBEARS branch-end probabilities. Values are percentages.
    # ``branch_top_supports`` is the probability at the descendant node; the
    # bottom values are immediately below that node on its incoming branch.
    branch_top_supports: Dict[str, float] = field(default_factory=dict)
    branch_bottom_supports: Dict[str, float] = field(default_factory=dict)

    pie_labels: List[str] = field(default_factory=list)
    pie_percents: List[float] = field(default_factory=list)
    pie_colors: List[str] = field(default_factory=list)

    supporting_tree_count: int = 1
    total_tree_count: int = 1
    unmatched_tree_count: int = 0

    event_summary: str = ""
    raw_method_payload: Dict = field(default_factory=dict)


@dataclass
class BioGeoBEARSResult:
    reference_tree: object

    node_results: Dict[str, BioGeoBEARSNodeResult] = field(default_factory=dict)
    parse_warnings: List[str] = field(default_factory=list)

    state_order: List[str] = field(default_factory=list)
    state_colors: Dict[str, str] = field(default_factory=dict)
    independent_state_colors: Dict[str, str] = field(default_factory=dict)
    biogeobears_state_colors: Dict[str, str] = field(default_factory=dict)
    area_order: List[str] = field(default_factory=list)
    area_colors: Dict[str, str] = field(default_factory=dict)
    state_area_members: Dict[str, List[str]] = field(default_factory=dict)

    reference_node_ids: Dict[str, str] = field(default_factory=dict)

    model_name: str = "BioGeoBEARS"
    result_note: str = ""
    input_tree_count: int = 1
    effective_tree_count: int = 1
    failed_tree_count: int = 0
    unmatched_tree_count: int = 0
    unmatched_clade_count: int = 0
    tree_failure_reasons: List[str] = field(default_factory=list)

    model_statistics: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)

    information_text: str = ""
    time_summary_text: str = ""


    def get_node_result(self, node_key: str) -> Optional[BioGeoBEARSNodeResult]:
        if not node_key:
            return None
        return self.node_results.get(node_key)

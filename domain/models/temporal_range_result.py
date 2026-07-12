from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TemporalRangeBranch:
    branch_id: str
    parent_clade_key: str
    child_clade_key: str
    parent_node_id: str = ""
    child_node_id: str = ""
    older_time: float = 0.0
    younger_time: float = 0.0
    older_probabilities: Dict[str, float] = field(default_factory=dict)
    younger_probabilities: Dict[str, float] = field(default_factory=dict)
    parent_node_probabilities: Dict[str, float] = field(default_factory=dict)
    interpolation_mode: str = "visual_linear_interpolation"
    metadata: Dict = field(default_factory=dict)


@dataclass
class TemporalRangeHistorySegment:
    sample_id: str
    branch_id: str
    older_time: float
    younger_time: float
    state: str
    metadata: Dict = field(default_factory=dict)


@dataclass
class TemporalRangeFrame:
    time: float
    active_branch_probabilities: Dict[str, Dict[str, float]] = field(default_factory=dict)
    selected_branch_id: str = ""
    selected_range_probabilities: Dict[str, float] = field(default_factory=dict)
    area_probabilities: Dict[str, float] = field(default_factory=dict)
    active_branch_count: int = 0
    display_scope: str = "all_active_lineages"
    history_mode: str = "endpoints"
    node_boundary_mode: str = "after_split"


@dataclass
class TemporalRangeResult:
    reference_tree: object
    source_model_name: str
    source_kind: str
    branches: List[TemporalRangeBranch] = field(default_factory=list)
    state_order: List[str] = field(default_factory=list)
    state_colors: Dict[str, str] = field(default_factory=dict)
    state_area_members: Dict[str, List[str]] = field(default_factory=dict)
    node_ages: Dict[str, float] = field(default_factory=dict)
    root_age: float = 0.0
    present_time: float = 0.0
    semantics_note: str = ""
    warnings: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    history_segments: List[TemporalRangeHistorySegment] = field(default_factory=list)
    history_sample_ids: List[str] = field(default_factory=list)

    def branch_by_id(self, branch_id: str) -> Optional[TemporalRangeBranch]:
        target = str(branch_id or "")
        for branch in self.branches:
            if branch.branch_id == target:
                return branch
        return None

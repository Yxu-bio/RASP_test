from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DivaNodeResult:
    node_key: str
    diva_node_id: int
    terminal_spec: str
    states: List[str] = field(default_factory=list)
    raw_line: str = ""

    # 饼图显示使用：每个状态一个独立扇区，等权
    pie_labels: List[str] = field(default_factory=list)
    pie_percents: List[float] = field(default_factory=list)
    pie_colors: List[str] = field(default_factory=list)

    @property
    def display_text(self) -> str:
        if self.states:
            return " ".join(self.states)
        return "无"

    @property
    def ambiguity_count(self) -> int:
        return len(self.states)


@dataclass
class DivaRunArtifacts:
    run_dir: str
    batch_file: str
    wrapper_file: str = ""
    console_log: str = ""
    extra_files: List[str] = field(default_factory=list)
    return_code: int = 0


@dataclass
class DivaResult:
    dataset: object
    node_results: Dict[str, DivaNodeResult] = field(default_factory=dict)
    artifacts: Optional[DivaRunArtifacts] = None
    parse_warnings: List[str] = field(default_factory=list)

    state_order: List[str] = field(default_factory=list)
    state_colors: Dict[str, str] = field(default_factory=dict)

    def get_node_result(self, node_key: str) -> Optional[DivaNodeResult]:
        if not node_key:
            return None
        return self.node_results.get(node_key)
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class TraitModelResult:
    reference_tree: object = None

    model_name: str = "Trait model statistics"
    result_note: str = ""
    input_tree_count: int = 1
    effective_tree_count: int = 1
    config: object = None

    model_statistics: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)
    parse_warnings: List[str] = field(default_factory=list)

    analysis_log_path: str = ""
    output_log_path: str = ""

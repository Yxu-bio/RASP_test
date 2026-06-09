from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ContinuousTraitNodeResult:
    node_key: str
    display_node_id: str = ""
    trait_name: str = ""

    mean: float = 0.0
    median: float = 0.0
    lower95: float = 0.0
    upper95: float = 0.0
    minimum: float = 0.0
    maximum: float = 0.0
    sample_count: int = 0

    raw_samples: List[float] = field(default_factory=list)
    raw_method_payload: Dict = field(default_factory=dict)


@dataclass
class ContinuousTraitResult:
    reference_tree: object

    node_results: Dict[str, ContinuousTraitNodeResult] = field(default_factory=dict)
    tip_values: Dict[str, float] = field(default_factory=dict)
    original_tip_values: Dict[str, float] = field(default_factory=dict)
    analysis_node_values: Dict[str, float] = field(default_factory=dict)
    original_node_values: Dict[str, float] = field(default_factory=dict)
    plot_tip_values: Dict[str, float] = field(default_factory=dict)
    plot_node_values: Dict[str, float] = field(default_factory=dict)
    parse_warnings: List[str] = field(default_factory=list)

    state_order: List[str] = field(default_factory=lambda: ["Low", "20%", "40%", "60%", "80%", "High"])
    state_colors: Dict[str, str] = field(default_factory=lambda: {
        "Low": "#440154",
        "20%": "#414487",
        "40%": "#2A788E",
        "60%": "#22A884",
        "80%": "#7AD151",
        "High": "#FDE725",
    })

    reference_node_ids: Dict[str, str] = field(default_factory=dict)

    model_name: str = "BayesTraits Continuous ASR"
    result_note: str = ""
    input_tree_count: int = 1
    effective_tree_count: int = 1

    trait_name: str = ""
    trait_transform: str = "none"
    trait_display_scale: str = "analysis"
    trait_plot_scale: str = "analysis"
    value_mode: str = "mean"
    color_scale_min: float = 0.0
    color_scale_max: float = 1.0

    model_statistics: Dict = field(default_factory=dict)

    # Optional metadata used by the publication-style continuous figure exporter.
    # These fields are intentionally generic so external workflows can supply
    # dated occurrences, time-series summaries, and clade/regime groups without
    # changing the BayesTraits result parser.
    figure_occurrences: List[Dict] = field(default_factory=list)
    figure_time_series: Dict = field(default_factory=dict)
    figure_time_bands: List[Dict] = field(default_factory=list)
    figure_groups: List[Dict] = field(default_factory=list)
    figure_group_values: Dict = field(default_factory=dict)
    figure_taxon_groups: Dict[str, str] = field(default_factory=dict)
    figure_group_order: List[str] = field(default_factory=list)
    figure_group_colors: Dict[str, str] = field(default_factory=dict)

    def get_node_result(self, node_key: str) -> Optional[ContinuousTraitNodeResult]:
        if not node_key:
            return None
        return self.node_results.get(node_key)

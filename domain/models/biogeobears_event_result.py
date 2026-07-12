from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BioGeoBEARSEventRecord:
    event_scope: str
    sample_id: str = ""
    event_type: str = ""
    event_text: str = ""
    time: Optional[float] = None
    node: str = ""
    branch: str = ""
    source_range: str = ""
    target_range: str = ""
    dispersal_to: str = ""
    extirpation_from: str = ""
    raw: Dict = field(default_factory=dict)


@dataclass
class BioGeoBEARSEventResult:
    source_model_name: str = "BioGeoBEARS"
    source_run_directory: str = ""
    source_output_json_path: str = ""
    source_clade_keys: List[str] = field(default_factory=list)

    events: List[BioGeoBEARSEventRecord] = field(default_factory=list)
    raw_tables: Dict[str, List[Dict]] = field(default_factory=dict)
    summary: Dict = field(default_factory=dict)
    event_type_counts: Dict[str, int] = field(default_factory=dict)
    route_counts: Dict[str, int] = field(default_factory=dict)
    time_series: List[Dict] = field(default_factory=list)
    parse_warnings: List[str] = field(default_factory=list)

    information_text: str = ""
    time_summary_text: str = ""

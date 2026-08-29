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
    schema_format: str = "rasp5_biogeobears_bsm_events"
    schema_version: int = 1
    source_model_name: str = "BioGeoBEARS"
    source_run_directory: str = ""
    source_output_json_path: str = ""
    source_clade_keys: List[str] = field(default_factory=list)
    event_source_files: Dict[str, str] = field(default_factory=dict)
    event_row_counts: Dict[str, int] = field(default_factory=dict)
    events_complete: bool = True
    raw_tables_complete: bool = True
    event_preview_limit: int = 0

    events: List[BioGeoBEARSEventRecord] = field(default_factory=list)
    raw_tables: Dict[str, List[Dict]] = field(default_factory=dict)
    summary: Dict = field(default_factory=dict)
    event_type_counts: Dict[str, int] = field(default_factory=dict)
    route_counts: Dict[str, int] = field(default_factory=dict)
    time_series: List[Dict] = field(default_factory=list)
    parse_warnings: List[str] = field(default_factory=list)

    precomputed_bsm_network_edges: List[Dict] = field(default_factory=list)
    precomputed_bsm_node_rows: List[Dict] = field(default_factory=list)
    precomputed_bsm_network_available: bool = False

    information_text: str = ""
    time_summary_text: str = ""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from domain.models.state_matrix import StateMatrix


@dataclass
class SpatialQAIssue:
    level: str
    code: str
    message: str
    row: Optional[int] = None
    taxon: str = ""


@dataclass
class OccurrenceRecord:
    taxon: str
    latitude: float
    longitude: float
    row_index: int
    country: str = ""
    locality: str = ""
    year: str = ""
    source: str = ""
    uncertainty_m: str = ""
    raw: Dict[str, str] = field(default_factory=dict)


@dataclass
class AreaSpatialRecord:
    area_code: str
    geometry_id: str
    display_name: str = ""
    color: str = ""
    group: str = ""
    centroid_lon: Optional[float] = None
    centroid_lat: Optional[float] = None
    source: str = ""
    crs: str = "EPSG:4326"
    geometry: Dict[str, object] = field(default_factory=dict)
    properties: Dict[str, object] = field(default_factory=dict)


@dataclass
class EncodedOccurrenceAuditRow:
    row_index: int
    taxon: str
    longitude: float
    latitude: float
    matched_areas: List[str] = field(default_factory=list)
    status: str = "unmatched"


@dataclass
class SpatialDataProject:
    occurrences: List[OccurrenceRecord] = field(default_factory=list)
    areas: List[AreaSpatialRecord] = field(default_factory=list)
    occurrence_source_path: str = ""
    area_source_path: str = ""
    qa_issues: List[SpatialQAIssue] = field(default_factory=list)
    encoded_matrix: Optional[StateMatrix] = None
    encoded_audit_rows: List[EncodedOccurrenceAuditRow] = field(default_factory=list)

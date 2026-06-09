from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BioGeoBEARSModelTestRow:
    model_name: str
    display_name: str

    success: bool = False
    error_message: str = ""

    log_likelihood: Optional[float] = None
    num_params: Optional[int] = None
    sample_size: Optional[int] = None

    aic: Optional[float] = None
    aicc: Optional[float] = None
    delta_aic: Optional[float] = None
    delta_aicc: Optional[float] = None
    weight: Optional[float] = None

    workdir: str = ""
    output_json_path: str = ""


@dataclass
class BioGeoBEARSModelTestLRTEntry:
    alt_model_name: str
    null_model_name: str
    alt_display_name: str
    null_display_name: str

    success: bool = False
    error_message: str = ""

    alt_log_likelihood: Optional[float] = None
    null_log_likelihood: Optional[float] = None
    alt_num_params: Optional[int] = None
    null_num_params: Optional[int] = None

    lrt_statistic: Optional[float] = None
    df: Optional[int] = None
    p_value: Optional[float] = None


@dataclass
class BioGeoBEARSModelTestResult:
    rows: List[BioGeoBEARSModelTestRow] = field(default_factory=list)
    lrt_entries: List[BioGeoBEARSModelTestLRTEntry] = field(default_factory=list)

    best_model_name: str = ""
    best_display_name: str = ""
    criterion_used: str = "AICc"

    input_tree_count: int = 1
    effective_model_count: int = 0
    failed_model_count: int = 0

    model_results: Dict[str, object] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    teststable_path: str = ""

    result_note: str = "BioGeoBEARS model test."

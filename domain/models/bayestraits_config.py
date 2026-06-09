import json
from dataclasses import dataclass, field
from typing import Dict, List


BAYESTRAITS_ANALYSIS_METHODS = {
    "ML": "Maximum Likelihood",
    "MCMC": "MCMC",
}

BAYESTRAITS_CONTINUOUS_TRANSFORMS = {
    "none": "None",
    "log": "Natural log (ln)",
    "log10": "Log10",
}

BAYESTRAITS_CONTINUOUS_DISPLAY_SCALES = {
    "analysis": "Analysis scale",
    "original": "Original scale (back-transformed)",
}

BAYESTRAITS_CONTINUOUS_PLOT_SCALES = {
    "analysis": "Analysis scale",
    "original": "Original scale (back-transformed)",
}

BAYESTRAITS_CONTINUOUS_DTT_WEIGHT_MODES = {
    "corrected": "Corrected gradual split",
    "paper_original": "Paper original weighting",
}

BAYESTRAITS_MODELS = {
    "MULTISTATE": {
        "label": "MultiState",
        "code": 1,
        "trait_kind": "categorical",
        "min_traits": 1,
        "max_traits": 1,
        "supports_nodes": True,
    },
    "CONTINUOUS_RANDOM_WALK": {
        "label": "Continuous: Random Walk (Model A)",
        "code": 4,
        "trait_kind": "continuous",
        "min_traits": 1,
        "max_traits": 1,
        "supports_nodes": False,
        "supports_continuous_asr": True,
    },
    "CONTINUOUS_DIRECTIONAL": {
        "label": "Continuous: Directional (Model B)",
        "code": 5,
        "trait_kind": "continuous",
        "min_traits": 1,
        "max_traits": 1,
        "supports_nodes": False,
        "supports_continuous_asr": True,
    },
    "INDEPENDENT_CONTRAST": {
        "label": "Independent Contrast",
        "code": 7,
        "trait_kind": "continuous",
        "min_traits": 1,
        "max_traits": 1,
        "supports_nodes": False,
    },
    "INDEPENDENT_CONTRAST_CORRELATION": {
        "label": "Independent Contrast: Correlation",
        "code": 8,
        "trait_kind": "continuous",
        "min_traits": 2,
        "max_traits": 0,
        "supports_nodes": False,
    },
    "FAT_TAIL": {
        "label": "Fat Tail",
        "code": 12,
        "trait_kind": "continuous",
        "min_traits": 1,
        "max_traits": 1,
        "supports_nodes": False,
        "analysis_method": "MCMC",
    },
}


BAYESTRAITS_HYPER_PRIOR_ALL = [
    "",
    "HyperPriorAll gamma 0 10 0 10",
    "HyperPriorAll exponential 0 10",
    "HyperPriorAll beta 0 100 0 50",
    "HyperPriorAll uniform 0 100 0 100",
]


BAYESTRAITS_REVJUMP_HP = [
    "",
    "RevJumpHP gamma 0 10 0 10",
    "RevJumpHP exponential 0 10",
    "RevJumpHP beta 0 100 0 50",
    "RevJumpHP uniform 0 100 0 100",
]


BAYESTRAITS_RESTRICT_ALL = [
    "",
    "RestrictAll 1",
]


BAYESTRAITS_STONES = [
    "",
    "stones 100 10000",
]


@dataclass
class BayesTraitsConfig:
    trait_columns: List[str]
    trait_column: str = ""
    model: str = "MULTISTATE"
    selected_trait_columns: List[str] = field(default_factory=list)

    analysis_method: str = "ML"
    ml_tries: int = 100

    iterations: int = 5050000
    sample_frequency: int = 10000
    burnin: int = 50000
    hyper_prior_all: str = ""
    revjump_hp: str = ""
    restrict_all: str = ""
    stones: str = "stones 100 10000"

    extra_commands: str = ""
    random_seed: int = 0
    auto_map_categorical: bool = False
    use_tree_collection: bool = True
    continuous_asr: bool = False
    continuous_transform: str = "none"
    continuous_display_scale: str = "analysis"
    continuous_plot_scale: str = "analysis"
    continuous_dtt: bool = False
    continuous_dtt_tree_limit: int = 30
    continuous_dtt_threads: int = 1
    continuous_dtt_random_seed: int = 20260608
    continuous_dtt_time_step: float = 5.0
    continuous_dtt_age_offset: float = 0.0
    continuous_dtt_bootstrap_count: int = 100
    continuous_dtt_weight_mode: str = "corrected"

    selected_node_ids: List[str] = field(default_factory=list)
    fossil_states: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def default_for_columns(cls, trait_columns, node_ids=None):
        columns = [str(x).strip() for x in list(trait_columns or []) if str(x).strip()]
        return cls(
            trait_columns=columns,
            trait_column=columns[0] if columns else "",
            selected_trait_columns=[columns[0]] if columns else [],
            selected_node_ids=[str(x).strip() for x in list(node_ids or []) if str(x).strip()],
        )

    def validate(self) -> None:
        columns = [str(x).strip() for x in list(self.trait_columns or []) if str(x).strip()]
        if not columns:
            raise ValueError("BayesTraits requires at least one trait/state column.")
        self.trait_columns = columns

        self.trait_column = str(self.trait_column or "").strip()
        if not self.trait_column:
            self.trait_column = columns[0]
        if self.trait_column not in columns:
            raise ValueError("Selected trait column is not present in the current matrix: %s" % self.trait_column)

        self.model = normalize_bayestraits_model(self.model)
        model_spec = BAYESTRAITS_MODELS[self.model]
        self.continuous_asr = bool(self.continuous_asr)
        self.continuous_dtt = bool(getattr(self, "continuous_dtt", False))
        self.continuous_transform = normalize_bayestraits_continuous_transform(
            getattr(self, "continuous_transform", "none")
        )
        self.continuous_display_scale = normalize_bayestraits_continuous_display_scale(
            getattr(self, "continuous_display_scale", "analysis")
        )
        self.continuous_plot_scale = normalize_bayestraits_continuous_plot_scale(
            getattr(self, "continuous_plot_scale", "analysis")
        )
        if str(model_spec.get("trait_kind", "")) != "continuous":
            self.continuous_transform = "none"
            self.continuous_display_scale = "analysis"
            self.continuous_plot_scale = "analysis"
            self.continuous_dtt = False
        if self.continuous_transform == "none":
            self.continuous_display_scale = "analysis"
            self.continuous_plot_scale = "analysis"
        self.random_seed = int(getattr(self, "random_seed", 0) or 0)
        if self.random_seed < 0:
            raise ValueError("Random seed cannot be negative.")
        if self.continuous_asr:
            if not bool(model_spec.get("supports_continuous_asr", False)):
                raise ValueError("Continuous ASR visualization is only available for Continuous Model A / Model B.")
            self.analysis_method = "MCMC"
            self.use_tree_collection = False
        else:
            self.continuous_dtt = False

        self.continuous_dtt_tree_limit = int(getattr(self, "continuous_dtt_tree_limit", 30) or 30)
        self.continuous_dtt_threads = int(getattr(self, "continuous_dtt_threads", 1) or 1)
        self.continuous_dtt_random_seed = int(getattr(self, "continuous_dtt_random_seed", 20260608) or 20260608)
        self.continuous_dtt_time_step = float(getattr(self, "continuous_dtt_time_step", 5.0) or 5.0)
        self.continuous_dtt_age_offset = float(getattr(self, "continuous_dtt_age_offset", 0.0) or 0.0)
        self.continuous_dtt_bootstrap_count = int(getattr(self, "continuous_dtt_bootstrap_count", 100) or 100)
        self.continuous_dtt_weight_mode = normalize_bayestraits_continuous_dtt_weight_mode(
            getattr(self, "continuous_dtt_weight_mode", "corrected")
        )
        self.continuous_dtt_tree_limit = max(1, min(30, self.continuous_dtt_tree_limit))
        self.continuous_dtt_threads = max(1, self.continuous_dtt_threads)
        self.continuous_dtt_time_step = max(0.000001, self.continuous_dtt_time_step)
        self.continuous_dtt_bootstrap_count = max(1, self.continuous_dtt_bootstrap_count)
        if self.continuous_dtt and self.continuous_dtt_random_seed < 0:
            raise ValueError("DTT random seed cannot be negative.")

        requested_traits = [
            str(x).strip()
            for x in list(self.selected_trait_columns or [])
            if str(x).strip()
        ]
        selected_traits = [col for col in requested_traits if col in columns]
        if not selected_traits:
            selected_traits = [self.trait_column]
        max_traits = int(model_spec.get("max_traits", 0) or 0)
        if max_traits > 0:
            selected_traits = selected_traits[:max_traits]
        min_traits = int(model_spec.get("min_traits", 1) or 1)
        if len(selected_traits) < min_traits:
            raise ValueError(
                "%s requires at least %s trait column(s)."
                % (model_spec["label"], min_traits)
            )
        self.selected_trait_columns = selected_traits
        self.trait_column = selected_traits[0]

        self.analysis_method = normalize_bayestraits_analysis_method(self.analysis_method)
        forced_method = str(model_spec.get("analysis_method", "") or "")
        if forced_method:
            self.analysis_method = forced_method
        if self.continuous_asr:
            self.analysis_method = "MCMC"
        self.ml_tries = int(self.ml_tries or 0)
        if self.ml_tries <= 0:
            raise ValueError("MLTries must be greater than 0.")

        self.iterations = int(self.iterations or 0)
        self.sample_frequency = int(self.sample_frequency or 0)
        self.burnin = int(self.burnin or 0)
        if self.iterations <= 0:
            raise ValueError("Iterations must be greater than 0.")
        if self.sample_frequency <= 0:
            raise ValueError("Sample must be greater than 0.")
        if self.burnin < 0:
            raise ValueError("BurnIn cannot be negative.")
        if self.analysis_method == "MCMC":
            if self.burnin >= self.iterations - self.sample_frequency - 1:
                raise ValueError("Number of discard samples is too large.")
            if self.burnin < 1000:
                raise ValueError("Number of discard samples is too small.")

        self.hyper_prior_all = str(self.hyper_prior_all or "").strip()
        self.revjump_hp = str(self.revjump_hp or "").strip()
        self.restrict_all = str(self.restrict_all or "").strip()
        self.stones = str(self.stones or "").strip()
        self.extra_commands = str(self.extra_commands or "").replace("\r\n", "\n").replace("\r", "\n")

        selected = [str(x).strip() for x in list(self.selected_node_ids or []) if str(x).strip()]
        if bool(model_spec.get("supports_nodes", False)) and not selected:
            raise ValueError("Select one node at least.")
        self.selected_node_ids = selected

        fossils = {}
        for node_id, state in dict(self.fossil_states or {}).items():
            key = str(node_id or "").strip()
            value = str(state or "").strip()
            if key and value:
                fossils[key] = value
        self.fossil_states = fossils

    def to_preset_dict(self) -> Dict[str, object]:
        return {
            "trait_columns": list(self.trait_columns or []),
            "trait_column": str(self.trait_column or ""),
            "model": str(self.model or "MULTISTATE"),
            "selected_trait_columns": list(self.selected_trait_columns or []),
            "analysis_method": str(self.analysis_method or "ML"),
            "ml_tries": int(self.ml_tries),
            "iterations": int(self.iterations),
            "sample_frequency": int(self.sample_frequency),
            "burnin": int(self.burnin),
            "hyper_prior_all": str(self.hyper_prior_all or ""),
            "revjump_hp": str(self.revjump_hp or ""),
            "restrict_all": str(self.restrict_all or ""),
            "stones": str(self.stones or ""),
            "extra_commands": str(self.extra_commands or ""),
            "random_seed": int(getattr(self, "random_seed", 0) or 0),
            "auto_map_categorical": bool(self.auto_map_categorical),
            "use_tree_collection": bool(self.use_tree_collection),
            "continuous_asr": bool(self.continuous_asr),
            "continuous_transform": str(getattr(self, "continuous_transform", "none") or "none"),
            "continuous_display_scale": str(getattr(self, "continuous_display_scale", "analysis") or "analysis"),
            "continuous_plot_scale": str(getattr(self, "continuous_plot_scale", "analysis") or "analysis"),
            "continuous_dtt": bool(getattr(self, "continuous_dtt", False)),
            "continuous_dtt_tree_limit": int(getattr(self, "continuous_dtt_tree_limit", 30) or 30),
            "continuous_dtt_threads": int(getattr(self, "continuous_dtt_threads", 1) or 1),
            "continuous_dtt_random_seed": int(getattr(self, "continuous_dtt_random_seed", 20260608) or 20260608),
            "continuous_dtt_time_step": float(getattr(self, "continuous_dtt_time_step", 5.0) or 5.0),
            "continuous_dtt_age_offset": float(getattr(self, "continuous_dtt_age_offset", 0.0) or 0.0),
            "continuous_dtt_bootstrap_count": int(getattr(self, "continuous_dtt_bootstrap_count", 100) or 100),
            "continuous_dtt_weight_mode": str(getattr(self, "continuous_dtt_weight_mode", "corrected") or "corrected"),
            "selected_node_ids": list(self.selected_node_ids or []),
            "fossil_states": dict(self.fossil_states or {}),
        }

    def to_preset_json_text(self) -> str:
        self.validate()
        payload = {
            "format": "RASP-Python BayesTraits config",
            "version": 1,
            "config": self.to_preset_dict(),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_preset_json_text(cls, text: str, trait_columns: List[str], node_ids=None, base_config=None):
        try:
            payload = json.loads(str(text or ""))
        except Exception as exc:
            raise ValueError("Not a JSON BayesTraits setting file.") from exc

        data = payload.get("config", payload) if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Invalid BayesTraits setting file.")

        columns = [str(x).strip() for x in list(trait_columns or []) if str(x).strip()]
        saved_columns = [str(x).strip() for x in list(data.get("trait_columns", []) or []) if str(x).strip()]
        if saved_columns and saved_columns != columns:
            raise ValueError(
                "The setting file trait columns (%s) do not match the current matrix columns (%s)."
                % (", ".join(saved_columns), ", ".join(columns))
            )

        default = cls.default_for_columns(columns, node_ids=node_ids)
        base = base_config if base_config is not None else default

        def value(name, fallback):
            return data.get(name, getattr(base, name, fallback))

        valid_node_ids = {str(x).strip() for x in list(node_ids or []) if str(x).strip()}
        selected = [
            str(x).strip()
            for x in list(value("selected_node_ids", getattr(default, "selected_node_ids", [])) or [])
            if str(x).strip()
        ]
        if valid_node_ids:
            selected = [node_id for node_id in selected if node_id in valid_node_ids]
            if not selected:
                selected = list(getattr(default, "selected_node_ids", []) or [])

        fossils = {}
        for node_id, state in dict(value("fossil_states", {}) or {}).items():
            key = str(node_id or "").strip()
            if valid_node_ids and key not in valid_node_ids:
                continue
            value_text = str(state or "").strip()
            if key and value_text:
                fossils[key] = value_text

        config = cls(
            trait_columns=columns,
            trait_column=str(value("trait_column", default.trait_column) or default.trait_column),
            model=str(value("model", default.model) or default.model),
            selected_trait_columns=[
                str(x).strip()
                for x in list(value("selected_trait_columns", getattr(default, "selected_trait_columns", [])) or [])
                if str(x).strip()
            ],
            analysis_method=str(value("analysis_method", default.analysis_method) or default.analysis_method),
            ml_tries=int(value("ml_tries", default.ml_tries) or default.ml_tries),
            iterations=int(value("iterations", default.iterations) or default.iterations),
            sample_frequency=int(value("sample_frequency", default.sample_frequency) or default.sample_frequency),
            burnin=int(value("burnin", default.burnin) or default.burnin),
            hyper_prior_all=str(value("hyper_prior_all", default.hyper_prior_all) or ""),
            revjump_hp=str(value("revjump_hp", default.revjump_hp) or ""),
            restrict_all=str(value("restrict_all", default.restrict_all) or ""),
            stones=str(value("stones", default.stones) or ""),
            extra_commands=str(value("extra_commands", default.extra_commands) or ""),
            random_seed=int(value("random_seed", getattr(default, "random_seed", 0)) or 0),
            auto_map_categorical=bool(value("auto_map_categorical", default.auto_map_categorical)),
            use_tree_collection=bool(value("use_tree_collection", default.use_tree_collection)),
            continuous_asr=bool(value("continuous_asr", getattr(default, "continuous_asr", False))),
            continuous_transform=str(value("continuous_transform", getattr(default, "continuous_transform", "none")) or "none"),
            continuous_display_scale=str(value("continuous_display_scale", getattr(default, "continuous_display_scale", "analysis")) or "analysis"),
            continuous_plot_scale=str(value("continuous_plot_scale", getattr(default, "continuous_plot_scale", "analysis")) or "analysis"),
            continuous_dtt=bool(value("continuous_dtt", getattr(default, "continuous_dtt", False))),
            continuous_dtt_tree_limit=int(value("continuous_dtt_tree_limit", getattr(default, "continuous_dtt_tree_limit", 30)) or 30),
            continuous_dtt_threads=int(value("continuous_dtt_threads", getattr(default, "continuous_dtt_threads", 1)) or 1),
            continuous_dtt_random_seed=int(value("continuous_dtt_random_seed", getattr(default, "continuous_dtt_random_seed", 20260608)) or 20260608),
            continuous_dtt_time_step=float(value("continuous_dtt_time_step", getattr(default, "continuous_dtt_time_step", 5.0)) or 5.0),
            continuous_dtt_age_offset=float(value("continuous_dtt_age_offset", getattr(default, "continuous_dtt_age_offset", 0.0)) or 0.0),
            continuous_dtt_bootstrap_count=int(value("continuous_dtt_bootstrap_count", getattr(default, "continuous_dtt_bootstrap_count", 100)) or 100),
            continuous_dtt_weight_mode=str(value("continuous_dtt_weight_mode", getattr(default, "continuous_dtt_weight_mode", "corrected")) or "corrected"),
            selected_node_ids=selected,
            fossil_states=fossils,
        )
        config.validate()
        return config


def normalize_bayestraits_analysis_method(value: str) -> str:
    text = str(value or "ML").strip().upper().replace(" ", "_")
    aliases = {
        "ML": "ML",
        "MAXIMUM_LIKELIHOOD": "ML",
        "MCMC": "MCMC",
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("Unsupported BayesTraits analysis method: %s" % value)


def normalize_bayestraits_continuous_transform(value: str) -> str:
    text = str(value or "none").strip().lower().replace(" ", "").replace("_", "")
    aliases = {
        "": "none",
        "none": "none",
        "no": "none",
        "raw": "none",
        "original": "none",
        "ln": "log",
        "log": "log",
        "naturallog": "log",
        "loge": "log",
        "log10": "log10",
        "base10log": "log10",
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("Unsupported continuous trait transform: %s" % value)


def normalize_bayestraits_continuous_display_scale(value: str) -> str:
    text = str(value or "analysis").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    aliases = {
        "": "analysis",
        "analysis": "analysis",
        "analysisscale": "analysis",
        "transformed": "analysis",
        "transformedscale": "analysis",
        "model": "analysis",
        "modelscale": "analysis",
        "original": "original",
        "originalscale": "original",
        "backtransformed": "original",
        "backtransformedoriginalscale": "original",
        "raw": "original",
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("Unsupported continuous trait display scale: %s" % value)


def normalize_bayestraits_continuous_plot_scale(value: str) -> str:
    text = str(value or "analysis").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    aliases = {
        "": "analysis",
        "analysis": "analysis",
        "analysisscale": "analysis",
        "transformed": "analysis",
        "transformedscale": "analysis",
        "model": "analysis",
        "modelscale": "analysis",
        "plot": "analysis",
        "colors": "analysis",
        "original": "original",
        "originalscale": "original",
        "backtransformed": "original",
        "backtransformedoriginalscale": "original",
        "linear": "original",
        "linearscale": "original",
        "raw": "original",
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("Unsupported continuous trait plot scale: %s" % value)


def normalize_bayestraits_continuous_dtt_weight_mode(value: str) -> str:
    text = str(value or "corrected").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    aliases = {
        "": "corrected",
        "corrected": "corrected",
        "normal": "corrected",
        "gradual": "corrected",
        "gradualsplit": "corrected",
        "paper": "paper_original",
        "paperoriginal": "paper_original",
        "original": "paper_original",
        "legacy": "paper_original",
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("Unsupported continuous DTT weight mode: %s" % value)


def normalize_bayestraits_model(value: str) -> str:
    text = str(value or "MULTISTATE").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "1": "MULTISTATE",
        "MULTISTATE": "MULTISTATE",
        "4": "CONTINUOUS_RANDOM_WALK",
        "CONTINUOUS_RANDOM_WALK": "CONTINUOUS_RANDOM_WALK",
        "CONTINUOUS_MODEL_A": "CONTINUOUS_RANDOM_WALK",
        "MODEL_A": "CONTINUOUS_RANDOM_WALK",
        "5": "CONTINUOUS_DIRECTIONAL",
        "CONTINUOUS_DIRECTIONAL": "CONTINUOUS_DIRECTIONAL",
        "CONTINUOUS_MODEL_B": "CONTINUOUS_DIRECTIONAL",
        "MODEL_B": "CONTINUOUS_DIRECTIONAL",
        "7": "INDEPENDENT_CONTRAST",
        "INDEPENDENT_CONTRAST": "INDEPENDENT_CONTRAST",
        "8": "INDEPENDENT_CONTRAST_CORRELATION",
        "INDEPENDENT_CONTRAST_CORRELATION": "INDEPENDENT_CONTRAST_CORRELATION",
        "CORRELATION": "INDEPENDENT_CONTRAST_CORRELATION",
        "12": "FAT_TAIL",
        "FAT_TAIL": "FAT_TAIL",
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("Unsupported BayesTraits model: %s" % value)

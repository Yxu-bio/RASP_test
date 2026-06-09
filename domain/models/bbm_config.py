import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


BBM_STATE_FREQUENCY_MODELS = {
    "JC": "Fixed (JC)",
    "F81": "Estimated (F81)",
}

BBM_RATE_VARIATION_MODELS = {
    "EQUAL": "Equal",
    "GAMMA": "Gamma (+G)",
}

BBM_ROOT_DISTRIBUTIONS = {
    "NULL": "Null",
    "WIDE": "Wide",
    "CUSTOM": "Custom",
}


@dataclass
class BBMConfig:
    area_names: List[str]

    max_areas: int = 4
    include_null_range: bool = False

    chain_length: int = 50000
    sample_frequency: int = 100
    discard_samples: int = 100
    chains: int = 10
    temperature: float = 0.1

    state_frequency_model: str = "JC"
    dirichlet_alpha: float = 0.5
    dirichlet_beta: float = 0.5
    rate_variation_model: str = "EQUAL"
    gamma_min: float = 0.001
    gamma_max: float = 100.0

    root_distribution: str = "NULL"
    custom_root_distribution: str = ""
    large_dataset_mode: bool = False

    selected_node_ids: List[str] = field(default_factory=list)

    @classmethod
    def default_for_areas(cls, area_names, node_ids=None):
        names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        return cls(
            area_names=names,
            max_areas=min(4, len(names)) if names else 1,
            selected_node_ids=[str(x).strip() for x in list(node_ids or []) if str(x).strip()],
        )

    def validate(self) -> None:
        names = [str(x).strip() for x in list(self.area_names or []) if str(x).strip()]
        if not names:
            raise ValueError("BBM requires at least one area.")
        if len(set(names)) != len(names):
            raise ValueError("BBM area names must be unique.")
        self.area_names = names

        self.max_areas = int(self.max_areas or 0)
        if self.max_areas <= 0:
            raise ValueError("Maximum number of areas must be greater than 0.")
        self.max_areas = min(self.max_areas, len(self.area_names))

        self.chain_length = int(self.chain_length or 0)
        self.sample_frequency = int(self.sample_frequency or 0)
        self.discard_samples = int(self.discard_samples or 0)
        self.chains = int(self.chains or 0)
        self.temperature = float(self.temperature)

        if self.chain_length <= 0:
            raise ValueError("Number of cycles must be greater than 0.")
        if self.sample_frequency <= 0:
            raise ValueError("Frequent of samples must be greater than 0.")
        if self.chain_length % self.sample_frequency != 0:
            raise ValueError("Number of cycles must be an integer multiple of frequent of samples.")
        if self.discard_samples < 10:
            raise ValueError("Number of discard samples is too small.")
        if self.discard_samples >= int(self.chain_length / self.sample_frequency) - 1:
            raise ValueError("Number of discard samples is too large.")
        if self.chains <= 0:
            raise ValueError("Number of chains must be greater than 0.")
        if self.temperature <= 0:
            raise ValueError("Temperature must be greater than 0.")

        self.state_frequency_model = normalize_bbm_state_frequency_model(self.state_frequency_model)
        self.rate_variation_model = normalize_bbm_rate_variation_model(self.rate_variation_model)
        self.root_distribution = normalize_bbm_root_distribution(self.root_distribution)

        self.dirichlet_alpha = float(self.dirichlet_alpha)
        self.dirichlet_beta = float(self.dirichlet_beta)
        self.gamma_min = float(self.gamma_min)
        self.gamma_max = float(self.gamma_max)
        if self.dirichlet_alpha <= 0 or self.dirichlet_beta <= 0:
            raise ValueError("Dirichlet distribution parameters must be greater than 0.")
        if self.gamma_min <= 0 or self.gamma_max <= 0 or self.gamma_min >= self.gamma_max:
            raise ValueError("Gamma distribution range is invalid.")

        custom = str(self.custom_root_distribution or "").strip().upper()
        if self.root_distribution == "CUSTOM":
            for ch in custom:
                if ch not in self.area_names:
                    raise ValueError("Custom root distribution contains an unknown area: %s" % ch)
        self.custom_root_distribution = custom

        self.selected_node_ids = [
            str(x).strip()
            for x in list(self.selected_node_ids or [])
            if str(x).strip()
        ]
        if not self.selected_node_ids:
            raise ValueError("Select one node at least.")

    def to_preset_dict(self) -> Dict[str, object]:
        return {
            "area_names": list(self.area_names or []),
            "max_areas": int(self.max_areas),
            "include_null_range": bool(self.include_null_range),
            "chain_length": int(self.chain_length),
            "sample_frequency": int(self.sample_frequency),
            "discard_samples": int(self.discard_samples),
            "chains": int(self.chains),
            "temperature": float(self.temperature),
            "state_frequency_model": str(self.state_frequency_model or "JC"),
            "dirichlet_alpha": float(self.dirichlet_alpha),
            "dirichlet_beta": float(self.dirichlet_beta),
            "rate_variation_model": str(self.rate_variation_model or "EQUAL"),
            "gamma_min": float(self.gamma_min),
            "gamma_max": float(self.gamma_max),
            "root_distribution": str(self.root_distribution or "NULL"),
            "custom_root_distribution": str(self.custom_root_distribution or ""),
            "large_dataset_mode": bool(self.large_dataset_mode),
            "selected_node_ids": list(self.selected_node_ids or []),
        }

    def to_preset_json_text(self) -> str:
        self.validate()
        payload = {
            "format": "RASP-Python BBM config",
            "version": 1,
            "config": self.to_preset_dict(),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_preset_json_text(cls, text: str, area_names: List[str], node_ids=None, base_config=None):
        try:
            payload = json.loads(str(text or ""))
        except Exception as exc:
            raise ValueError("Not a JSON BBM setting file.") from exc

        data = payload.get("config", payload) if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Invalid BBM setting file.")

        names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        saved_areas = [str(x).strip() for x in list(data.get("area_names", []) or []) if str(x).strip()]
        if saved_areas and saved_areas != names:
            raise ValueError(
                "The setting file areas (%s) do not match the current data areas (%s)."
                % (", ".join(saved_areas), ", ".join(names))
            )

        default = cls.default_for_areas(names, node_ids=node_ids)
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

        config = cls(
            area_names=names,
            max_areas=int(value("max_areas", default.max_areas) or default.max_areas),
            include_null_range=bool(value("include_null_range", False)),
            chain_length=int(value("chain_length", default.chain_length) or default.chain_length),
            sample_frequency=int(value("sample_frequency", default.sample_frequency) or default.sample_frequency),
            discard_samples=int(value("discard_samples", default.discard_samples) or default.discard_samples),
            chains=int(value("chains", default.chains) or default.chains),
            temperature=float(value("temperature", default.temperature) or default.temperature),
            state_frequency_model=str(value("state_frequency_model", default.state_frequency_model) or default.state_frequency_model),
            dirichlet_alpha=float(value("dirichlet_alpha", default.dirichlet_alpha) or default.dirichlet_alpha),
            dirichlet_beta=float(value("dirichlet_beta", default.dirichlet_beta) or default.dirichlet_beta),
            rate_variation_model=str(value("rate_variation_model", default.rate_variation_model) or default.rate_variation_model),
            gamma_min=float(value("gamma_min", default.gamma_min) or default.gamma_min),
            gamma_max=float(value("gamma_max", default.gamma_max) or default.gamma_max),
            root_distribution=str(value("root_distribution", default.root_distribution) or default.root_distribution),
            custom_root_distribution=str(value("custom_root_distribution", default.custom_root_distribution) or ""),
            large_dataset_mode=bool(value("large_dataset_mode", default.large_dataset_mode)),
            selected_node_ids=selected,
        )
        config.validate()
        return config


def normalize_bbm_state_frequency_model(value: str) -> str:
    text = str(value or "JC").strip().upper().replace(" ", "_")
    aliases = {
        "JC": "JC",
        "FIXED": "JC",
        "FIXED_(JC)": "JC",
        "F81": "F81",
        "ESTIMATED": "F81",
        "ESTIMATED_(F81)": "F81",
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("Unsupported BBM state-frequency model: %s" % value)


def normalize_bbm_rate_variation_model(value: str) -> str:
    text = str(value or "EQUAL").strip().upper().replace(" ", "_")
    aliases = {
        "EQUAL": "EQUAL",
        "GAMMA": "GAMMA",
        "GAMMA_(+G)": "GAMMA",
        "+G": "GAMMA",
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("Unsupported BBM rate-variation model: %s" % value)


def normalize_bbm_root_distribution(value: str) -> str:
    text = str(value or "NULL").strip().upper().replace(" ", "_")
    aliases = {
        "NULL": "NULL",
        "WIDE": "WIDE",
        "CUSTOM": "CUSTOM",
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("Unsupported BBM root distribution: %s" % value)

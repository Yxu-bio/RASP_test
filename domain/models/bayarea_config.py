import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


BAYAREA_MODEL_DISPLAY = {
    "INDEPENDENCE": "INDEPENDENCE",
    "DISTANCE_NORM": "DISTANCE NORM",
}

BAYAREA_MODEL_CODE = {
    "INDEPENDENCE": 1,
    "DISTANCE_NORM": 3,
}


@dataclass
class BayAreaConfig:
    area_names: List[str]
    coordinates: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    chain_length: int = 5000000
    sample_frequency: int = 1000
    burnin: int = 0
    model_type: str = "DISTANCE_NORM"
    guess_initial_rates: bool = True
    use_auxiliary_sampling: bool = False
    geo_distance_power_positive: bool = False
    geo_distance_truncate: bool = False
    seed: Optional[int] = None
    other_options: str = (
        "-gainPrior=1.0\n"
        "-lossPrior=1.0\n"
        "-distancePowerPrior=1.0\n"
        "-areaProposalTuner=0.2"
    )
    save_original_results: bool = False
    save_original_results_path: str = ""

    @classmethod
    def default_for_areas(cls, area_names):
        names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        return cls(
            area_names=names,
            coordinates={name: (0.0, 0.0) for name in names},
        )

    def validate(self) -> None:
        names = [str(x).strip() for x in list(self.area_names or []) if str(x).strip()]
        if not names:
            raise ValueError("No areas were detected from the matrix.")
        if len(set(names)) != len(names):
            raise ValueError("Area names must be unique.")

        self.area_names = names
        self.chain_length = int(self.chain_length or 0)
        self.sample_frequency = int(self.sample_frequency or 0)
        self.burnin = int(self.burnin or 0)
        if self.chain_length <= 0:
            raise ValueError("BayArea chain length must be greater than 0.")
        if self.sample_frequency <= 0:
            raise ValueError("BayArea sample frequency must be greater than 0.")
        if self.chain_length % self.sample_frequency != 0:
            raise ValueError("Chain length must be an integer multiple of sample frequency.")
        if self.burnin < 0:
            raise ValueError("Burn-in must be greater than or equal to 0.")
        if self.burnin >= self.chain_length:
            raise ValueError("Burn-in must be smaller than chain length.")
        if self.burnin and self.burnin % self.sample_frequency != 0:
            raise ValueError("Burn-in must be an integer multiple of sample frequency.")

        self.model_type = normalize_bayarea_model_type(self.model_type)
        if self.seed is not None:
            self.seed = int(self.seed)
            if self.seed <= 0:
                self.seed = None

        normalized_coords = {}
        for area in names:
            lat, lon = self.coordinates.get(area, (0.0, 0.0))
            normalized_coords[area] = (float(lat), float(lon))
        self.coordinates = normalized_coords

    def engine_kwargs(self) -> Dict[str, object]:
        self.validate()
        return {
            "chain_length": int(self.chain_length),
            "sample_frequency": int(self.sample_frequency),
            "burnin": int(self.burnin),
            "model_type": self.model_type,
            "model_type_code": BAYAREA_MODEL_CODE[self.model_type],
            "guess_initial_rates": bool(self.guess_initial_rates),
            "use_auxiliary_sampling": bool(self.use_auxiliary_sampling),
            "geo_distance_power_positive": bool(self.geo_distance_power_positive),
            "geo_distance_truncate": bool(self.geo_distance_truncate),
            "seed": self.seed,
            "other_options": str(self.other_options or ""),
            "save_original_results": bool(self.save_original_results),
            "save_original_results_path": str(self.save_original_results_path or ""),
        }

    def to_preset_dict(self) -> Dict[str, object]:
        return {
            "area_names": list(self.area_names or []),
            "coordinates": {
                key: [float(value[0]), float(value[1])]
                for key, value in dict(self.coordinates or {}).items()
            },
            "chain_length": int(self.chain_length),
            "sample_frequency": int(self.sample_frequency),
            "burnin": int(self.burnin),
            "model_type": str(self.model_type or "DISTANCE_NORM"),
            "guess_initial_rates": bool(self.guess_initial_rates),
            "use_auxiliary_sampling": bool(self.use_auxiliary_sampling),
            "geo_distance_power_positive": bool(self.geo_distance_power_positive),
            "geo_distance_truncate": bool(self.geo_distance_truncate),
            "seed": self.seed,
            "other_options": str(self.other_options or ""),
            "save_original_results": bool(self.save_original_results),
            "save_original_results_path": str(self.save_original_results_path or ""),
        }

    def to_preset_json_text(self) -> str:
        self.validate()
        payload = {
            "format": "RASP-Python BayArea config",
            "version": 1,
            "config": self.to_preset_dict(),
            "runtime": self.engine_kwargs(),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_preset_json_text(cls, text: str, area_names: List[str], base_config=None):
        try:
            payload = json.loads(str(text or ""))
        except Exception as exc:
            raise ValueError("Not a JSON BayArea setting file.") from exc

        data = payload.get("config", payload) if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Invalid BayArea setting file.")

        names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        saved_areas = [str(x).strip() for x in list(data.get("area_names", []) or []) if str(x).strip()]
        if saved_areas and saved_areas != names:
            raise ValueError(
                "The setting file areas (%s) do not match the current data areas (%s)."
                % (", ".join(saved_areas), ", ".join(names))
            )

        base = base_config if base_config is not None else cls.default_for_areas(names)

        def value(name, default):
            return data.get(name, getattr(base, name, default))

        coords = {}
        raw_coords = value("coordinates", getattr(base, "coordinates", {})) or {}
        for area in names:
            raw = raw_coords.get(area, (0.0, 0.0)) if isinstance(raw_coords, dict) else (0.0, 0.0)
            try:
                coords[area] = (float(raw[0]), float(raw[1]))
            except Exception:
                coords[area] = (0.0, 0.0)

        seed_value = value("seed", getattr(base, "seed", None))
        try:
            seed_value = int(seed_value) if seed_value not in (None, "") else None
        except Exception:
            seed_value = None

        config = cls(
            area_names=names,
            coordinates=coords,
            chain_length=int(value("chain_length", getattr(base, "chain_length", 5000000)) or 5000000),
            sample_frequency=int(value("sample_frequency", getattr(base, "sample_frequency", 1000)) or 1000),
            burnin=int(value("burnin", getattr(base, "burnin", 0)) or 0),
            model_type=str(value("model_type", getattr(base, "model_type", "DISTANCE_NORM")) or "DISTANCE_NORM"),
            guess_initial_rates=bool(value("guess_initial_rates", getattr(base, "guess_initial_rates", True))),
            use_auxiliary_sampling=bool(value("use_auxiliary_sampling", getattr(base, "use_auxiliary_sampling", False))),
            geo_distance_power_positive=bool(value("geo_distance_power_positive", getattr(base, "geo_distance_power_positive", False))),
            geo_distance_truncate=bool(value("geo_distance_truncate", getattr(base, "geo_distance_truncate", False))),
            seed=seed_value,
            other_options=str(value("other_options", getattr(base, "other_options", "")) or ""),
            save_original_results=bool(value("save_original_results", getattr(base, "save_original_results", False))),
            save_original_results_path=str(value("save_original_results_path", getattr(base, "save_original_results_path", "")) or ""),
        )
        config.validate()
        return config


def normalize_bayarea_model_type(value: str) -> str:
    text = str(value or "DISTANCE_NORM").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "INDEPENDENCE": "INDEPENDENCE",
        "1": "INDEPENDENCE",
        "DISTANCE": "DISTANCE_NORM",
        "DISTANCE_NORM": "DISTANCE_NORM",
        "DISTANCE_NORMALIZED": "DISTANCE_NORM",
        "3": "DISTANCE_NORM",
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("Unsupported BayArea model type: %s" % value)

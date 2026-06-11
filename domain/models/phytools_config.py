from dataclasses import dataclass
from typing import List

from domain.models.bayestraits_config import (
    BAYESTRAITS_CONTINUOUS_TRANSFORMS,
    normalize_bayestraits_continuous_transform,
)


PHYTOOLS_CONTINUOUS_METHODS = {
    "FASTANC": "Continuous: fastAnc",
    "FASTANC_CI": "Continuous: fastAnc + 95% CI",
    "ANC_BAYES": "Continuous: anc.Bayes (MCMC)",
    "ANC_ML_BM": "Experimental: anc.ML (BM)",
    "ANC_ML_OU": "Experimental: anc.ML (OU)",
    "ANC_ML_EB": "Experimental: anc.ML (EB)",
}

PHYTOOLS_TREESET_CONTINUOUS_METHODS = {
    "FASTANC": PHYTOOLS_CONTINUOUS_METHODS["FASTANC"],
    "FASTANC_CI": PHYTOOLS_CONTINUOUS_METHODS["FASTANC_CI"],
}

PHYTOOLS_EXPERIMENTAL_METHODS = {
    "ANC_ML_BM",
    "ANC_ML_OU",
    "ANC_ML_EB",
}

PHYTOOLS_DISCRETE_METHODS = {
    "ACE_ER": "Discrete: ace (ER)",
    "ACE_SYM": "Discrete: ace (SYM)",
    "ACE_ARD": "Discrete: ace (ARD)",
}

PHYTOOLS_METHODS = {}
PHYTOOLS_METHODS.update(PHYTOOLS_CONTINUOUS_METHODS)
PHYTOOLS_METHODS.update(PHYTOOLS_DISCRETE_METHODS)


@dataclass
class PhytoolsConfig:
    trait_columns: List[str]
    trait_column: str = ""
    method: str = "FASTANC"
    continuous_transform: str = "none"
    threads: int = 1
    anc_ml_maxit: int = 2000
    bayes_iterations: int = 10000
    bayes_sample_frequency: int = 1000
    bayes_burnin: int = 0
    seed: int = 1

    @classmethod
    def default_for_columns(cls, trait_columns):
        columns = [str(x).strip() for x in list(trait_columns or []) if str(x).strip()]
        return cls(
            trait_columns=columns,
            trait_column=columns[0] if columns else "",
        )

    def validate(self) -> None:
        columns = [str(x).strip() for x in list(self.trait_columns or []) if str(x).strip()]
        if not columns:
            raise ValueError("phytools requires at least one trait column.")
        self.trait_columns = columns

        self.trait_column = str(self.trait_column or "").strip()
        if not self.trait_column:
            self.trait_column = columns[0]
        if self.trait_column not in columns:
            raise ValueError("Selected trait column is not present in the current matrix: %s" % self.trait_column)

        self.method = normalize_phytools_method(self.method)
        self.continuous_transform = normalize_bayestraits_continuous_transform(self.continuous_transform)
        self.threads = max(1, int(getattr(self, "threads", 1) or 1))
        self.anc_ml_maxit = max(100, int(getattr(self, "anc_ml_maxit", 2000) or 2000))
        self.bayes_iterations = max(100, int(getattr(self, "bayes_iterations", 10000) or 10000))
        self.bayes_sample_frequency = max(1, int(getattr(self, "bayes_sample_frequency", 1000) or 1000))
        self.bayes_burnin = max(0, int(getattr(self, "bayes_burnin", 0) or 0))
        self.seed = max(0, int(getattr(self, "seed", 1) or 0))
        if self.bayes_burnin >= self.bayes_iterations:
            raise ValueError("Bayesian burn-in must be smaller than iterations.")


def normalize_phytools_method(value: str) -> str:
    key = str(value or "").strip().upper()
    if key in PHYTOOLS_METHODS:
        return key
    raise ValueError("Unsupported phytools method: %s" % value)


def phytools_method_kind(method: str) -> str:
    key = normalize_phytools_method(method)
    if key in PHYTOOLS_CONTINUOUS_METHODS:
        return "continuous"
    if key in PHYTOOLS_DISCRETE_METHODS:
        return "discrete"
    raise ValueError("Unsupported phytools method: %s" % method)


def phytools_ace_model(method: str) -> str:
    key = normalize_phytools_method(method)
    if key == "ACE_ER":
        return "ER"
    if key == "ACE_SYM":
        return "SYM"
    if key == "ACE_ARD":
        return "ARD"
    return ""


def phytools_continuous_model(method: str) -> str:
    key = normalize_phytools_method(method)
    if key == "ANC_ML_BM":
        return "BM"
    if key == "ANC_ML_OU":
        return "OU"
    if key == "ANC_ML_EB":
        return "EB"
    return ""


def phytools_is_experimental(method: str) -> bool:
    return normalize_phytools_method(method) in PHYTOOLS_EXPERIMENTAL_METHODS


__all__ = [
    "BAYESTRAITS_CONTINUOUS_TRANSFORMS",
    "PHYTOOLS_CONTINUOUS_METHODS",
    "PHYTOOLS_DISCRETE_METHODS",
    "PHYTOOLS_EXPERIMENTAL_METHODS",
    "PHYTOOLS_METHODS",
    "PHYTOOLS_TREESET_CONTINUOUS_METHODS",
    "PhytoolsConfig",
    "phytools_ace_model",
    "phytools_continuous_model",
    "phytools_is_experimental",
    "phytools_method_kind",
    "normalize_phytools_method",
]

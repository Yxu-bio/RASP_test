from dataclasses import dataclass, field
from typing import List
import random


@dataclass
class TreeCollectionPreparedResult:
    raw_count: int = 0
    loaded_count: int = 0
    parse_error_count: int = 0
    bifurcating_count: int = 0
    post_burnin_count: int = 0
    analysis_count: int = 0

    corrected_pre_burnin: int = 0
    corrected_post_burnin: int = 0
    corrected_random_sample_size: int = 0

    loaded_entries: List[object] = field(default_factory=list)
    bifurcating_entries: List[object] = field(default_factory=list)
    post_filtered_entries: List[object] = field(default_factory=list)
    analysis_entries: List[object] = field(default_factory=list)


class TreeCollectionPrepareService:
    def prepare(
        self,
        collection,
        pre_burnin: int = 0,
        post_burnin: int = 0,
        enable_random_sampling: bool = False,
        random_sample_size: int = 0,
    ) -> TreeCollectionPreparedResult:
        if collection is None:
            return TreeCollectionPreparedResult()

        result = TreeCollectionPreparedResult()
        result.raw_count = collection.raw_tree_count

        pre_burnin = max(0, int(pre_burnin))
        post_burnin = max(0, int(post_burnin))
        random_sample_size = max(0, int(random_sample_size))

        if pre_burnin > result.raw_count:
            pre_burnin = result.raw_count
        result.corrected_pre_burnin = pre_burnin

        loaded_entries = collection.get_loaded_entries(pre_burnin=pre_burnin)
        result.loaded_entries = loaded_entries
        result.loaded_count = len(loaded_entries)

        result.parse_error_count = sum(
            1 for x in loaded_entries if str(getattr(x, "parse_error", "")).strip()
        )

        bifurcating_entries = collection.get_bifurcating_entries(pre_burnin=pre_burnin)
        result.bifurcating_entries = bifurcating_entries
        result.bifurcating_count = len(bifurcating_entries)

        if post_burnin > result.bifurcating_count:
            post_burnin = result.bifurcating_count
        result.corrected_post_burnin = post_burnin

        post_filtered_entries = bifurcating_entries[post_burnin:]
        result.post_filtered_entries = post_filtered_entries
        result.post_burnin_count = len(post_filtered_entries)

        if not enable_random_sampling:
            result.analysis_entries = post_filtered_entries
            result.analysis_count = len(post_filtered_entries)
            result.corrected_random_sample_size = random_sample_size
            return result

        result.corrected_random_sample_size = random_sample_size

        if random_sample_size <= 0:
            result.analysis_entries = []
        else:
            result.analysis_entries = self._legacy_random_sample(post_filtered_entries, random_sample_size)

        result.analysis_count = len(result.analysis_entries)
        return result

    def prepare_loaded_entries(
        self,
        loaded_entries,
        post_burnin: int = 0,
        enable_random_sampling: bool = False,
        random_sample_size: int = 0,
    ) -> TreeCollectionPreparedResult:
        loaded_entries = list(loaded_entries or [])

        result = TreeCollectionPreparedResult()
        result.raw_count = len(loaded_entries)
        result.loaded_entries = loaded_entries
        result.loaded_count = len(loaded_entries)

        result.parse_error_count = sum(
            1 for x in loaded_entries if str(getattr(x, "parse_error", "")).strip()
        )

        bifurcating_entries = [
            x for x in loaded_entries if getattr(x, "is_bifurcating", False)
        ]
        result.bifurcating_entries = bifurcating_entries
        result.bifurcating_count = len(bifurcating_entries)

        post_burnin = max(0, int(post_burnin))
        random_sample_size = max(0, int(random_sample_size))

        if post_burnin > result.bifurcating_count:
            post_burnin = result.bifurcating_count
        result.corrected_post_burnin = post_burnin

        post_filtered_entries = bifurcating_entries[post_burnin:]
        result.post_filtered_entries = post_filtered_entries
        result.post_burnin_count = len(post_filtered_entries)

        if not enable_random_sampling:
            result.analysis_entries = post_filtered_entries
            result.analysis_count = len(post_filtered_entries)
            result.corrected_random_sample_size = random_sample_size
            return result

        result.corrected_random_sample_size = random_sample_size

        if random_sample_size <= 0:
            result.analysis_entries = []
        else:
            result.analysis_entries = self._legacy_random_sample(post_filtered_entries, random_sample_size)

        result.analysis_count = len(result.analysis_entries)
        return result

    def _legacy_random_sample(self, entries, random_sample_size: int):
        entries = list(entries or [])
        if not entries or random_sample_size <= 0:
            return []

        # Old RASP samples tree numbers repeatedly with System.Random.Next,
        # so duplicates are allowed.  Its upper bound is exclusive, which
        # leaves the last loaded tree out when more than one tree is present.
        upper = len(entries) - 1 if len(entries) > 1 else len(entries)
        return [entries[random.randrange(0, upper)] for _ in range(random_sample_size)]

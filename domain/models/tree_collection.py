from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class TreeCollectionEntry:
    tree_name: str
    original_tree_text: str
    translated_tree_text: str = ""
    parsed_tree: Any = None
    is_bifurcating: bool = False
    parse_error: str = ""


@dataclass
class TreeCollection:
    source_path: str
    format_name: str = "nexus"
    taxa_names: List[str] = field(default_factory=list)
    translate_map: Dict[str, str] = field(default_factory=dict)
    entries: List[TreeCollectionEntry] = field(default_factory=list)

    @property
    def raw_tree_count(self) -> int:
        return len(self.entries)

    def get_loaded_entries(self, pre_burnin: int = 0) -> List[TreeCollectionEntry]:
        n = max(0, int(pre_burnin))
        return self.entries[n:]

    def get_bifurcating_entries(self, pre_burnin: int = 0) -> List[TreeCollectionEntry]:
        loaded = self.get_loaded_entries(pre_burnin=pre_burnin)
        return [x for x in loaded if x.is_bifurcating]

    def get_analysis_entries(
        self,
        pre_burnin: int = 0,
        post_burnin: int = 0,
        enable_random_sampling: bool = False,
        random_sample_size: int = 0,
    ) -> List[TreeCollectionEntry]:
        entries = self.get_bifurcating_entries(pre_burnin=pre_burnin)

        post_n = max(0, int(post_burnin))
        if post_n > 0:
            entries = entries[post_n:]

        if not enable_random_sampling:
            return entries

        k = max(0, int(random_sample_size))
        if k <= 0:
            return []

        if k >= len(entries):
            return entries

        import random
        return random.sample(entries, k)
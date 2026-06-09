from dataclasses import dataclass


@dataclass
class TreeCollectionOptions:
    pre_burnin: int = 0
    post_burnin: int = 0
    enable_random_sampling: bool = True
    random_sample_size: int = 100

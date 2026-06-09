from dataclasses import dataclass


@dataclass
class SelectedNodeInfo:
    node_id: str
    name: str
    is_leaf: bool
    children_count: int
    clade_signature: str = ""

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "is_leaf": self.is_leaf,
            "children_count": self.children_count,
            "clade_signature": self.clade_signature,
        }

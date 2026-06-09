from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass
class ProjectImportCandidate:
    path: str
    label: str
    score: int = 0


@dataclass
class ProjectImportPlan:
    root_dir: str
    consensus_tree_candidates: list = field(default_factory=list)
    tree_collection_candidates: list = field(default_factory=list)
    matrix_candidates: list = field(default_factory=list)

    @property
    def selected_consensus_tree(self):
        return self.consensus_tree_candidates[0].path if self.consensus_tree_candidates else ""

    @property
    def selected_tree_collection(self):
        return self.tree_collection_candidates[0].path if self.tree_collection_candidates else ""

    @property
    def selected_matrix(self):
        return self.matrix_candidates[0].path if self.matrix_candidates else ""

    def has_any_candidates(self):
        return bool(
            self.consensus_tree_candidates
            or self.tree_collection_candidates
            or self.matrix_candidates
        )

    def is_unambiguous(self):
        return (
            len(self.consensus_tree_candidates) == 1
            and len(self.tree_collection_candidates) == 1
            and len(self.matrix_candidates) == 1
        )


class ProjectImportService:
    TREE_EXTENSIONS = {".tree", ".tre", ".nwk", ".newick", ".nex", ".nexus", ".txt"}
    COLLECTION_EXTENSIONS = {".trees", ".nex", ".nexus", ".tre", ".txt"}
    MATRIX_EXTENSIONS = {".csv", ".tsv", ".txt"}
    IGNORED_DIRS = {
        ".git",
        ".idea",
        "__pycache__",
        "runs",
        "engines",
        "infrastructure",
        "application",
        "domain",
        "gui",
        "visualization",
    }

    def scan(self, root_dir):
        root = Path(root_dir)
        if not root.exists() or not root.is_dir():
            raise ValueError("项目文件夹不存在: %s" % root_dir)

        consensus = []
        collections = []
        matrices = []

        for path in self._iter_candidate_files(root):
            lower_name = path.name.lower()
            suffix = path.suffix.lower()

            if suffix in self.MATRIX_EXTENSIONS and self._looks_like_matrix(path):
                matrices.append(self._candidate(path, root, self._matrix_score(lower_name)))
                continue

            if suffix in self.TREE_EXTENSIONS or suffix in self.COLLECTION_EXTENSIONS:
                tree_count = self._count_tree_definitions(path)
                if suffix == ".trees" or tree_count > 1:
                    collections.append(self._candidate(path, root, self._collection_score(lower_name, tree_count)))
                elif self._looks_like_tree(path):
                    consensus.append(self._candidate(path, root, self._consensus_score(lower_name)))

        return ProjectImportPlan(
            root_dir=str(root),
            consensus_tree_candidates=self._sort_candidates(consensus),
            tree_collection_candidates=self._sort_candidates(collections),
            matrix_candidates=self._sort_candidates(matrices),
        )

    def _iter_candidate_files(self, root):
        files = []
        for path in root.iterdir():
            if path.is_file():
                files.append(path)

        if files:
            return files

        for path in root.rglob("*"):
            if len(files) >= 300:
                break
            if not path.is_file():
                continue
            rel_parts = path.relative_to(root).parts
            if any(part in self.IGNORED_DIRS for part in rel_parts[:-1]):
                continue
            files.append(path)
        return files

    def _candidate(self, path, root, score):
        try:
            label = str(path.relative_to(root))
        except Exception:
            label = path.name
        return ProjectImportCandidate(path=str(path), label=label, score=int(score))

    def _sort_candidates(self, candidates):
        return sorted(
            list(candidates or []),
            key=lambda item: (-int(item.score), len(str(item.label)), str(item.label).lower()),
        )

    def _matrix_score(self, lower_name):
        score = 10
        if lower_name in ("distribution.csv", "distribution.tsv", "ranges.csv", "range.csv"):
            score += 100
        if "distribution" in lower_name:
            score += 40
        if "range" in lower_name:
            score += 30
        return score

    def _consensus_score(self, lower_name):
        score = 10
        if lower_name.endswith(".tree"):
            score += 60
        if "consensus" in lower_name or "reference" in lower_name or "final" in lower_name:
            score += 50
        if lower_name.endswith(".trees"):
            score -= 100
        return score

    def _collection_score(self, lower_name, tree_count):
        score = 10 + min(int(tree_count or 0), 100)
        if lower_name.endswith(".trees"):
            score += 80
        if "dataset" in lower_name or "posterior" in lower_name or "trees" in lower_name:
            score += 40
        if "consensus" in lower_name or "reference" in lower_name:
            score -= 50
        return score

    def _looks_like_matrix(self, path):
        try:
            sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:4096]
        except Exception:
            return False
        if not sample.strip():
            return False
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        cells = [cell.strip() for cell in re.split(r"[\t,]", first_line)]
        return len(cells) >= 3 and cells[0] == "ID" and cells[1] == "Name"

    def _looks_like_tree(self, path):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            return False
        if not text or ";" not in text:
            return False
        if text.lstrip().upper().startswith("#NEXUS"):
            return self._count_tree_definitions(path) == 1
        return "(" in text and ")" in text

    def _count_tree_definitions(self, path):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return 0
        if not text.strip():
            return 0
        if text.lstrip().upper().startswith("#NEXUS"):
            return len(
                re.findall(
                    r"^\s*tree\s+[^\s=]+\s*(?:\[[^\]]*\])?\s*=",
                    text,
                    flags=re.IGNORECASE | re.MULTILINE,
                )
            )
        if path.suffix.lower() == ".trees":
            return max(1, text.count(";"))
        return 0

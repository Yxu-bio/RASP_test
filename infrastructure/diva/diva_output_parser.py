import re
from pathlib import Path
from typing import Dict, List

from domain.models.diva_result import DivaNodeResult, DivaResult


class DivaOutputParser:
    """
    按真实 DIVA 输出格式解析，例如：
    node 24 (anc. of terminals 1-6): C BC
    node 37 (anc. of terminals 1-19): A AB
    """

    NODE_LINE_RE = re.compile(
        r"^node\s+(?P<node_id>\d+)\s+"
        r"\(anc\.\s+of\s+terminals\s+(?P<terminals>[^)]+)\):\s*"
        r"(?P<states>.+?)\s*$",
        re.IGNORECASE,
    )

    def parse_log_file(self, log_file: str, dataset) -> DivaResult:
        path = Path(log_file)
        if not path.exists():
            raise FileNotFoundError(f"DIVA 控制台日志不存在: {log_file}")

        text = path.read_text(encoding="utf-8", errors="ignore")
        result = DivaResult(dataset=dataset)

        hit = False
        in_distribution_block = False
        saw_distribution_header = False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.lower().startswith("optimal distributions at each node"):
                in_distribution_block = True
                saw_distribution_header = True
                continue

            if saw_distribution_header and in_distribution_block and not line:
                in_distribution_block = False
                continue

            if not line:
                continue

            if saw_distribution_header and not in_distribution_block:
                continue

            m = self.NODE_LINE_RE.match(line)
            if not m:
                continue

            hit = True
            diva_node_id = int(m.group("node_id"))
            terminal_spec = m.group("terminals").strip()
            states_raw = m.group("states").strip()

            terminal_indices = self._parse_terminal_spec(terminal_spec)
            if not terminal_indices:
                result.parse_warnings.append(f"无法解析 terminals: {terminal_spec}")
                continue

            clade_key = self._terminals_to_clade_key(terminal_indices, dataset)
            states = self._parse_states(states_raw)

            result.node_results[clade_key] = DivaNodeResult(
                node_key=clade_key,
                diva_node_id=diva_node_id,
                terminal_spec=terminal_spec,
                states=states,
                raw_line=line,
            )

        if not hit:
            result.parse_warnings.append("日志中未找到 'node ... (anc. of terminals ...): ...' 结果行。")

        return result

    def _parse_terminal_spec(self, spec: str) -> List[int]:
        """
        支持：
        1-6
        10-12
        5
        1-3,5,7-9
        """
        spec = spec.strip()
        if not spec:
            return []

        tokens = re.split(r"[,\s]+", spec)
        values: List[int] = []

        for token in tokens:
            token = token.strip()
            if not token:
                continue

            if "-" in token:
                a, b = token.split("-", 1)
                start = int(a)
                end = int(b)
                if start <= end:
                    values.extend(range(start, end + 1))
                else:
                    values.extend(range(end, start + 1))
            else:
                values.append(int(token))

        return sorted(set(values))

    def _terminals_to_clade_key(self, terminal_indices: List[int], dataset) -> str:
        taxa = []
        for idx in terminal_indices:
            if idx not in dataset.index_to_name:
                raise ValueError(f"DIVA 输出中的 terminal {idx} 不在 index_to_name 中")
            taxa.append(dataset.index_to_name[idx])

        return "|".join(sorted(taxa))

    def _parse_states(self, text: str) -> List[str]:
        """
        DIVA 真实输出是空格分隔，例如：
        C
        C BC
        AB AC ABC
        """
        tokens = []
        for part in re.split(r"\s+", text.strip()):
            token = part.strip()
            if not token:
                continue
            if token not in tokens:
                tokens.append(token)
        return tokens

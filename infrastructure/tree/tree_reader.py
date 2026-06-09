import re
from pathlib import Path

from domain.models.tree_collection import TreeCollection, TreeCollectionEntry


class TreeReader:
    def read_text(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"树文件不存在: {file_path}")

        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError("树文件内容为空")

        return text

    def read_newick(self, file_path: str) -> str:
        text = self.read_text(file_path)

        if ";" not in text:
            raise ValueError("看起来不是合法的 Newick 内容，缺少分号 ';'")

        return text

    def read_nexus(self, file_path: str) -> str:
        text = self.read_text(file_path)
        return self.parse_nexus_text(text)

    def read_tree(self, file_path: str) -> str:
        text = self.read_text(file_path)
        stripped = text.lstrip()

        if stripped.upper().startswith("#NEXUS"):
            return self.parse_nexus_text(text)

        return self.read_newick(file_path)

    def read_tree_collection(self, file_path: str) -> TreeCollection:
        text = self.read_text(file_path)
        stripped = text.lstrip()

        if not stripped.upper().startswith("#NEXUS"):
            raise ValueError("当前树集合读入仅支持 NEXUS 多树文件")

        collection = self.parse_nexus_tree_collection(text)
        collection.source_path = str(Path(file_path))
        return collection

    def parse_nexus_text(self, text: str) -> str:
        translate_map = self._parse_translate_block(text)
        tree_text = self._parse_tree_block(text)

        if translate_map:
            tree_text = self._replace_numeric_taxa(tree_text, translate_map)

        return tree_text

    def parse_nexus_tree_collection(self, text: str) -> TreeCollection:
        translate_map = self._parse_translate_block(text)
        taxa_names = self._parse_taxlabels_block(text)
        entries = []

        for tree_name, raw_tree_text in self._parse_all_tree_blocks(text):
            translated = raw_tree_text
            if translate_map:
                translated = self._replace_numeric_taxa(translated, translate_map)

            parsed_tree = None
            parse_error = ""
            is_bifurcating = False

            try:
                cleaned = self._strip_newick_comments(translated)
                parsed_tree = self._parse_ete_tree(cleaned)
                is_bifurcating = self._is_fully_bifurcating(parsed_tree)
            except Exception as exc:
                parse_error = str(exc)

            entries.append(
                TreeCollectionEntry(
                    tree_name=tree_name,
                    original_tree_text=raw_tree_text,
                    translated_tree_text=translated,
                    parsed_tree=parsed_tree,
                    is_bifurcating=is_bifurcating,
                    parse_error=parse_error,
                )
            )

        return TreeCollection(
            source_path="",
            format_name="nexus",
            taxa_names=taxa_names,
            translate_map=translate_map,
            entries=entries,
        )

    def _parse_translate_block(self, text: str) -> dict:
        match = re.search(
            r"Translate\s+(.*?)\s*;",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return {}

        block = match.group(1).strip()
        translate_map = {}

        parts = [p.strip() for p in block.split(",") if p.strip()]
        for part in parts:
            m = re.match(r"(\d+)\s+(.+)", part)
            if not m:
                continue

            key = m.group(1).strip()
            value = m.group(2).strip().strip("'").strip('"')
            translate_map[key] = value

        return translate_map

    def _parse_taxlabels_block(self, text: str) -> list:
        match = re.search(
            r"Taxlabels\s+(.*?)\s*;",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return []

        block = match.group(1)
        names = []
        for line in block.splitlines():
            s = line.strip()
            if not s:
                continue
            s = s.rstrip(",")
            s = s.strip("'").strip('"')
            if s:
                names.append(s)

        return names

    def _parse_tree_block(self, text: str) -> str:
        match = re.search(
            r"tree\s+[^=]+=\s*(?:\[[^\]]*\]\s*)?(.+?;)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            raise ValueError("NEXUS 文件中未找到 tree 定义")

        tree_text = match.group(1).strip()
        return tree_text

    def _parse_all_tree_blocks(self, text: str) -> list:
        matches = re.finditer(
            r"^\s*tree\s+([^\s=]+)\s*(?:\[[^\]]*\])?\s*=\s*(?:\[[^\]]*\]\s*)?(.+?;)\s*$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )

        items = []
        for m in matches:
            tree_name = m.group(1).strip()
            tree_text = m.group(2).strip()
            items.append((tree_name, tree_text))

        if not items:
            raise ValueError("NEXUS 树集合中未找到任何 tree 定义")

        return items

    def _replace_numeric_taxa(self, tree_text: str, translate_map: dict) -> str:
        def repl(match):
            token = match.group(1)
            return translate_map.get(token, token)

        pattern = r'(?<=[(,])\s*(\d+)\s*(?=[:),])'
        return re.sub(pattern, repl, tree_text)

    def _strip_newick_comments(self, tree_text: str) -> str:
        return re.sub(r"\[.*?\]", "", tree_text)

    def _parse_ete_tree(self, tree_text: str):
        from ete3 import Tree
        return Tree(tree_text, format=1)

    def _is_fully_bifurcating(self, tree) -> bool:
        for node in tree.traverse():
            if node.is_leaf():
                continue
            if len(node.children) != 2:
                return False
        return True
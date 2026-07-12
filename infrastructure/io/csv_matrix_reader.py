import csv
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from domain.models.state_matrix import StateMatrix


class CsvMatrixReader:
    def read(self, file_path: str) -> StateMatrix:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError("Matrix file does not exist: %s" % file_path)

        if path.suffix.lower() == ".xlsx":
            rows = self._read_xlsx_rows(path)
        else:
            delimiter = self._detect_delimiter(path)
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f, delimiter=delimiter)
                rows = [row for row in reader if row and any(cell.strip() for cell in row)]

        if not rows:
            raise ValueError("Matrix file is empty")

        header = [col.strip() for col in rows[0]]
        has_id_name = len(header) >= 3 and header[0] == "ID" and header[1] == "Name"
        has_name_only = len(header) >= 2 and self._is_taxon_name_column(header[0])
        if not has_id_name and not has_name_only:
            raise ValueError(
                "Matrix format requires either ID, Name, state columns or a first taxon-name column followed by state columns"
            )

        if has_id_name:
            state_columns = header[2:]
        else:
            state_columns = header[1:]

        parsed_rows = []
        ids = []
        taxa_names = []

        for i, row in enumerate(rows[1:], start=2):
            row = [cell.strip() for cell in row]
            if len(row) < len(header):
                row.extend([""] * (len(header) - len(row)))
            elif len(row) > len(header):
                row = row[:len(header)]

            if has_id_name:
                if len(row) < 2:
                    raise ValueError("Row %d has too few columns; at least ID and Name are required" % i)
                row_id = row[0]
                name = row[1]
                states = row[2:]
            else:
                if not row:
                    raise ValueError("Row %d has too few columns; a taxon name is required" % i)
                row_id = str(i - 1)
                name = row[0]
                states = row[1:]

            if not row_id:
                raise ValueError("Row %d has an empty ID" % i)
            if not name:
                raise ValueError("Row %d has an empty Name" % i)

            row_dict = {
                "ID": row_id,
                "Name": name,
            }
            for col_name, value in zip(state_columns, states):
                row_dict[col_name] = value

            parsed_rows.append(row_dict)
            ids.append(row_id)
            taxa_names.append(name)

        return StateMatrix(
            ids=ids,
            taxa_names=taxa_names,
            state_columns=state_columns,
            rows=parsed_rows,
            source_path=str(path),
        )

    def _detect_delimiter(self, path: Path) -> str:
        sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:2048]
        if "\t" in sample:
            return "\t"
        return ","

    def _is_taxon_name_column(self, name: str) -> bool:
        normalized = str(name or "").strip().lower().replace(" ", "_")
        return normalized in {
            "name",
            "taxon",
            "taxa",
            "taxon_name",
            "taxa_name",
            "species",
            "species_name",
            "current_name",
        }

    def _read_xlsx_rows(self, path: Path):
        with ZipFile(str(path), "r") as workbook:
            shared_strings = self._read_shared_strings(workbook)
            sheet_path = self._first_sheet_path(workbook)
            root = ElementTree.fromstring(workbook.read(sheet_path))

        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows = []
        for row_node in root.findall(".//m:sheetData/m:row", ns):
            cells = []
            for cell_node in row_node.findall("m:c", ns):
                ref = cell_node.attrib.get("r", "")
                col_index = self._column_index_from_ref(ref)
                while len(cells) < col_index:
                    cells.append("")
                cells.append(self._xlsx_cell_value(cell_node, shared_strings))
            if cells and any(str(cell).strip() for cell in cells):
                rows.append([str(cell).strip() for cell in cells])
        return rows

    def _read_shared_strings(self, workbook: ZipFile):
        if "xl/sharedStrings.xml" not in workbook.namelist():
            return []
        root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        strings = []
        for item in root.findall("m:si", ns):
            parts = []
            for text_node in item.findall(".//m:t", ns):
                parts.append(text_node.text or "")
            strings.append("".join(parts))
        return strings

    def _first_sheet_path(self, workbook: ZipFile):
        ns = {
            "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
        }
        workbook_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
        first_sheet = workbook_root.find(".//m:sheets/m:sheet", ns)
        if first_sheet is None:
            raise ValueError("XLSX workbook does not contain a worksheet")
        rel_id = first_sheet.attrib.get("{%s}id" % ns["r"])
        rel_root = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        for rel in rel_root.findall("rel:Relationship", ns):
            if rel.attrib.get("Id") == rel_id:
                target = rel.attrib.get("Target", "")
                if target.startswith("/"):
                    return target.lstrip("/")
                if target.startswith("xl/"):
                    return target
                return "xl/" + target
        raise ValueError("XLSX first worksheet relationship is missing")

    def _xlsx_cell_value(self, cell_node, shared_strings):
        cell_type = cell_node.attrib.get("t", "")
        ns_uri = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        value_node = cell_node.find("{%s}v" % ns_uri)
        if cell_type == "inlineStr":
            return "".join(
                text_node.text or ""
                for text_node in cell_node.findall(".//{%s}t" % ns_uri)
            )
        if value_node is None or value_node.text is None:
            return ""
        raw = value_node.text
        if cell_type == "s":
            try:
                return shared_strings[int(raw)]
            except (IndexError, TypeError, ValueError):
                return raw
        if cell_type == "b":
            return "1" if raw == "1" else "0"
        return raw

    def _column_index_from_ref(self, ref: str) -> int:
        letters = ""
        for char in ref:
            if char.isalpha():
                letters += char.upper()
            else:
                break
        if not letters:
            return 0
        index = 0
        for char in letters:
            index = index * 26 + (ord(char) - ord("A") + 1)
        return index - 1

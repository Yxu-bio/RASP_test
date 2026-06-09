import csv
from pathlib import Path

from domain.models.state_matrix import StateMatrix


class CsvMatrixReader:
    def read(self, file_path: str) -> StateMatrix:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"矩阵文件不存在: {file_path}")

        delimiter = self._detect_delimiter(path)

        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter=delimiter)
            rows = [row for row in reader if row and any(cell.strip() for cell in row)]

        if not rows:
            raise ValueError("矩阵文件为空")

        header = [col.strip() for col in rows[0]]
        if len(header) < 3:
            raise ValueError("矩阵文件至少需要三列：ID、Name 和至少一个状态列")

        if header[0] != "ID" or header[1] != "Name":
            raise ValueError("当前矩阵格式要求前两列必须分别为 ID 和 Name")

        state_columns = header[2:]

        parsed_rows = []
        ids = []
        taxa_names = []

        for i, row in enumerate(rows[1:], start=2):
            if len(row) < 2:
                raise ValueError(f"第 {i} 行列数不足，至少需要 ID 和 Name")

            row = [cell.strip() for cell in row]
            if len(row) < len(header):
                row.extend([""] * (len(header) - len(row)))
            elif len(row) > len(header):
                row = row[:len(header)]

            row_id = row[0]
            name = row[1]
            states = row[2:]

            if not row_id:
                raise ValueError(f"第 {i} 行 ID 为空")
            if not name:
                raise ValueError(f"第 {i} 行 Name 为空")

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

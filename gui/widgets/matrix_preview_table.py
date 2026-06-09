from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem


class MatrixPreviewTable(QTableWidget):
    trait_column_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self._headers = []
        self._selected_trait_column = ""
        self.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.cellClicked.connect(self._on_cell_clicked)

    def load_matrix(self, matrix, selected_trait_column=""):
        headers = ["ID", "Name"] + list(matrix.state_columns)
        self._headers = list(headers)
        rows = matrix.preview_rows(limit=100)

        self.clear()
        self.setRowCount(len(rows))
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)

        for row_idx, row in enumerate(rows):
            for col_idx, header in enumerate(headers):
                value = row.get(header, "")
                self.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

        self.resizeColumnsToContents()
        self.set_selected_trait_column(selected_trait_column)

    def set_selected_trait_column(self, column_name):
        column = str(column_name or "").strip()
        if column and column not in self._headers[2:]:
            column = ""
        self._selected_trait_column = column
        self._refresh_trait_column_style()

    def selected_trait_column(self):
        return self._selected_trait_column

    def _on_header_clicked(self, column_index):
        self._select_trait_column_index(column_index)

    def _on_cell_clicked(self, row_index, column_index):
        self._select_trait_column_index(column_index)

    def _select_trait_column_index(self, column_index):
        if column_index < 2 or column_index >= len(self._headers):
            return
        column = self._headers[column_index]
        self.set_selected_trait_column(column)
        self.trait_column_selected.emit(column)

    def _refresh_trait_column_style(self):
        selected_color = QColor(153, 204, 51)
        normal_color = QColor(255, 255, 255)
        for row in range(self.rowCount()):
            for col in range(2, self.columnCount()):
                item = self.item(row, col)
                if item is None:
                    continue
                column_name = self._headers[col] if col < len(self._headers) else ""
                item.setBackground(selected_color if column_name == self._selected_trait_column else normal_color)

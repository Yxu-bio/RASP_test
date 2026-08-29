import csv
from pathlib import Path

from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.window_behavior import configure_resizable_window


class TraitModelStatisticsDialog(QDialog):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        self.setWindowTitle("Trait Model Statistics - %s" % str(getattr(result, "model_name", "") or "Result"))
        self.resize(880, 620)
        self.setMinimumSize(680, 460)
        configure_resizable_window(self)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        summary = QLabel(self._summary_text(), self)
        summary.setWordWrap(True)
        layout.addWidget(summary)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_statistics_tab(), "Statistics")
        tabs.addTab(self._build_log_tab(self._analysis_log_path()), "Analysis log")
        tabs.addTab(self._build_log_tab(self._output_log_path()), "Raw output")
        layout.addWidget(tabs, 1)

        buttons = QHBoxLayout()
        export_button = QPushButton("Export CSV", self)
        export_button.clicked.connect(self._export_csv)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.close)
        buttons.addStretch(1)
        buttons.addWidget(export_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _build_statistics_tab(self):
        table = QTableWidget(self)
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Parameter", "Mean", "Minimum", "Maximum", "N"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        rows = self._summary_rows()
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                table.setItem(row_index, column_index, QTableWidgetItem(str(value)))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 5):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        return table

    def _build_log_tab(self, path):
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        text = QTextEdit(widget)
        text.setReadOnly(True)
        text.setLineWrapMode(QTextEdit.NoWrap)
        if path and path.exists():
            text.setPlainText(path.read_text(encoding="utf-8", errors="replace"))
        else:
            text.setPlainText("No log file is available for this result.")
        layout.addWidget(text)
        return widget

    def _summary_text(self):
        stats = dict(getattr(self.result, "model_statistics", {}) or {})
        lines = [
            "Model: %s" % str(getattr(self.result, "model_name", "") or "Trait model"),
            "Analysis: %s" % str(stats.get("analysis_method", "") or "not reported"),
            "Traits: %s" % ", ".join(str(x) for x in list(stats.get("trait_columns", []) or []) if str(x)),
            "Samples/rows: %s" % str(stats.get("sample_count", getattr(self.result, "effective_tree_count", 0))),
        ]
        note = str(getattr(self.result, "result_note", "") or "").strip()
        if note:
            lines.extend(["", note])
        warnings = list(getattr(self.result, "parse_warnings", []) or [])
        if warnings:
            lines.extend(["", "Warnings:"])
            lines.extend("- %s" % str(item) for item in warnings)
        return "\n".join(lines)

    def _summary_rows(self):
        stats = dict(getattr(self.result, "model_statistics", {}) or {})
        summaries = stats.get("numeric_summaries", {}) or {}
        rows = []
        for name, summary in summaries.items():
            if str(name) in ("Tree No", "Iteration"):
                continue
            summary = dict(summary or {})
            rows.append((
                str(name),
                self._format_number(summary.get("mean")),
                self._format_number(summary.get("min")),
                self._format_number(summary.get("max")),
                str(summary.get("n", "")),
            ))
        return rows

    def _analysis_log_path(self):
        path = str(getattr(self.result, "analysis_log_path", "") or "")
        if not path:
            path = str(dict(getattr(self.result, "model_statistics", {}) or {}).get("analysis_log_path", "") or "")
        return Path(path) if path else None

    def _output_log_path(self):
        path = str(getattr(self.result, "output_log_path", "") or "")
        if not path:
            path = str(dict(getattr(self.result, "model_statistics", {}) or {}).get("output_log_path", "") or "")
        return Path(path) if path else None

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export trait model statistics", "", "CSV files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Parameter", "Mean", "Minimum", "Maximum", "N"])
                writer.writerows(self._summary_rows())
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    @staticmethod
    def _format_number(value):
        if value is None or value == "":
            return ""
        try:
            return "%.8g" % float(value)
        except Exception:
            return str(value)

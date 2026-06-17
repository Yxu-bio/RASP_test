import csv
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class BSMEventTableDialog(QDialog):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        self.all_events = list(getattr(self.result, "events", []) or [])
        self.filtered_events = list(self.all_events)
        self.setWindowTitle("BioGeoBEARS BSM Event Table")
        self.resize(1180, 720)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_events_tab(), "Events")
        self.tabs.addTab(self._build_summary_tab(), "Summary")
        self.tabs.addTab(self._build_time_tab(), "Time")
        self.tabs.addTab(self._build_raw_tab(), "Raw tables")
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_filtered_views()

    def _build_events_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)

        top = QHBoxLayout()
        self.export_events_button = QPushButton("Export events CSV", page)
        self.export_events_button.clicked.connect(self._export_events_csv)
        self.events_caption_label = QLabel(self._events_caption(), page)
        top.addWidget(self.events_caption_label)
        top.addStretch(1)
        top.addWidget(self.export_events_button)
        layout.addLayout(top)

        filters = QGridLayout()
        filters.setContentsMargins(0, 0, 0, 0)
        filters.setHorizontalSpacing(6)
        filters.setVerticalSpacing(4)
        self.scope_combo = self._build_filter_combo(["anagenetic", "cladogenetic"], page)
        self.event_type_combo = self._build_filter_combo(self._unique_event_values("event_type"), page)
        self.source_combo = self._build_filter_combo(self._unique_event_values("source_range"), page)
        self.target_combo = self._build_filter_combo(self._unique_event_values("target_range"), page)
        self.time_min_edit = QLineEdit(page)
        self.time_min_edit.setPlaceholderText("min")
        self.time_max_edit = QLineEdit(page)
        self.time_max_edit.setPlaceholderText("max")
        self.search_edit = QLineEdit(page)
        self.search_edit.setPlaceholderText("text search")
        self.reset_filters_button = QPushButton("Reset filters", page)
        self.reset_filters_button.clicked.connect(self._reset_filters)

        filters.addWidget(QLabel("Scope", page), 0, 0)
        filters.addWidget(self.scope_combo, 0, 1)
        filters.addWidget(QLabel("Type", page), 0, 2)
        filters.addWidget(self.event_type_combo, 0, 3)
        filters.addWidget(QLabel("Source", page), 0, 4)
        filters.addWidget(self.source_combo, 0, 5)
        filters.addWidget(QLabel("Target", page), 0, 6)
        filters.addWidget(self.target_combo, 0, 7)
        filters.addWidget(QLabel("Time", page), 1, 0)
        filters.addWidget(self.time_min_edit, 1, 1)
        filters.addWidget(self.time_max_edit, 1, 2)
        filters.addWidget(QLabel("Search", page), 1, 3)
        filters.addWidget(self.search_edit, 1, 4, 1, 3)
        filters.addWidget(self.reset_filters_button, 1, 7)
        layout.addLayout(filters)

        for combo in [self.scope_combo, self.event_type_combo, self.source_combo, self.target_combo]:
            combo.currentIndexChanged.connect(self._apply_filters)
        self.time_min_edit.textChanged.connect(self._apply_filters)
        self.time_max_edit.textChanged.connect(self._apply_filters)
        self.search_edit.textChanged.connect(self._apply_filters)

        self.events_table = QTableWidget(page)
        self.events_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.events_table.setAlternatingRowColors(True)
        layout.addWidget(self.events_table, 1)
        return page

    def _build_summary_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)
        self.summary_text = QTextEdit(page)
        self.summary_text.setReadOnly(True)
        layout.addWidget(self.summary_text)
        return page

    def _build_time_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)
        self.time_table = QTableWidget(page)
        self.time_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.time_table.setAlternatingRowColors(True)
        layout.addWidget(self.time_table, 1)
        return page

    def _build_raw_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Table:", page))
        self.raw_table_combo = QComboBox(page)
        raw_tables = dict(getattr(self.result, "raw_tables", {}) or {})
        for name in sorted(raw_tables.keys()):
            self.raw_table_combo.addItem(name, name)
        self.raw_table_combo.currentIndexChanged.connect(self._populate_raw_table)
        controls.addWidget(self.raw_table_combo)
        controls.addStretch(1)
        self.export_raw_button = QPushButton("Export raw CSV", page)
        self.export_raw_button.clicked.connect(self._export_raw_csv)
        controls.addWidget(self.export_raw_button)
        layout.addLayout(controls)

        self.raw_table = QTableWidget(page)
        self.raw_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.raw_table.setAlternatingRowColors(True)
        layout.addWidget(self.raw_table, 1)
        return page

    def _events_caption(self):
        summary = dict(getattr(self.result, "summary", {}) or {})
        maps = summary.get("nummaps", "")
        prefix = "%d / %d BSM events" % (len(self.filtered_events), len(self.all_events))
        if maps != "":
            prefix += " from %s stochastic maps" % maps
        return prefix

    def _populate_events_table(self):
        events = list(self.filtered_events or [])
        headers = [
            "scope",
            "sample_id",
            "time",
            "node",
            "branch",
            "event_type",
            "event_text",
            "source_range",
            "target_range",
            "dispersal_to",
            "extirpation_from",
        ]
        rows = []
        for event in events:
            rows.append([
                getattr(event, "event_scope", ""),
                getattr(event, "sample_id", ""),
                "" if getattr(event, "time", None) is None else "%.6g" % float(event.time),
                getattr(event, "node", ""),
                getattr(event, "branch", ""),
                getattr(event, "event_type", ""),
                getattr(event, "event_text", ""),
                getattr(event, "source_range", ""),
                getattr(event, "target_range", ""),
                getattr(event, "dispersal_to", ""),
                getattr(event, "extirpation_from", ""),
            ])
        self._fill_table(self.events_table, headers, rows)

    def _populate_time_table(self):
        rows = self._build_time_series(self.filtered_events)
        keys = []
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(key)
        if "time" in keys:
            keys = ["time"] + [key for key in keys if key != "time"]
        table_rows = [[row.get(key, "") for key in keys] for row in rows]
        self._fill_table(self.time_table, keys, table_rows)

    def _populate_raw_table(self):
        if not hasattr(self, "raw_table"):
            return
        name = self.raw_table_combo.currentData() if hasattr(self, "raw_table_combo") else ""
        raw_tables = dict(getattr(self.result, "raw_tables", {}) or {})
        rows = list(raw_tables.get(str(name), []) or [])
        display_rows = rows[:5000]
        headers = []
        for row in display_rows:
            for key in row.keys():
                if key not in headers:
                    headers.append(key)
        table_rows = [[row.get(key, "") for key in headers] for row in display_rows]
        self._fill_table(self.raw_table, headers, table_rows)

    def _summary_text(self, events=None):
        events = list(self.filtered_events if events is None else events)
        event_type_counts = Counter(self._event_count_key(event) for event in events)
        route_counts = Counter(self._event_route_key(event) for event in events if self._event_route_key(event))
        lines = []
        lines.append("BioGeoBEARS BSM event summary")
        lines.append("")
        lines.append("Source model: %s" % str(getattr(self.result, "source_model_name", "") or "BioGeoBEARS"))
        lines.append("Filtered events: %d / %d" % (len(events), len(self.all_events)))
        metadata = self._filter_metadata()
        active_filters = [
            "%s=%s" % (key, value)
            for key, value in metadata.items()
            if str(value).strip() and str(value).strip().lower() not in ("all", "")
        ]
        if active_filters:
            lines.append("Filters: %s" % "; ".join(active_filters))
        lines.append("")
        lines.append("Event counts")
        if event_type_counts:
            for key, value in sorted(event_type_counts.items(), key=lambda x: (-int(x[1]), x[0])):
                lines.append("  %s: %s" % (key, value))
        else:
            lines.append("  none")
        if route_counts:
            lines.append("")
            lines.append("Top event routes")
            for route, value in sorted(route_counts.items(), key=lambda x: (-int(x[1]), x[0]))[:20]:
                lines.append("  %s: %s" % (route, value))
        summary = dict(getattr(self.result, "summary", {}) or {})
        if summary:
            lines.append("")
            lines.append("BSM run metadata")
            for key in sorted(summary.keys()):
                lines.append("%s: %s" % (key, summary.get(key)))
        return "\n".join([line for line in lines if line is not None])

    def _build_filter_combo(self, values, parent):
        combo = QComboBox(parent)
        combo.addItem("All", "")
        for value in sorted({str(item).strip() for item in list(values or []) if str(item).strip()}):
            combo.addItem(value, value)
        return combo

    def _unique_event_values(self, attribute):
        values = []
        for event in self.all_events:
            value = str(getattr(event, attribute, "") or "").strip()
            if value:
                values.append(value)
        return values

    def _apply_filters(self, *args):
        if not hasattr(self, "events_table"):
            return
        self.filtered_events = [
            event for event in self.all_events
            if self._event_matches_filters(event)
        ]
        self._refresh_filtered_views()

    def _refresh_filtered_views(self):
        if hasattr(self, "events_caption_label"):
            self.events_caption_label.setText(self._events_caption())
        if hasattr(self, "events_table"):
            self._populate_events_table()
        if hasattr(self, "summary_text"):
            self.summary_text.setPlainText(self._summary_text())
        if hasattr(self, "time_table"):
            self._populate_time_table()
        if hasattr(self, "raw_table"):
            self._populate_raw_table()

    def _reset_filters(self):
        for combo in [self.scope_combo, self.event_type_combo, self.source_combo, self.target_combo]:
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        for edit in [self.time_min_edit, self.time_max_edit, self.search_edit]:
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
        self._apply_filters()

    def _event_matches_filters(self, event):
        metadata = self._filter_metadata()
        scope = str(getattr(event, "event_scope", "") or "").strip()
        event_type = str(getattr(event, "event_type", "") or "").strip()
        source = str(getattr(event, "source_range", "") or "").strip()
        target = str(getattr(event, "target_range", "") or "").strip()
        if metadata["scope"] and scope != metadata["scope"]:
            return False
        if metadata["event_type"] and event_type != metadata["event_type"]:
            return False
        if metadata["source_range"] and source != metadata["source_range"]:
            return False
        if metadata["target_range"] and target != metadata["target_range"]:
            return False
        time_value = getattr(event, "time", None)
        if metadata["time_min"]:
            minimum = self._safe_float_or_none(metadata["time_min"])
            if minimum is not None and (time_value is None or float(time_value) < minimum):
                return False
        if metadata["time_max"]:
            maximum = self._safe_float_or_none(metadata["time_max"])
            if maximum is not None and (time_value is None or float(time_value) > maximum):
                return False
        search = metadata["search"].lower()
        if search:
            haystack = " ".join([
                scope,
                event_type,
                str(getattr(event, "event_text", "") or ""),
                source,
                target,
                str(getattr(event, "dispersal_to", "") or ""),
                str(getattr(event, "extirpation_from", "") or ""),
                str(getattr(event, "node", "") or ""),
                str(getattr(event, "branch", "") or ""),
            ]).lower()
            if search not in haystack:
                return False
        return True

    def _filter_metadata(self):
        def combo_value(name):
            widget = getattr(self, name, None)
            if widget is None:
                return ""
            return str(widget.currentData() or "").strip()

        def edit_value(name):
            widget = getattr(self, name, None)
            if widget is None:
                return ""
            return str(widget.text() or "").strip()

        return {
            "scope": combo_value("scope_combo"),
            "event_type": combo_value("event_type_combo"),
            "source_range": combo_value("source_combo"),
            "target_range": combo_value("target_combo"),
            "time_min": edit_value("time_min_edit"),
            "time_max": edit_value("time_max_edit"),
            "search": edit_value("search_edit"),
        }

    def _build_time_series(self, events):
        buckets = defaultdict(lambda: Counter())
        for event in list(events or []):
            if getattr(event, "time", None) is None:
                continue
            try:
                time_key = round(float(event.time), 6)
            except Exception:
                continue
            buckets[time_key][self._event_count_key(event)] += 1
            buckets[time_key]["total"] += 1

        rows = []
        for time_key in sorted(buckets.keys()):
            counter = buckets[time_key]
            row = {"time": time_key}
            for key, value in sorted(counter.items()):
                row[key] = int(value)
            rows.append(row)
        return rows

    def _event_count_key(self, event):
        event_type = str(getattr(event, "event_type", "") or "").strip()
        scope = str(getattr(event, "event_scope", "") or "").strip()
        if event_type:
            return "%s:%s" % (scope, event_type)
        return scope or "event"

    def _event_route_key(self, event):
        text = str(getattr(event, "event_text", "") or "").strip()
        if text and text.lower() not in ("none", "na", "<na>", "nan", "null"):
            return text
        source = str(getattr(event, "source_range", "") or "").strip()
        target = str(getattr(event, "target_range", "") or "").strip()
        if source or target:
            return "%s->%s" % (source or "?", target or "?")
        return ""

    def _safe_float_or_none(self, value):
        try:
            return float(str(value).strip())
        except Exception:
            return None

    def _export_events_csv(self):
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export BSM Events",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if "." not in path.replace("\\", "/").split("/")[-1]:
            path += ".csv"

        events = list(self.filtered_events or [])
        metadata = self._filter_metadata()
        headers = [
            "filter_scope",
            "filter_event_type",
            "filter_source_range",
            "filter_target_range",
            "filter_time_min",
            "filter_time_max",
            "filter_search",
            "source_model_name",
            "source_run_directory",
            "event_scope",
            "sample_id",
            "event_type",
            "event_text",
            "time",
            "node",
            "branch",
            "source_range",
            "target_range",
            "dispersal_to",
            "extirpation_from",
        ]
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                for event in events:
                    if is_dataclass(event):
                        row = asdict(event)
                    else:
                        row = dict(getattr(event, "__dict__", {}) or {})
                    row.update({
                        "filter_scope": metadata.get("scope", ""),
                        "filter_event_type": metadata.get("event_type", ""),
                        "filter_source_range": metadata.get("source_range", ""),
                        "filter_target_range": metadata.get("target_range", ""),
                        "filter_time_min": metadata.get("time_min", ""),
                        "filter_time_max": metadata.get("time_max", ""),
                        "filter_search": metadata.get("search", ""),
                        "source_model_name": str(getattr(self.result, "source_model_name", "") or ""),
                        "source_run_directory": str(getattr(self.result, "source_run_directory", "") or ""),
                    })
                    writer.writerow({key: row.get(key, "") for key in headers})
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_raw_csv(self):
        name = self.raw_table_combo.currentData() if hasattr(self, "raw_table_combo") else ""
        raw_tables = dict(getattr(self.result, "raw_tables", {}) or {})
        rows = list(raw_tables.get(str(name), []) or [])
        if not rows:
            QMessageBox.information(self, "Export raw CSV", "The selected raw table is empty.")
            return
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export Raw BSM Table",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if "." not in path.replace("\\", "/").split("/")[-1]:
            path += ".csv"

        headers = ["raw_table"]
        for row in rows:
            for key in row.keys():
                if key not in headers:
                    headers.append(key)
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                for row in rows:
                    out = dict(row)
                    out["raw_table"] = str(name)
                    writer.writerow({key: out.get(key, "") for key in headers})
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _fill_table(self, table, headers, rows):
        headers = [str(header) for header in list(headers or [])]
        rows = list(rows or [])
        table.setSortingEnabled(False)
        table.clear()
        table.setColumnCount(len(headers))
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels(headers)
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(list(row or [])):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row_idx, col_idx, item)
        table.resizeColumnsToContents()
        table.setSortingEnabled(True)
